To wipe disks for ODF:

```
disk_id=sdb

wipefs -fa /dev/$disk_id
sgdisk --zap-all /dev/$disk_id
dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=0
dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((1 * 1024**2))
dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((10 * 1024**2))
dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((100 * 1024**2))
dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((1000 * 1024**2))
```