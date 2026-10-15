# Revert Screen to the Chromium kiosk
sudo /boot/dietpi/dietpi-autostart 11 && sudo reboot
(Chromium autostart script/index backups: ~/debloat-rollback-20261014/)
# Panel files: ~/ha-minipanel (config.json), supervisor: /var/lib/dietpi/dietpi-autostart/custom.sh, log: /var/log/ha-minipanel.log
# Token: /root/.config/ha-minipanel/token (mode 600)
# v2 -> v1 panel code: see docs/PANEL_DEPLOY_AND_ROLLBACK.md (backup dir ~/ha-minipanel.v1-<date>, config.json.v1)
# Panel-only layout: /root/.config/ha-minipanel/layout.json (+ .bak) - delete to return to default rooms
