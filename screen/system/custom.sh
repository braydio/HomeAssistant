#!/bin/bash
# Native Qt Home Panel supervisor. Revert to Chromium: sudo dietpi-autostart 11 && sudo reboot
PANEL=/home/braydenchaffee/ha-minipanel/panel.py
LOG=/var/log/ha-minipanel.log
for i in $(seq 40); do ip route | grep -q default && break; sleep 1; done
fails=0
while true; do
  start=$(date +%s)
  xinit /usr/bin/python3 "$PANEL" -- :0 vt1 -nolisten tcp >>"$LOG" 2>&1
  up=$(( $(date +%s) - start ))
  if [ "$up" -ge 60 ]; then fails=0; else fails=$((fails+1)); fi
  if [ "$fails" -ge 5 ]; then echo "$(date) panel failed 5x quickly, giving up (SSH still available)" >>"$LOG"; exit 1; fi
  sleep $(( fails*5 + 3 ))
done
