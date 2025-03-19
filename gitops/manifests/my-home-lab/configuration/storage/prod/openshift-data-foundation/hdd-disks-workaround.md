# Workaround for ODF to work with HDD disks. Only works with:

1. Change the script below setting the appropriate ODF node names and disks wwn:

```bash
#!/bin/bash

# Get the hostname of the machine
HOSTNAME=$(hostname)

# Define the disk WWN based on the hostname
case "$HOSTNAME" in
    "marge.simpsons.lab.gfontana.me")
        DISK_WWN="wwn-0x644a84202ca9cf002f5c702849484052"
        ;;
    "bart.simpsons.lab.gfontana.me")
        DISK_WWN="wwn-0x61866da063b4c9002e9c3f2023019681"
        ;;
    "homer.simpsons.lab.gfontana.me")
        DISK_WWN="wwn-0x61866da062ba8a002e9c435a0f77c154"
        ;;
    *)
        echo "Hostname not recognized. Exiting."
        exit 1
        ;;
esac

# Find the corresponding disk device
DISK_ID=$(readlink -f "/dev/disk/by-id/$DISK_WWN" | awk -F'/' '{print $NF}')

if [ -n "$DISK_ID" ]; then
    echo "Setting rotational value to 0 for $DISK_ID"
    sudo bash -c "echo 0 > /sys/block/${DISK_ID}/queue/rotational"
else
    echo "Disk not found for WWN: $DISK_WWN"
    exit 1
fi
```

2. Encode it with base 64:

```
config_base64=$(cat script.sh | base64 -w0)
```

3. Create the MC:

```
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
          mode: 493
          overwrite: true
          path: /usr/local/bin/set-disk-rotational.sh
    systemd:
      units:
        - contents: |
            [Unit]
            Description=Set Disk Rotational Attribute
            After=network-online.target
            Wants=network-online.target

            [Service]
            Type=oneshot
            ExecStart=/usr/local/bin/set-disk-rotational.sh
            RemainAfterExit=true

            [Install]
            WantedBy=multi-user.target
          enabled: true
          name: set-disk-rotational.service
EOF
```
