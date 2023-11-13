## Lab GitOps Resources

This repo provides a gitops based implementation of my home lab using GitOps


### Provisioning
Clone this or user the raw files url if preferred, then assuming a fresh install of OpenShift run the first command to install the Red Hat GitOps operator:

```
oc create -k gitops/manifests/operators/openshift-gitops-operator/overlays/latest
```

Once the operator is installed, we use the App of Apps pattern to initiate the install of all other operators, including the creation of the pipeline and integration of ACS with the Internal Registry. Notice this might take a while to finish the sync and install everything.

```
oc create -k gitops/manifests/my-home-lab/bootstrap/base
```
