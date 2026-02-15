#!/bin/bash
export disk_id=sdb

sudo wipefs -fa /dev/$disk_id
sudo sgdisk --zap-all /dev/$disk_id
sudo dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=0
sudo dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((1 * 1024**2))
sudo dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((10 * 1024**2))
sudo dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((100 * 1024**2))
sudo dd if=/dev/zero of="/dev/$disk_id" bs=1K count=200 oflag=direct,dsync seek=$((1000 * 1024**2))
```