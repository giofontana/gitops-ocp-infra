# Home Lab Deployment Procedure

1. Install Local Volume Operator
2. Install ODF Operator
3. Create StorageSystem using Local Volumes
4. Install NMState Operator
5. Create NMState instance
6. Install OpenShift Virt
7. Create HyperConverged instance
8. Install ACM
9. Install ACS
10. Install OpenShift Pipelines
11. Install OpenShift GitOps
12. Create [NodeNetworkConfigurationPolicy](gitops/manifests/my-home-lab/configuration/network/base/nodenetworkconfpolicy.yaml)
13. Create a sample namespace: vm-samples
14. Create NAD:

```yaml
apiVersion: "k8s.cni.cncf.io/v1"
kind: NetworkAttachmentDefinition
metadata:
  name: tuning-bridge-fixed
  namespace: vm-samples
  annotations:
    k8s.v1.cni.cncf.io/resourceName: bridge.network.kubevirt.io/br1
spec:
  config: '{
    "cniVersion": "0.3.1",
    "name": "groot",
    "plugins": [
      {
        "type": "cnv-bridge",
        "bridge": "br1"
      },
      {
        "type": "tuning"
      }
    ]
  }'
```

15. Create a VM on vm-samples to test it.
16. Configure htpasswd
17. Remove kubeadmin: `oc delete secrets kubeadmin -n kube-system`
