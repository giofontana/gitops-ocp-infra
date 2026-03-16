# Frigate - Network Video Recorder (NVR)

Frigate is an open-source NVR built around real-time AI object detection. It uses OpenCV and Tensorflow to perform object detection on camera feeds.

**Homepage:** https://frigate.video/
**GitHub:** https://github.com/blakeblackshear/frigate

## Overview

This directory contains the Kustomize manifests for deploying Frigate as a workload in the OpenShift cluster.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frigate Deployment                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Camera     │  │   Object     │  │  Recording   │  │
│  │   Streams    │──│  Detection   │──│   Storage    │  │
│  │   (RTSP)     │  │   (AI/ML)    │  │   (PVC)      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
   ┌───────────────┐                   ┌────────────────┐
   │   Route       │                   │  Media Storage │
   │ (TLS/HTTPS)   │                   │    (NFS PV)    │
   └───────────────┘                   └────────────────┘
```

## Directory Structure

```
frigate/
├── README.md                    # This file
├── base/                        # Base configuration (shared)
│   ├── kustomization.yaml       # Base kustomization
│   ├── namespace.yaml           # frigate namespace
│   ├── config-secret-sealed.yaml # Frigate configuration (sealed)
│   ├── db-pvc.yaml              # Database persistent storage
│   ├── media-pv.yaml            # Media persistent volume (NFS)
│   ├── media-pvc.yaml           # Media persistent volume claim
│   ├── rolebinding.yaml         # RBAC permissions
│   ├── route.yaml               # OpenShift route (frigate.gfontana.me)
│   ├── service.yaml             # Kubernetes service
│   └── sa.yaml                  # Service account
└── overlays/                    # Deployment variants
    ├── cpu/                     # CPU-only deployment
    │   ├── kustomization.yaml
    │   └── deployment.yaml      # CPU-optimized deployment
    └── nvidia/                  # NVIDIA GPU deployment
        ├── kustomization.yaml
        └── deployment.yaml      # GPU-accelerated deployment
```

## Deployment Overlays

### CPU Overlay (`overlays/cpu`)
- **Use case:** Standard deployment without GPU acceleration
- **Features:**
  - CPU-based object detection
  - Lower resource requirements
  - Suitable for basic monitoring setups

### NVIDIA Overlay (`overlays/nvidia`)
- **Use case:** High-performance deployment with GPU acceleration
- **Features:**
  - GPU-accelerated object detection
  - Better performance for multiple camera streams
  - Requires NVIDIA GPU operator

## Certificate Management

**As of March 2026:** Frigate uses **cert-manager** for automated TLS certificate management.

### Certificate Details
- **Domain:** `frigate.gfontana.me`
- **Issuer:** Let's Encrypt Production (via ClusterIssuer)
- **Secret Name:** `frigate-certs` (in `frigate` namespace)
- **Auto-renewal:** 30 days before expiry
- **Certificate Keys:**
  - `tls.crt` (mapped to `fullchain.pem`)
  - `tls.key` (mapped to `privkey.pem`)

### Certificate Configuration Location
The Certificate resource is cluster-specific and located at:
```
clusters/simpsons/configuration/frigate-certs/certificate-frigate.yaml
```

This follows the GitOps layered pattern where:
- **Base workload:** Shared deployment configuration
- **Cluster config:** Cluster-specific resources (like certificates)

## Storage

### Database Storage
- **Type:** PersistentVolumeClaim (ReadWriteOnce)
- **Purpose:** SQLite database and configuration
- **Mount Path:** `/config`

### Media Storage
- **Type:** NFS PersistentVolume
- **Purpose:** Video recordings and snapshots
- **Mount Path:** `/media`

### Cache Storage
- **Type:** EmptyDir (Memory)
- **Purpose:** Temporary processing cache
- **Size:** 1Gi

### Shared Memory
- **Type:** EmptyDir (Memory)
- **Purpose:** Shared memory for video processing
- **Size:** 384Mi

## Network Configuration

### Service Ports
- **5000:** Web UI (HTTPS)
- **8971:** Internal API
- **8554:** RTSP stream server (TCP)
- **8555:** WebRTC stream (TCP/UDP)
- **1935:** RTMP stream
- **554:** RTSP auxiliary port

### Route
- **Host:** `frigate.gfontana.me`
- **TLS Termination:** Passthrough (application handles TLS)
- **Insecure Traffic:** Redirected to HTTPS

## Configuration

### Application Configuration
The Frigate application configuration is stored as a sealed secret:
```
base/config-secret-sealed.yaml
```

This contains `config.yaml` which defines:
- Camera configurations
- Object detection settings
- Recording rules
- Notification settings

### RTSP Password
Set via environment variable in deployment:
```yaml
env:
- name: FRIGATE_RTSP_PASSWORD
  value: "password"  # Change in production!
