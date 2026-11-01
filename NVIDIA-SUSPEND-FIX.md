# Razer laptop suspend/resume fix

Goal: lid close sleeps, lid open resumes cleanly (no suspend loop, no hard reboot, data drive survives).

Status: **resolved** (2026-11-01). Tested on CachyOS, kernel 7.3.1-1-cachyos, KDE Plasma 6 Wayland, nvidia-open 615.78.08, Limine bootloader.

## Problems and causes

| Problem | Cause | Fix |
|---|---|---|
| Suspend/resume loop, then hard reboot | NVIDIA suspend support not configured (services disabled, video memory not preserved) | Step 1 |
| Firmware bounces straight back out of S3 (wakes within ~1 ms), second suspend never returns | Razer firmware (last updated 2022) has a broken S3 (`deep`) path | Step 2 (use s2idle) |
| Second NVMe (`/home/mscattergood/data`, btrfs) vanishes on resume: `pcieport 0000:00:06.0: broken device, retraining non-functional downstream link`, `nvme1: Disabling device after reset failure`, `BTRFS: device has gone missing` | PCIe link to the data drive fails to retrain after sleep | Step 3 |

## 1. NVIDIA suspend services

```
echo 'options nvidia NVreg_PreserveVideoMemoryAllocations=1 NVreg_TemporaryFilePath=/var/tmp' | sudo tee /etc/modprobe.d/nvidia-power.conf
sudo systemctl enable nvidia-suspend.service nvidia-resume.service nvidia-hibernate.service
sudo mkinitcpio -P
```

Verify after reboot:

```
grep -iE "PreserveVideoMemory|TemporaryFilePath" /proc/driver/nvidia/params
systemctl is-enabled nvidia-suspend nvidia-resume nvidia-hibernate
```

Expected: `PreserveVideoMemoryAllocations: 1`, `TemporaryFilePath: "/var/tmp"`, and `enabled` x3.

## 2. Use s2idle instead of S3 (persistent)

Try it at runtime first:

```
echo s2idle | sudo tee /sys/power/mem_sleep
```

Make it persistent:

```
echo 'w /sys/power/mem_sleep - - - - s2idle' | sudo tee /etc/tmpfiles.d/s2idle.conf
```

Verify after reboot: `cat /sys/power/mem_sleep` should show `[s2idle] deep`.

Side effects: opening the lid now wakes the laptop automatically (no keypress needed), and sleep battery drain is somewhat higher than S3.

## 3. Keep the data NVMe alive across sleep

Append these to the kernel command line in `/etc/default/limine` (the `KERNEL_CMDLINE[default]+=` line):

```
pcie_aspm=off pcie_port_pm=off nvme_core.default_ps_max_latency_us=0
```

Then:

```
sudo cp /etc/default/limine /etc/default/limine.bak   # before editing
sudo limine-update
```

Reboot and verify:

```
cat /proc/cmdline
lsblk -f | grep -A1 nvme1
```

After a short suspend test, `lsblk -f` should still show the data drive mounted.

Note: a runtime ASPM policy change (`/sys/module/pcie_aspm/parameters/policy`) was not enough on its own. The kernel parameters were needed.

## 4. Remove any "never sleep" workaround

If you set one in `~/.config/powerdevilrc` (AutoSuspendAction, LidAction, PowerButtonAction = 0), remove it so lid close sleeps again:

```
rm ~/.config/powerdevilrc
systemctl --user restart plasma-powerdevil.service
```

## 5. Test

Save your work first. Close the lid for about 30 seconds, then open it. Check:

```
journalctl -b --no-pager | grep -E "PM: suspend|Lid|nvidia-(suspend|resume)"
lsblk -f | grep -A1 nvme1
```

## 6. If something breaks later

- After a hard reboot: `journalctl -b -1 --no-pager | grep -iE "suspend|resume|PM:|xhci|nvidia|nvme|pcieport" | tail -100`
- Spurious wake sources: `cat /proc/acpi/wakeup` (XHCI, TXHC, TDM0/1 enabled), Bluetooth mouse (MX Anywhere 2S). Toggle with `echo NAME | sudo tee /proc/acpi/wakeup` (it toggles).
- Excess sleep battery drain: try `pcie_port_pm=off` alone, or revert to the previous `/etc/default/limine.bak`.
- If the data drive still drops: unmount it before sleep and remount after with a systemd sleep hook.
- Try the LTS kernel (`linux-cachyos-lts`).
