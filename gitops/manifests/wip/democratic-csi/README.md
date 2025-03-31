
```
oc new-project democratic-csi
oc label --overwrite namespace democratic-csi pod-security.kubernetes.io/enforce=privileged
oc adm policy add-scc-to-user -z zfs-nfs-democratic-csi-node-sa priviledged
oc adm policy add-scc-to-user -z zfs-nfs-democratic-csi-node-sa privileged

helm repo add democratic-csi https://democratic-csi.github.io/charts/
helm repo update
helm search repo democratic-csi/

helm upgrade \
--install \
--values iscsi-values.yaml \
--namespace democratic-csi \
zfs-iscsi democratic-csi/democratic-csi

helm upgrade \
--install \
--values nfs-values.yaml \
--namespace democratic-csi \
zfs-nfs democratic-csi/democratic-csi

oc patch storageprofile truenas-nfs-csi -p '{"spec":{"claimPropertySets":[{"accessModes":["ReadWriteMany"],"volumeMode":"Filesystem"}],"cloneStrategy":"csi-snapshot","dataImportCronSourceFormat":"snapshot","provisioner":"org.democratic-csi.nfs","storageClass":"truenas-nfs-csi"}}' --type=merge

oc patch storageprofile truenas-iscsi-csi -p '{"spec":{"claimPropertySets":[{"accessModes":["ReadWriteMany"],"volumeMode":"Block"},{"accessModes":["ReadWriteOnce"],"volumeMode":"Block"},{"accessModes":["ReadWriteOnce"],"volumeMode":"Filesystem"}],"cloneStrategy":"csi-clone","dataImportCronSourceFormat":"snapshot"}}' --type=merge

helm repo add democratic-csi https://democratic-csi.github.io/charts/
helm repo update

helm upgrade --install --namespace kube-system --create-namespace snapshot-controller democratic-csi/snapshot-controller
kubectl -n kube-system logs -f -l app=snapshot-controller

```
