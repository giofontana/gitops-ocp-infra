#!/bin/bash

# Check if user is logged into OpenShift
if ! oc whoami > /dev/null 2>&1; then
  echo "Error: You are not logged into an OpenShift cluster. Please login using 'oc login' before running this script."
  exit 1
fi

# Check if the user has cluster-admin privileges
if ! oc auth can-i '*' '*' --all-namespaces > /dev/null 2>&1; then
  echo "Error: You do not have cluster-admin privileges. Please log in with a user that has the cluster-admin role."
  exit 1
fi

# Deploy openshift gitops
oc apply -k gitops/manifests/my-home-lab/bootstrap/stable
