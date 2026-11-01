# razerctl usage

`razerctl` controls the power mode and fans of the Razer Blade 15 Advanced (2021, RZ09-0409, USB `1532:0276`) by talking to the embedded controller (EC) over hidraw. A companion daemon, `razerctld`, keeps the Razer power mode in sync with your desktop power profile and runs a temperature-driven fan curve.

For protocol details see [PROTOCOL.md](PROTOCOL.md).

## Install

```sh
sudo ./install.sh              # install or upgrade
sudo ./install.sh --uninstall  # remove (keeps /etc/razerctl)
```

The installer:

- copies the package to `/usr/local/lib/razerctl` and a wrapper to `/usr/local/bin/razerctl`
- installs `/etc/razerctl/config.toml` (an existing one is never overwritten)
- installs the udev rules in `/etc/udev/rules.d/` (hidraw access for the logged-in user, touchpad wake fix)
- installs, enables and starts `razerctld.service`

Requirements: Python 3, PyGObject (`gi`) for the daemon, and `power-profiles-daemon` for profile syncing.

To run from a checkout without installing, use `bin/razerctl` (same arguments). You still need the udev rule for hidraw access.

## Commands

```
razerctl status
razerctl mode {balanced|gaming|creator|silent}
razerctl fan {auto|<rpm>}
```

### `status`

Prints the current state:

```
power mode : balanced (zone2: balanced)
fan control: automatic  (RPM is not readable on this model)
boost      : cpu=1 gpu=1
temps      : cpu=52C  gpu=n/a (asleep)
desktop    : power profile=balanced, razerctld=active
```

- **fan control** is `MANUAL` when the EC has been told to hold a fixed RPM, otherwise `automatic`. The actual fan speed cannot be read; use temperatures as feedback.
- **gpu** shows `n/a (asleep)` when the NVIDIA GPU is runtime-suspended. `status` does not wake it.
- The **desktop** line shows the `powerprofilesctl` profile and the `razerctld` service state.

### `mode <name>`

Sets the Razer power mode, then prints `status`.

| Name | Notes |
|---|---|
| `balanced` | Default |
| `gaming` | Higher power budget; can exceed what the cooling absorbs |
| `creator` | Accepted by the EC; not exercised on the test unit |
| `silent` | Accepted by the EC; not exercised on the test unit |

Setting a mode returns the fans to EC automatic control. The `custom` mode (boost levels) is not exposed.

### `fan auto` / `fan <rpm>`

- `razerctl fan auto` hands fan control back to the EC.
- `razerctl fan 4500` holds the fans at a manual RPM. Values are clamped to **3500-5000** and the applied value is printed.

A manual setting is also cleared by the next `mode` change. Manual fan speed is refused in custom mode.

## Interaction with the daemon

While `razerctld` is running with `curve_enabled = true`, it reasserts the fan state on its next poll (every `poll_seconds`), so a manual `razerctl fan <rpm>` is overridden within a few seconds. Likewise it moves the power mode back to match the desktop power profile. To control things by hand:

```sh
sudo systemctl stop razerctld     # fans are returned to automatic on stop
razerctl mode gaming
razerctl fan 5000
...
sudo systemctl start razerctld    # resume automatic management
```

Alternatively set `curve_enabled = false` in the config to stop the daemon from touching fans while still following the power profile.

## The daemon (`razerctld`)

Each tick the daemon:

1. Maps the active power-profiles-daemon profile to a Razer mode (`[profile_map]`) and applies it if different. It also reacts immediately to profile changes.
2. Takes the temperature `max(CPU package, GPU)` and picks a fan RPM from the curve.
3. Applies that RPM, or EC automatic control below the first curve point. It re-applies if the EC loses a manual setting (for example after resume).

On any stop (clean, crash or kill) `ExecStopPost` runs `razerctl fan auto`, so fans are never left stuck on manual. After 10 consecutive failures the daemon exits.

Service management and logs:

```sh
systemctl status razerctld
sudo systemctl restart razerctld
journalctl -u razerctld -f
```

Dry run (logs decisions, writes nothing; run as a normal user from the repo):

```sh
PYTHONPATH=. python3 -m razerctl.daemon --config config/razerctl.toml --dry-run
```

## Configuration

`/etc/razerctl/config.toml` (restart the daemon after editing: `sudo systemctl restart razerctld`).

| Key | Default | Meaning |
|---|---|---|
| `poll_seconds` | `2` | Seconds between control ticks |
| `hysteresis` | `5` | Degrees C below a threshold before that fan level releases |
| `curve_enabled` | `true` | `false` = never touch fans; only follow the power profile |
| `curve` | `[[75, 3500], [82, 4200], [88, 5000]]` | List of `[temp_C, rpm]`, ascending. RPM must be 3500-5000 |
| `[profile_map]` | see below | Desktop profile -> Razer mode number |

Curve behavior: below the first temperature the EC's own automatic control is used. A level engages when the temperature reaches its threshold and releases when it falls below `threshold - hysteresis`. With the defaults, fans go to 3500 RPM at 75C, 4200 at 82C, 5000 at 88C, and step down at 70C, 77C and 83C respectively.

Default profile map (modes: 0 balanced, 1 gaming, 2 creator, 3 silent):

```toml
[profile_map]
power-saver = 3
balanced    = 0
performance = 1
```

Change the profile with `powerprofilesctl set performance` or the KDE/GNOME power menu.

## Troubleshooting

- **`no permission on hidraw: install the udev rule`** (exit code 2): the udev rule grants access to the active session user via `uaccess`. Run `sudo ./install.sh`, or reload with `sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw`, then log out and in if needed. The rule file must sort before `73-seat-late.rules`.
- **`error: ...`** (exit code 1): the EC rejected a command or the device could not be opened (for example, wrong model). Only `1532:0276` is matched.
- **Manual fan setting keeps reverting**: the daemon is overriding it; see "Interaction with the daemon".
- **Fans stay loud or stuck**: run `razerctl fan auto` and check `razerctl status`.
- **CPU still hits ~97C in gaming mode**: this is expected under sustained 8-core load, because the power budget exceeds cooling capacity. Use `balanced` for sustained loads.

## Lighting setup (OpenRazer)

The GUI's keyboard and logo lighting controls use the OpenRazer daemon. OpenRazer does not provide fan or power control, so those still go through razerctl.

One-time setup:

```sh
sudo pacman -S openrazer-daemon openrazer-driver-dkms python-openrazer
sudo gpasswd -a $USER openrazer     # group is "openrazer" on Arch, not "plugdev"
```

Then log out and back in (or reboot). After that:

```sh
groups | tr ' ' '\n' | grep -x openrazer   # must print "openrazer"
getent group openrazer                      # must list your username
lsmod | grep razer                          # driver loaded; if empty: sudo modprobe razerkbd
systemctl --user enable --now openrazer-daemon
journalctl --user -u openrazer-daemon -n 30
razerctl status                             # EC control should still work
bin/razerctl-gui                            # test power mode, fan, keyboard effects, logo
```

If the logo controls are missing or behave oddly, inspect what the daemon exposes:

```sh
gdbus introspect --session -d org.razer -o /org/razer/device/<serial>
```

Troubleshooting:

- **Daemon fails with `User is not a member of the openrazer group`**: the group add did not take effect. Run `sudo gpasswd -a $USER openrazer` (if `getent group openrazer` shows nothing, run `sudo groupadd openrazer` first), then log out and in.
- **Lighting section is empty in the GUI**: the daemon is not running or no device was found; check `systemctl --user status openrazer-daemon`.
