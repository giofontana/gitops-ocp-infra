#!/bin/bash

MACHINENETWORKCIDR="10.1.0.0/16"
PULLSECRET=""
SSHPUBKEY=""

cat <<EOF > install-config.yaml
apiVersion: v1
baseDomain: test.example.com
compute:
- architecture: amd64 
  hyperthreading: Enabled
  name: worker
  replicas: 0
controlPlane:
  architecture: amd64
  hyperthreading: Enabled
  name: master
  replicas: 1
metadata:
  name: sno-cluster 
networking:
  clusterNetwork:
  - cidr: 10.128.0.0/14
    hostPrefix: 23
  machineNetwork:
  - cidr: ${MACHINENETWORKCIDR}
  networkType: OVNKubernetes 
  serviceNetwork:
  - 172.30.0.0/16
platform:
  none: {}
pullSecret: '${PULLSECRET}'
sshKey: |
  '${SSHPUBKEY}'
EOF

MACADDR=$(echo $FQDN|md5sum|sed 's/^\(..\)\(..\)\(..\)\(..\)\(..\).*$/02:\1:\2:\3:\4:\5/')
SERVERIP="10.1.100.100"
DNSRESOLVER="10.1.0.1"
GATEWAY="10.1.0.1"

cat > agent-config.yaml << EOF
apiVersion: v1alpha1
kind: AgentConfig
metadata:
  name: sno-cluster
hosts: 
  - hostname: master-0 
    interfaces:
      - name: enp1s0
        macAddress: ${MACADDR}
    rootDeviceHints: 
      deviceName: /dev/vdb
    networkConfig: 
      interfaces:
        - name: enp1s0
          type: ethernet
          state: up
          mac-address: ${MACADDR}
          ipv4:
            enabled: true
            address:
              - ip: ${SERVERIP}
                prefix-length: 16
            dhcp: false
      dns-resolver:
        config:
          server:
            - ${DNSRESOLVER}
      routes:
        config:
          - destination: 0.0.0.0/0
            next-hop-address: ${GATEWAY}
            next-hop-interface: enp1s0
            table-id: 254
EOF

oc new-project ocp2
virtctl image-upload dv ocp-iso --size=30Gi --image-path=install/agent.x86_64.iso
oc apply -f virtual-machine.yaml
virtctl start ocp2