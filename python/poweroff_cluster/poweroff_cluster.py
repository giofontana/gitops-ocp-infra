#!/usr/bin/env python3
"""Power off a bare-metal OpenShift cluster: drain nodes, graceful shutdown, force off."""

import argparse
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

REDFISH_SYSTEM_PATH = "/redfish/v1/Systems/System.Embedded.1"
REDFISH_RESET_PATH = f"{REDFISH_SYSTEM_PATH}/Actions/ComputerSystem.Reset"
ALL_PHASES = ["drain", "shutdown", "wait_poweroff"]

log = logging.getLogger(__name__)


# --- Configuration ---

def parse_hosts(hosts_str):
    hosts = []
    for entry in hosts_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) < 2:
            continue
        host = {"name": parts[0], "ansible_host": parts[1]}
        if len(parts) >= 3 and parts[2]:
            host["idrac_host"] = parts[2]
        hosts.append(host)
    return hosts


def load_config(env_path):
    if not os.path.isfile(env_path):
        log.error("Environment file not found: %s", env_path)
        sys.exit(1)

    load_dotenv(env_path, override=True)

    hosts_str = os.getenv("HOSTS")
    if not hosts_str:
        log.error("HOSTS variable is required in %s", env_path)
        sys.exit(1)

    username = os.getenv("IDRAC_USERNAME")
    password = os.getenv("IDRAC_PASSWORD")
    if not username or not password:
        log.error("IDRAC_USERNAME and IDRAC_PASSWORD are required in %s", env_path)
        sys.exit(1)

    return {
        "idrac": {
            "username": username,
            "password": password,
            "verify_certs": os.getenv("IDRAC_VERIFY_CERTS", "false").lower() == "true",
        },
        "ssh": {
            "user": os.getenv("SSH_USER", "core"),
            "key": os.getenv("SSH_KEY", ""),
        },
        "hosts": parse_hosts(hosts_str),
        "timeouts": {
            "drain_timeout": int(os.getenv("DRAIN_TIMEOUT", "60")),
            "power_off_poll_interval": int(os.getenv("POWER_OFF_POLL_INTERVAL", "30")),
            "power_off_poll_max_attempts": int(os.getenv("POWER_OFF_POLL_MAX_ATTEMPTS", "30")),
        },
    }


def get_idrac_hosts(config):
    return [h for h in config["hosts"] if "idrac_host" in h]


def get_ssh_hosts(config):
    return [h for h in config["hosts"] if "idrac_host" not in h]


def get_all_hostnames(config):
    return [h["name"] for h in config["hosts"]]


# --- Phase 1: Drain ---

def drain_host(hostname, drain_timeout, dry_run):
    cmd = [
        "oc", "adm", "drain", hostname,
        "--ignore-daemonsets",
        "--delete-emptydir-data",
        "--force",
        "--disable-eviction",
        f"--timeout={drain_timeout}s",
    ]
    cmd_str = " ".join(cmd)

    if dry_run:
        log.info("[DRY RUN] Would run: %s", cmd_str)
        return (hostname, True, "dry run")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=drain_timeout + 30)
        if result.returncode == 0:
            log.info("%s: drained successfully", hostname)
            return (hostname, True, "drained")
        log.warning("%s: drain returned rc=%d: %s", hostname, result.returncode,
                    result.stderr.strip() or result.stdout.strip())
        return (hostname, False, "drain failed")
    except subprocess.TimeoutExpired:
        log.warning("%s: drain timed out", hostname)
        return (hostname, False, "drain timed out")
    except FileNotFoundError:
        log.error("'oc' command not found in PATH")
        return (hostname, False, "oc not found")


def phase_drain(config, dry_run):
    log.info("=== Phase 1: Drain OCP Nodes ===")
    hostnames = get_all_hostnames(config)
    drain_timeout = config["timeouts"]["drain_timeout"]
    all_ok = True

    with ThreadPoolExecutor(max_workers=len(hostnames)) as pool:
        futures = {
            pool.submit(drain_host, name, drain_timeout, dry_run): name
            for name in hostnames
        }
        for future in as_completed(futures):
            name, success, msg = future.result()
            if not success:
                log.warning("%s: drain issue (%s), continuing with shutdown", name, msg)
                all_ok = False

    return all_ok


