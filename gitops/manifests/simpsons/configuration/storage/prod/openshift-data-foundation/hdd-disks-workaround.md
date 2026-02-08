# Workaround for ODF to work with HDD disks.

1. Set config_base variable:

```bash
config=$(cat <<'EOF'
ACTION=="add|change", KERNEL=="sd[a-z]|scini*|nvme[0-9]*", SUBSYSTEM=="block",  ATTR{queue/rotational}="0"
EOF
)
config_base64=$(echo "$config" | base64 -w0)
```

2. Create the MC. Note, it will trigger reboot of all servers.

```bash
cat <<EOF > hdd-disks-workaround.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 99-custom-disk-rotational
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
        - contents:
            source: data:text/plain;charset=utf-8;base64,$config_base64
          mode: 420
          overwrite: true
          path: /etc/udev/rules.d/99-disable-rotational.rules
  osImageURL: ""
EOF
```

3. Apply it:
```
oc apply -f hdd-disks-workaround.yaml
```