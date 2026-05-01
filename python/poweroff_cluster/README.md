# poweroff_cluster

Power off a bare-metal OpenShift cluster: drain nodes, graceful shutdown via iDRAC Redfish or SSH, and force off if needed.

This script replaces the equivalent Ansible playbook with a standalone Python program. It handles three phases:

1. **Drain** -- Drains all OCP nodes in parallel (`oc adm drain`)
2. **Shutdown** -- Sends graceful shutdown via iDRAC Redfish or SSH fallback (parallel)
3. **Wait for Power Off** -- Polls iDRAC until servers report `PowerState: Off`, then force-powers-off any that didn't shut down gracefully

## Prerequisites

- Python 3.9+
- `oc` CLI installed and configured with a valid kubeconfig
- Network access to iDRAC management interfaces (Redfish API over HTTPS)
- SSH access to nodes without iDRAC (user `core`, key-based auth)

## Setup

```bash
cd python/poweroff_cluster

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the sample environment file and edit it with your values:

```bash
cp .env.sample .env
```

### .env variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `IDRAC_USERNAME` | Yes | -- | iDRAC login username |
| `IDRAC_PASSWORD` | Yes | -- | iDRAC login password |
| `IDRAC_VERIFY_CERTS` | No | `false` | Set to `true` to verify iDRAC TLS certificates |
| `SSH_USER` | No | `core` | SSH user for nodes without iDRAC |
| `SSH_KEY` | No | -- | Path to SSH private key for non-iDRAC nodes |
| `HOSTS` | Yes | -- | Comma-separated host list (see format below) |
| `DRAIN_TIMEOUT` | No | `60` | Seconds for `oc adm drain` timeout per node |
| `POWER_OFF_POLL_INTERVAL` | No | `30` | Seconds between power state checks |
| `POWER_OFF_POLL_MAX_ATTEMPTS` | No | `30` | Max poll attempts (~15 min with default interval) |

### HOSTS format

Each host entry uses colon-separated fields: `name:host_ip:idrac_ip`

The `idrac_ip` field is optional. Hosts without it use SSH for shutdown instead of iDRAC Redfish.

```
HOSTS=node1:192.168.101.11:192.168.100.11,node2:192.168.101.12:192.168.100.12,node3:192.168.101.13
```

## Usage

```bash
source venv/bin/activate

# Run all phases
./poweroff_cluster.py

# Dry run with verbose output
./poweroff_cluster.py --dry-run -v

# Run specific phases
./poweroff_cluster.py --phases drain,shutdown
./poweroff_cluster.py --phases wait_poweroff

# Use a different .env file
./poweroff_cluster.py -e /path/to/.env
```

### CLI options

| Option | Description |
|---|---|
| `-e, --env-file` | Path to `.env` file (default: `.env` in script directory) |
| `--phases` | Comma-separated phases: `drain`, `shutdown`, `wait_poweroff` (default: all) |
| `--dry-run` | Log what would happen without making any changes |
| `-v, --verbose` | Enable debug-level logging |

## Phases

### drain

Runs `oc adm drain` on every node in parallel with `--ignore-daemonsets`, `--delete-emptydir-data`, `--force`, and `--disable-eviction`. Drain failures are logged as warnings and do not block the shutdown phases.

### shutdown

Sends a graceful shutdown command to each node in parallel:

- **Nodes with iDRAC**: Redfish `ComputerSystem.Reset` with `ResetType: GracefulShutdown`
- **Nodes without iDRAC**: SSH `sudo shutdown -h now`

### wait_poweroff

Polls the Redfish system endpoint on each iDRAC host and checks `PowerState == "Off"`. If a host does not power off within the polling window, a Redfish `ForceOff` command is sent automatically. Only applies to nodes with iDRAC.
