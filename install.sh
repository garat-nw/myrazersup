#!/bin/sh
# Usage: sudo ./install.sh            install / upgrade
#        sudo ./install.sh --uninstall
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
if [ "${1:-}" = "--uninstall" ]; then
  systemctl disable --now razerctld 2>/dev/null || true
  rm -f /etc/systemd/system/razerctld.service /usr/local/bin/razerctl /usr/local/bin/razerctl-gui /usr/local/share/applications/razerctl-gui.desktop /etc/udev/rules.d/60-razer-blade.rules /etc/udev/rules.d/61-razer-blade-nowake.rules
  rm -rf /usr/local/lib/razerctl
  systemctl daemon-reload; udevadm control --reload
  echo "uninstalled (config in /etc/razerctl kept)"; exit 0
fi
install -d /usr/local/lib/razerctl /etc/razerctl
rm -rf /usr/local/lib/razerctl/razerctl && cp -r razerctl /usr/local/lib/razerctl/ && find /usr/local/lib/razerctl -name __pycache__ -prune -exec rm -rf {} +
printf '#!/bin/sh\nexec env PYTHONPATH=/usr/local/lib/razerctl python3 -m razerctl "$@"\n' > /usr/local/bin/razerctl
printf '#!/bin/sh\nexec env PYTHONPATH=/usr/local/lib/razerctl python3 -m razerctl.gui "$@"\n' > /usr/local/bin/razerctl-gui
chmod 755 /usr/local/bin/razerctl /usr/local/bin/razerctl-gui
install -D -m 644 desktop/razerctl-gui.desktop /usr/local/share/applications/razerctl-gui.desktop
[ -e /etc/razerctl/config.toml ] || install -m 644 config/razerctl.toml /etc/razerctl/config.toml
install -m 644 udev/60-razer-blade.rules udev/61-razer-blade-nowake.rules /etc/udev/rules.d/
install -m 644 systemd/razerctld.service /etc/systemd/system/
udevadm control --reload; udevadm trigger --subsystem-match=hidraw; udevadm trigger --action=add --subsystem-match=i2c
systemctl daemon-reload
systemctl enable razerctld
systemctl restart razerctld
echo "installed. check: razerctl status ; journalctl -u razerctld -f"
