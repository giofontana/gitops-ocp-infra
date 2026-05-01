# poweron_cluster

Power on a bare-metal OpenShift cluster via Dell iDRAC Redfish API and restore OCP services.

This script replaces the equivalent Ansible playbook with a standalone Python program. It handles three phases:

1. **Power On** -- Sends power-on commands to Dell servers via iDRAC Redfish (parallel)
2. **Wait for Power On** -- Polls each iDRAC until the server reports `PowerState: On` (parallel, up to 5 min)
3. **Restore OCP Services** -- Waits for the OCP API, uncordons all nodes, and verifies cluster health

## Prerequisites

- Python 3.9+
- `oc` CLI installed and configured with a valid kubeconfig
- Network access to iDRAC management interfaces (Redfish API over HTTPS)

## Setup

```bash
cd python/poweron_cluster

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
| `HOSTS` | Yes | -- | Comma-separated host list (see format below) |
| `POWER_ON_POLL_INTERVAL` | No | `5` | Seconds between power state checks |
| `POWER_ON_POLL_MAX_ATTEMPTS` | No | `60` | Max poll attempts (~5 min with default interval) |
| `OCP_API_RETRY_DELAY` | No | `60` | Seconds between OCP API retries |
| `OCP_API_MAX_RETRIES` | No | `20` | Max OCP API retry attempts |
| `OCP_SETTLE_PAUSE` | No | `60` | Seconds to wait after API is up before uncordoning |

### HOSTS format

Each host entry uses colon-separated fields: `name:host_ip:idrac_ip`

The `idrac_ip` field is optional. Hosts without it are skipped during power operations but still uncordoned in the restore phase.

```
HOSTS=node1:192.168.101.11:192.168.100.11,node2:192.168.101.12:192.168.100.12,node3:192.168.101.13
```

## Usage

```bash
source venv/bin/activate

# Run all phases
./poweron_cluster.py

# Dry run with verbose output
./poweron_cluster.py --dry-run -v

# Run specific phases
./poweron_cluster.py --phases power_on,wait_power
./poweron_cluster.py --phases restore_ocp

# Use a different .env file
./poweron_cluster.py -e /path/to/.env
```

### CLI options

| Option | Description |
|---|---|
| `-e, --env-file` | Path to `.env` file (default: `.env` in script directory) |
| `--phases` | Comma-separated phases: `power_on`, `wait_power`, `restore_ocp` (default: all) |
| `--dry-run` | Log what would happen without making any changes |
| `-v, --verbose` | Enable debug-level logging |

## Phases

### power_on

Sends a Redfish `ComputerSystem.Reset` action with `ResetType: On` to each iDRAC endpoint. Runs in parallel across all hosts. Servers already powered on (HTTP 409) are treated as success.

### wait_power

Polls the Redfish system endpoint on each iDRAC and checks the `PowerState` field. Exits early per host as soon as it reports `On`. Times out after the configured number of attempts.

### restore_ocp

Runs sequentially:

1. Retries `oc get nodes` until the API is reachable
2. Pauses to let the API stabilize
3. Runs `oc adm uncordon` on each node
4. Checks `oc get clusterversion` until the cluster reports `Available: True`
