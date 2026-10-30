#!/bin/bash
# Run on Screen (Pi Zero 2 W), not on the Home Assistant Pi 4.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
APP=/home/braydenchaffee/ha-minipanel
SUPERVISOR=/var/lib/dietpi/dietpi-autostart/custom.sh

if [ ! -f "$APP/panel.py" ] || [ ! -f "$APP/config.json" ]; then
  echo "Native Qt panel/config not found at $APP. Refusing to install watcher."
  exit 1
fi
if [ ! -f "$SUPERVISOR" ] || ! grep -Fq "$APP/panel.py" "$SUPERVISOR"; then
  echo "Expected DietPi Qt supervisor not present; inspect current startup before proceeding."
  exit 1
fi
for bin in git /usr/bin/python3 systemctl; do
  command -v "$bin" >/dev/null || { echo "Missing prerequisite: $bin"; exit 1; }
done
/usr/bin/python3 -c "import PyQt5.QtWidgets" || {
  echo "Install python3-pyqt5 (system Python) first."; exit 1;
}
install -m 0755 "$HERE/panel-update.py" /usr/local/sbin/ha-minipanel-update
install -m 0644 "$HERE/ha-minipanel-update.service" /etc/systemd/system/
install -m 0644 "$HERE/ha-minipanel-update.timer" /etc/systemd/system/
install -d -m 0700 /var/lib/ha-minipanel-updater
systemctl daemon-reload
systemctl enable --now ha-minipanel-update.timer
echo "Installed pull-only native panel watcher. First scan begins after boot/timer schedule."
echo "Check: systemctl list-timers ha-minipanel-update.timer"
echo "Logs:  journalctl -u ha-minipanel-update.service -n 80 --no-pager"
echo "Run now (after checking screen): sudo systemctl start ha-minipanel-update.service"
