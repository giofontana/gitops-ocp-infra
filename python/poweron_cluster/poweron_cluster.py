#!/usr/bin/env python3
"""Power on a bare-metal OpenShift cluster via iDRAC Redfish and restore OCP services."""

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
ALL_PHASES = ["power_on", "wait_power", "restore_ocp"]

log = logging.getLogger(__name__)


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
        "hosts": parse_hosts(hosts_str),
        "timeouts": {
            "power_on_poll_interval": int(os.getenv("POWER_ON_POLL_INTERVAL", "5")),
            "power_on_poll_max_attempts": int(os.getenv("POWER_ON_POLL_MAX_ATTEMPTS", "60")),
            "ocp_api_retry_delay": int(os.getenv("OCP_API_RETRY_DELAY", "60")),
            "ocp_api_max_retries": int(os.getenv("OCP_API_MAX_RETRIES", "20")),
            "ocp_settle_pause": int(os.getenv("OCP_SETTLE_PAUSE", "60")),
        },
    }


def get_idrac_hosts(config):
    return [h for h in config["hosts"] if "idrac_host" in h]


def get_all_hostnames(config):
    return [h["name"] for h in config["hosts"]]


# --- Phase 1: Power On ---

def power_on_host(host, idrac_creds, verify_certs, dry_run):
    name = host["name"]
    idrac = host["idrac_host"]
    url = f"https://{idrac}{REDFISH_RESET_PATH}"

    if dry_run:
        log.info("[DRY RUN] Would power on %s via %s", name, url)
        return (name, True, "dry run")

    try:
        resp = requests.post(
            url,
            json={"ResetType": "On"},
            auth=(idrac_creds["username"], idrac_creds["password"]),
            verify=verify_certs,
            timeout=30,
        )
        if resp.status_code == 409:
            log.warning("%s: already powered on", name)
            return (name, True, "already on")
        resp.raise_for_status()
        log.info("%s: power on command sent", name)
        return (name, True, "power on sent")
    except requests.RequestException as e:
        log.error("%s: failed to power on: %s", name, e)
        return (name, False, str(e))


def phase_power_on(config, dry_run):
    log.info("=== Phase 1: Power On BM Nodes ===")
    hosts = get_idrac_hosts(config)
    if not hosts:
        log.warning("No hosts with iDRAC configured, skipping power on")
        return True

    creds = config["idrac"]
    verify = creds["verify_certs"]
    all_ok = True

    with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {
            pool.submit(power_on_host, h, creds, verify, dry_run): h["name"]
            for h in hosts
        }
        for future in as_completed(futures):
            name, success, msg = future.result()
            if not success:
                all_ok = False

    return all_ok


# --- Phase 2: Wait for Power On ---

def wait_host_power_on(host, idrac_creds, verify_certs, poll_interval, max_attempts, dry_run):
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
                if power_state == "On":
                    log.info("%s: powered on", name)
                    return (name, True, "powered on")
        except requests.RequestException as e:
            log.debug("%s: unreachable (%s), attempt %d", name, e, attempt)

        if attempt < max_attempts:
            time.sleep(poll_interval)

    log.error("%s: timed out waiting for power on after %d attempts", name, max_attempts)
    return (name, False, "timed out")


def phase_wait_power(config, dry_run):
    log.info("=== Phase 2: Waiting for Nodes to Power On ===")
    hosts = get_idrac_hosts(config)
    if not hosts:
        log.warning("No hosts with iDRAC configured, skipping wait")
        return True

    creds = config["idrac"]
    verify = creds["verify_certs"]
    t = config["timeouts"]
    all_ok = True

    with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {
            pool.submit(
                wait_host_power_on, h, creds, verify,
                t["power_on_poll_interval"], t["power_on_poll_max_attempts"], dry_run
            ): h["name"]
            for h in hosts
        }
        for future in as_completed(futures):
            name, success, msg = future.result()
            if not success:
                all_ok = False

    return all_ok


# --- Phase 3: Restore OCP Services ---

def run_oc_command(args, retries, delay, dry_run, check_fn=None):
    cmd = ["oc"] + args
    cmd_str = " ".join(cmd)

    if dry_run:
        log.info("[DRY RUN] Would run: %s", cmd_str)
        return (True, "dry run")

    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if check_fn:
                if check_fn(result.stdout):
                    log.info("Command succeeded: %s", cmd_str)
                    return (True, result.stdout)
            elif result.returncode == 0:
                log.info("Command succeeded: %s", cmd_str)
                return (True, result.stdout)

            log.warning(
                "Command failed (attempt %d/%d): %s — rc=%d, stderr=%s",
                attempt, retries, cmd_str, result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
        except subprocess.TimeoutExpired:
            log.warning("Command timed out (attempt %d/%d): %s", attempt, retries, cmd_str)
        except FileNotFoundError:
            log.error("'oc' command not found in PATH")
            return (False, "oc not found")

        if attempt < retries:
            log.info("Retrying in %ds...", delay)
            time.sleep(delay)

    log.error("Command failed after %d attempts: %s", retries, cmd_str)
    return (False, "max retries exceeded")


def phase_restore_ocp(config, dry_run):
    log.info("=== Phase 3: Restore OCP Services ===")
    t = config["timeouts"]
    retries = t["ocp_api_max_retries"]
    delay = t["ocp_api_retry_delay"]

    log.info("Checking OCP API is up...")
    ok, _ = run_oc_command(["get", "nodes"], retries, delay, dry_run)
    if not ok:
        return False

    pause = t["ocp_settle_pause"]
    if dry_run:
        log.info("[DRY RUN] Would pause %ds for API to settle", pause)
    else:
        log.info("Pausing %ds for API to settle...", pause)
        time.sleep(pause)

    for hostname in get_all_hostnames(config):
        log.info("Uncordoning %s...", hostname)
        ok, _ = run_oc_command(["adm", "uncordon", hostname], retries, delay, dry_run)
        if not ok:
            return False

    log.info("Waiting for cluster to be healthy...")
    ok, _ = run_oc_command(
        [
            "get", "clusterversion", "version", "-o",
            'jsonpath={..status.conditions[?(@.type=="Available")].status}',
        ],
        retries, delay, dry_run,
        check_fn=lambda out: out.strip() == "True",
    )
    if not ok:
        return False

    return True


# --- Main ---

def parse_args():
    parser = argparse.ArgumentParser(
        description="Power on a bare-metal OpenShift cluster."
    )
    default_env = str(Path(__file__).parent / ".env")
    parser.add_argument(
        "-e", "--env-file", default=default_env,
        help="Path to .env file (default: .env in script directory)",
    )
    parser.add_argument(
        "--phases", default=",".join(ALL_PHASES),
        help="Comma-separated phases to run: power_on,wait_power,restore_ocp (default: all)",
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
        "power_on": phase_power_on,
        "wait_power": phase_wait_power,
        "restore_ocp": phase_restore_ocp,
    }

    try:
        for phase_name in ALL_PHASES:
            if phase_name in phases:
                if not phase_map[phase_name](config, args.dry_run):
                    log.error("Phase '%s' failed", phase_name)
                    sys.exit(1)
        log.info("All phases completed successfully")
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
