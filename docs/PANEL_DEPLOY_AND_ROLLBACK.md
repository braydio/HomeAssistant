# Panel v2 – deploy and rollback (Screen = Pi Zero 2 W)

Startup is unchanged from v1: `dietpi-autostart 14` → `/var/lib/dietpi/dietpi-autostart/custom.sh`
(`screen/system/custom.sh`) waits for the default route, then runs `xinit python3 ~/ha-minipanel/panel.py -- :0 vt1 -nolisten tcp`
as root with a back-off restart (gives up after 5 quick failures; log `/var/log/ha-minipanel.log`).
v2 only replaces the files in `~/ha-minipanel`. Chromium and the wait page are still installed as the last-resort fallback.

## Install / update

```bash
# on the dev machine, from screen/ha-minipanel/
python3 -m unittest test_layout_model test_colors test_core test_ha_client   # Qt-free, any machine
tar cf - camera.py colors.py ha_client.py layout_model.py panel.py settings.py state_store.py telemetry.py views.py test_*.py \
  | ssh <screen> 'mkdir -p ~/ha-minipanel-next && tar xf - -C ~/ha-minipanel-next'

# on the Screen: test side-by-side BEFORE touching the running app
cd ~/ha-minipanel-next && python3 -m py_compile *.py
cp ~/ha-minipanel/config.json . ; cp config.example.json config.example.json
QT_QPA_PLATFORM=offscreen python3 -m unittest test_ui_offscreen       # needs python3-pyqt5, which the panel already uses

# deploy: keep a copy, swap files, restart only the panel
cp -a ~/ha-minipanel ~/ha-minipanel.v1-$(date +%Y%m%d)
cp ~/ha-minipanel-next/{camera,colors,ha_client,layout_model,panel,settings,state_store,telemetry,views}.py ~/ha-minipanel/
# merge the new keys into ~/ha-minipanel/config.json (see config.example.json: rooms, scenes[{entity_id,label}], colors, ...)
sudo pkill -x xinit                                                   # supervisor relaunches the panel in ~3 s
```

`config.json` keys from v1 (`lights`, `cameras`, `poll_seconds`, `touch_band`, …) are still read. `rooms` replaces
`lights` for the room list; `lights` inside a room pins members when a group entity is unavailable.
The token stays in `~/.config/ha-minipanel/token` (root's copy `/root/.config/ha-minipanel/token` is what the autostart uses).

## Panel-only layout file

`/root/.config/ha-minipanel/layout.json` (0600, directory 0700) is written only when you press **Done** in Lights → Edit layout,
atomically (`.tmp` + fsync + rename) with `layout.json.bak` kept. It never touches Home Assistant.
To go back to the curated default rooms: Edit layout → Reset → Yes → Done, **or** `sudo rm /root/.config/ha-minipanel/layout.json*` and restart the panel.

## Rollback (fastest first)

1. **Panel code only (v2 → v1):**
   ```bash
   rm -r ~/ha-minipanel && mv ~/ha-minipanel.v1-<date> ~/ha-minipanel && sudo pkill -x xinit
   ```
   (`config.json.v1` is the v1 config; v1 ignores the new keys anyway.)
2. **Autostart back to the kiosk Chromium:** `sudo /boot/dietpi/dietpi-autostart 11 && sudo reboot`
   (the Chromium kiosk script and wait page are still present under `/opt/kiosk/` and `~/debloat-rollback-20261014/`).
3. **Layout only:** delete `layout.json*` as above.

## What deployment does *not* change

Home Assistant, its areas/groups/scenes/automations, `.storage`, `secrets.yaml`, camera credentials, `tapo_control`
(still disabled), the trusted-networks block in `configuration.yaml` (flagged for a separate security review – see the audit),
or any network/boot setting on either Pi.
