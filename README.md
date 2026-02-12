## Lab GitOps Resources

This repo provides a gitops based implementation of my home lab using GitOps

## Installing SealedSecrets

Sensitive secrets in this repo uses Bitnami Sealed Secrets. To install it run the following:

```
oc create -k gitops/manifests/operators/openshift-gitops-operator/overlays/default
```

Then run the following script to replace SS key (key should be located in ~/.bitnami/sealed-secrets-secret.yaml of your workstation or bastion host):

```
./gitops/manifests/operators/openshift-gitops-operator/scripts/replace-sealed-secrets-secret.sh
```

### Provisioning
Clone this or user the raw files url if preferred, then assuming a fresh install of OpenShift run the first command to install the Red Hat GitOps operator:

```
oc create -k gitops/manifests/operators/openshift-gitops-operator/overlays/latest
```

Once the operator is installed, we use the App of Apps pattern to initiate the install of all other operators, including the creation of the pipeline and integration of ACS with the Internal Registry. Notice this might take a while to finish the sync and install everything.

```
oc create -k gitops/manifests/<cluster-name>/bootstrap/stable
```
