#!/usr/bin/env bash

patch_subscription() {
  local SUB_NS="openshift-operators"
  local SUB_NAME="openshift-gitops-operator"
  local ENV_NAME="ARGOCD_CLUSTER_CONFIG_NAMESPACES"
  local NAMESPACE="argocd-workloads"

  echo "Checking current value of ${ENV_NAME} in subscription ${SUB_NAME}..."

  CURRENT=$(oc get subscription "${SUB_NAME}" -n "${SUB_NS}" \
    -o jsonpath="{.spec.config.env[?(@.name==\"${ENV_NAME}\")].value}" 2>/dev/null || true)

  echo "Current value: '${CURRENT}'"

  # Idempotency check
  if echo "${CURRENT}" | grep -qw "${NAMESPACE}"; then
    echo "${NAMESPACE} is already present in ${ENV_NAME}. Nothing to do."
    return 0
  fi

  # Build the new value: append with comma if something already exists
  if [ -z "${CURRENT}" ]; then
    NEW_VALUE="${NAMESPACE}"
  else
    NEW_VALUE="${CURRENT}, ${NAMESPACE}"
  fi

  echo "New value will be: '${NEW_VALUE}'"

  # Check if the ARGOCD_CLUSTER_CONFIG_NAMESPACES entry already exists in the env array
  ENV_ENTRIES=$(oc get subscription "${SUB_NAME}" -n "${SUB_NS}" \
    -o jsonpath="{range .spec.config.env[*]}{.name}{'\n'}{end}" 2>/dev/null || true)

  if echo "${ENV_ENTRIES}" | grep -q "^${ENV_NAME}$"; then
    # Entry exists — find its index and replace the value
    INDEX=0
    while IFS= read -r name; do
      [ "${name}" = "${ENV_NAME}" ] && break
      INDEX=$((INDEX + 1))
    done <<< "${ENV_ENTRIES}"

    echo "Replacing existing entry at index ${INDEX}..."
    oc patch subscription "${SUB_NAME}" -n "${SUB_NS}" --type=json \
      -p "[{\"op\":\"replace\",\"path\":\"/spec/config/env/${INDEX}/value\",\"value\":\"${NEW_VALUE}\"}]"
  else
    # Entry does not exist — check if the env array itself exists
    HAS_ENV=$(oc get subscription "${SUB_NAME}" -n "${SUB_NS}" \
      -o jsonpath="{.spec.config.env}" 2>/dev/null || true)

    if [ -n "${HAS_ENV}" ] && [ "${HAS_ENV}" != "null" ]; then
      echo "Appending new entry to existing env array..."
      oc patch subscription "${SUB_NAME}" -n "${SUB_NS}" --type=json \
        -p "[{\"op\":\"add\",\"path\":\"/spec/config/env/-\",\"value\":{\"name\":\"${ENV_NAME}\",\"value\":\"${NEW_VALUE}\"}}]"
    else
      echo "Creating spec.config.env array with new entry..."
      oc patch subscription "${SUB_NAME}" -n "${SUB_NS}" --type=merge \
        -p "{\"spec\":{\"config\":{\"env\":[{\"name\":\"${ENV_NAME}\",\"value\":\"${NEW_VALUE}\"}]}}}"
    fi
  fi

  echo "Successfully updated ${ENV_NAME} to: '${NEW_VALUE}'"
}

patch_subscription