```

**⚠️ Security Note:** This should be moved to a sealed secret in production.

## Deployment to Clusters

Frigate is currently deployed to the **simpsons** cluster via the cluster-specific aggregate:

```
clusters/simpsons/aggregate/workloads/frigate/kustomization.yaml
```

This aggregate includes:
1. **Certificate configuration** (from `clusters/simpsons/configuration/frigate-certs/`)
2. **Workload deployment** (from `workloads/frigate/overlays/cpu/`)
3. **Certificate key mapping patch** (to map cert-manager keys to Let's Encrypt format)

### Sync Waves
- **Wave 4:** Certificate resource creation (cert-manager issues certificate)
- **Wave 5:** Frigate deployment (uses issued certificate)

## Making Changes

### Updating Frigate Configuration

1. **Decrypt the existing sealed secret:**
   ```bash
   # Get the current sealed secret
   oc get sealedsecret frigate-config-secret -n frigate -o yaml > config-sealed.yaml
   ```

2. **Create new configuration:**
   ```bash
   # Create unsealed secret with new config
   kubectl create secret generic frigate-config-secret \
     --from-file=config.yaml=./my-new-config.yaml \
     --dry-run=client -o yaml > config-unsealed.yaml
   ```

3. **Seal the new secret:**
   ```bash
   kubeseal --format=yaml < config-unsealed.yaml > config-secret-sealed.yaml
   ```

4. **Update in Git:**
   ```bash
   mv config-secret-sealed.yaml base/config-secret-sealed.yaml
   git add base/config-secret-sealed.yaml
   git commit -m "Update Frigate configuration"
   git push
   ```

### Switching Between CPU and GPU Deployment

Edit the aggregate kustomization to point to the desired overlay:

```yaml
# clusters/simpsons/aggregate/workloads/frigate/kustomization.yaml
resources:
  - ../../../configuration/frigate-certs
  - ../../../../../workloads/frigate/overlays/nvidia  # Change cpu to nvidia
```

### Updating Container Image

The image is defined in the overlay deployment files:
```yaml
# overlays/cpu/deployment.yaml or overlays/nvidia/deployment.yaml
containers:
- name: frigate
  image: ghcr.io/blakeblackshear/frigate:stable  # Update tag here
```

## Accessing Frigate

### Web UI
- **URL:** https://frigate.gfontana.me
- **Protocol:** HTTPS (TLS via cert-manager)

### RTSP Streams
- **Base URL:** `rtsp://frigate.gfontana.me:8554/`
- **Authentication:** Uses FRIGATE_RTSP_PASSWORD

### API
- **Base URL:** https://frigate.gfontana.me/api/

## Troubleshooting

### Check Pod Status
```bash
oc get pods -n frigate
oc logs -n frigate deployment/frigate
```

### Check Certificate Status
```bash
# Verify certificate is ready
oc get certificate frigate-cert -n frigate

# Check certificate details
oc describe certificate frigate-cert -n frigate

# Verify secret exists
oc get secret frigate-certs -n frigate
```

### Check Storage
```bash
# Verify PVCs are bound
oc get pvc -n frigate

# Check PV status
oc get pv | grep frigate
```

### Check Route
```bash
# Verify route is configured
oc get route -n frigate

# Test TLS certificate from outside
echo | openssl s_client -connect frigate.gfontana.me:443 -servername frigate.gfontana.me 2>/dev/null | openssl x509 -noout -dates -issuer
```

### Common Issues

**Issue:** Certificate not being issued
**Solution:** Check ClusterIssuer status and DNS configuration
```bash
oc get clusterissuer letsencrypt-prod
oc describe certificate frigate-cert -n frigate
```

**Issue:** Pod fails to start
**Solution:** Check storage permissions and resource availability
```bash
oc describe pod -n frigate
oc get events -n frigate --sort-by='.lastTimestamp'
```

**Issue:** Can't access web UI
**Solution:** Verify route and certificate are working
```bash
oc get route frigate-web -n frigate
curl -I https://frigate.gfontana.me
```

## Security Considerations

1. **TLS Certificates:** Managed by cert-manager with Let's Encrypt
2. **Sealed Secrets:** Application configuration encrypted in Git
3. **RBAC:** Service account with minimal required permissions
4. **Network Policy:** Consider adding network policies to restrict traffic
5. **RTSP Password:** Should be moved to a sealed secret

## Maintenance

### Certificate Renewal
- **Automatic:** cert-manager handles renewal 30 days before expiry
- **Manual Check:**
  ```bash
  oc get certificate frigate-cert -n frigate -o jsonpath='{.status.renewalTime}'
  ```

### Backup Recommendations
1. **Database:** Backup `/config` PVC regularly
2. **Recordings:** Backup `/media` PV if critical
3. **Configuration:** Sealed secret is in Git (already backed up)

### Updates
- Monitor Frigate releases: https://github.com/blakeblackshear/frigate/releases
- Test updates in non-production environment first
- Review breaking changes in release notes

## References

- **Frigate Documentation:** https://docs.frigate.video/
- **cert-manager Documentation:** https://cert-manager.io/
- **OpenShift Documentation:** https://docs.openshift.com/
- **Kustomize Documentation:** https://kustomize.io/

## Migration History

### March 2026: cert-manager Migration
- **Previous:** Manual certificate management via sealed secrets
- **Current:** Automated renewal via cert-manager
- **Benefits:**
  - No manual intervention required
  - Automatic renewal 30 days before expiry
  - Consistent certificate management across cluster
  - Reduced operational overhead