# --- Phase 2: Shutdown ---

def shutdown_host_idrac(host, idrac_creds, verify_certs, dry_run):
    name = host["name"]
    idrac = host["idrac_host"]
    url = f"https://{idrac}{REDFISH_RESET_PATH}"

    if dry_run:
        log.info("[DRY RUN] Would send GracefulShutdown to %s via %s", name, url)
        return (name, True, "dry run")

    try:
        resp = requests.post(
            url,
            json={"ResetType": "GracefulShutdown"},
            auth=(idrac_creds["username"], idrac_creds["password"]),
            verify=verify_certs,
            timeout=30,
        )
        if resp.status_code == 409:
            log.warning("%s: already powered off", name)
            return (name, True, "already off")
        resp.raise_for_status()
        log.info("%s: graceful shutdown command sent", name)
        return (name, True, "shutdown sent")
    except requests.RequestException as e:
        log.error("%s: failed to send shutdown: %s", name, e)
        return (name, False, str(e))


def shutdown_host_ssh(host, ssh_config, dry_run):
    name = host["name"]
    ip = host["ansible_host"]
    user = ssh_config["user"]
    key = ssh_config["key"]

    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
    ]
    if key:
        ssh_cmd += ["-i", key]
    ssh_cmd += [f"{user}@{ip}", "sudo", "shutdown", "-h", "now"]
    cmd_str = " ".join(ssh_cmd)

    if dry_run:
        log.info("[DRY RUN] Would run: %s", cmd_str)
        return (name, True, "dry run")

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        # SSH to a shutting-down host often returns non-zero as connection drops
        log.info("%s: shutdown command sent via SSH", name)
        return (name, True, "shutdown sent via SSH")
    except subprocess.TimeoutExpired:
        log.warning("%s: SSH shutdown timed out", name)
        return (name, False, "SSH timeout")
    except FileNotFoundError:
        log.error("'ssh' command not found in PATH")
        return (name, False, "ssh not found")


def phase_shutdown(config, dry_run):
    log.info("=== Phase 2: Graceful Shutdown ===")
    creds = config["idrac"]
    verify = creds["verify_certs"]
    ssh_config = config["ssh"]
    all_ok = True

    idrac_hosts = get_idrac_hosts(config)
    ssh_hosts = get_ssh_hosts(config)

    all_hosts = len(idrac_hosts) + len(ssh_hosts)
    with ThreadPoolExecutor(max_workers=max(all_hosts, 1)) as pool:
        futures = {}
        for h in idrac_hosts:
            futures[pool.submit(shutdown_host_idrac, h, creds, verify, dry_run)] = h["name"]
        for h in ssh_hosts:
            futures[pool.submit(shutdown_host_ssh, h, ssh_config, dry_run)] = h["name"]

        for future in as_completed(futures):
            name, success, msg = future.result()
            if not success:
                all_ok = False

    return all_ok


# --- Phase 3: Wait for Power Off + Force Off ---

def wait_host_poweroff(host, idrac_creds, verify_certs, poll_interval, max_attempts, dry_run):
    name = host["name"]
    idrac = host["idrac_host"]
    url = f"https://{idrac}{REDFISH_SYSTEM_PATH}"

    if dry_run:
        log.info("[DRY RUN] Would poll %s for power state at %s", name, url)
        return (name, True, "dry run")

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(
                url,
                auth=(idrac_creds["username"], idrac_creds["password"]),
                verify=verify_certs,
                timeout=15,
            )
            if resp.ok:
                power_state = resp.json().get("PowerState", "Unknown")
                log.debug("%s: power state = %s (attempt %d)", name, power_state, attempt)
                if power_state == "Off":
                    log.info("%s: powered off", name)
                    return (name, True, "powered off")
        except requests.RequestException as e:
            log.debug("%s: unreachable (%s), attempt %d", name, e, attempt)

        if attempt < max_attempts:
            time.sleep(poll_interval)

    log.warning("%s: still on after %d attempts, will force off", name, max_attempts)
    return (name, False, "still on")


