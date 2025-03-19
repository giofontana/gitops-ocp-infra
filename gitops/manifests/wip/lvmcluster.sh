NODE_NAME=$(oc get no -o name)

oc label $NODE_NAME topology.kubernetes.io/lvm-disk=sda

oc apply -f - <<EOF
apiVersion: lvm.topolvm.io/v1alpha1
kind: LVMCluster
metadata:
  name: lvmcluster
  namespace: openshift-storage
spec:
  storage:
    deviceClasses:
      - deviceSelector:
          paths:
            - '/dev/disk/by-path/pci-0000:05:00.0-ata-1.0'
        fstype: xfs
        name: vg1
        nodeSelector:
          nodeSelectorTerms:
            - matchExpressions:
                - key: topology.kubernetes.io/lvm-disk
                  operator: In
                  values:
                    - sda
        thinPoolConfig:
          chunkSizeCalculationPolicy: Static
          metadataSizeCalculationPolicy: Host
          name: thin-pool-1
          overprovisionRatio: 10
          sizePercent: 90
EOF