def force_off_host(host, idrac_creds, verify_certs, dry_run):
    name = host["name"]
    idrac = host["idrac_host"]
    url = f"https://{idrac}{REDFISH_RESET_PATH}"

    if dry_run:
        log.info("[DRY RUN] Would send ForceOff to %s via %s", name, url)
        return (name, True, "dry run")

    try:
        resp = requests.post(
            url,
            json={"ResetType": "ForceOff"},
            auth=(idrac_creds["username"], idrac_creds["password"]),
            verify=verify_certs,
            timeout=30,
        )
        if resp.status_code == 409:
            log.info("%s: already powered off", name)
            return (name, True, "already off")
        resp.raise_for_status()
        log.info("%s: force off command sent", name)
        return (name, True, "force off sent")
    except requests.RequestException as e:
        log.error("%s: failed to force off: %s", name, e)
        return (name, False, str(e))


def phase_wait_poweroff(config, dry_run):
    log.info("=== Phase 3: Wait for Power Off ===")
    idrac_hosts = get_idrac_hosts(config)
    if not idrac_hosts:
        log.warning("No hosts with iDRAC configured, skipping power off monitoring")
        return True

    creds = config["idrac"]
    verify = creds["verify_certs"]
    t = config["timeouts"]
    all_ok = True

    # Poll all hosts in parallel for graceful shutdown completion
    hosts_still_on = []
    with ThreadPoolExecutor(max_workers=len(idrac_hosts)) as pool:
        futures = {
            pool.submit(
                wait_host_poweroff, h, creds, verify,
                t["power_off_poll_interval"], t["power_off_poll_max_attempts"], dry_run
            ): h
            for h in idrac_hosts
        }
        for future in as_completed(futures):
            host = futures[future]
            name, success, msg = future.result()
            if not success:
                hosts_still_on.append(host)

    # Force off any hosts that didn't shut down gracefully
    if hosts_still_on:
        log.info("Force shutting down %d host(s) that did not power off gracefully",
                 len(hosts_still_on))
        with ThreadPoolExecutor(max_workers=len(hosts_still_on)) as pool:
            futures = {
                pool.submit(force_off_host, h, creds, verify, dry_run): h["name"]
                for h in hosts_still_on
            }
            for future in as_completed(futures):
                name, success, msg = future.result()
                if not success:
                    all_ok = False

    return all_ok


# --- Main ---

def parse_args():
    parser = argparse.ArgumentParser(
        description="Power off a bare-metal OpenShift cluster."
    )
    default_env = str(Path(__file__).parent / ".env")
    parser.add_argument(
        "-e", "--env-file", default=default_env,
        help="Path to .env file (default: .env in script directory)",
    )
    parser.add_argument(
        "--phases", default=",".join(ALL_PHASES),
        help="Comma-separated phases to run: drain,shutdown,wait_poweroff (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log actions without executing",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    args = parse_args()
    setup_logging(args.verbose)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    config = load_config(args.env_file)

    phases = [p.strip() for p in args.phases.split(",")]
    for p in phases:
        if p not in ALL_PHASES:
            log.error("Unknown phase: %s (valid: %s)", p, ", ".join(ALL_PHASES))
            sys.exit(1)

    phase_map = {
        "drain": phase_drain,
        "shutdown": phase_shutdown,
        "wait_poweroff": phase_wait_poweroff,
    }

    try:
        for phase_name in ALL_PHASES:
            if phase_name in phases:
                success = phase_map[phase_name](config, args.dry_run)
                if not success and phase_name != "drain":
                    log.error("Phase '%s' failed", phase_name)
                    sys.exit(1)
                elif not success:
                    log.warning("Phase '%s' had issues, continuing with shutdown", phase_name)
        log.info("All phases completed successfully")
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
