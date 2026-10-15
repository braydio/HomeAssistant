# Setup notes

## Home (Pi 4)
- HA Container at `/mnt/dietpi_userdata/homeassistant`; backups in `/mnt/dietpi_userdata/backups-ha/`.
- Integrations (configured in the UI, not tracked): Cync (GE lights), WiZ, VeSync, Cast, Alexa Devices, HACS (+ Bubble Card, kiosk-mode, Browser Mod). `tapo_control` is installed but **disabled** (re-enabling with a stale password can trigger a camera lockout).
- Auth: `trusted_networks` auto-logs Home itself (`127.0.0.1`, `::1`) and Screen (`192.168.1.134`) in as the non-admin *Kiosk* user. Adjust the Screen IP if its DHCP lease changes, or reserve it in the router. Validate config before every restart.
- UI-created pieces to recreate on a fresh install: dashboard `home-panel` (`dashboards/home-panel.json`), helpers in `dashboards/helpers-*.json`, light groups `light.all_lights`, `kitchen_lights`, `bathroom_lights`, `living_room_lights`.
- BirdNET: `birdnet/` bridge as `c120-birdnet-bridge.service` (drop-in `backoff.conf`: 120 s restart delay to avoid camera lockouts).

## Screen (Pi Zero 2 W)
- Panel in `~/ha-minipanel`, started by `screen/system/custom.sh` (installed at `/var/lib/dietpi/dietpi-autostart/custom.sh`, enabled with `dietpi-autostart 14`). It waits for the network, runs X + the panel, restarts on crash and gives up after 5 quick failures so SSH stays available.
- Install: `sudo apt install --no-install-recommends python3-pyqt5`; copy `screen/ha-minipanel/` to `~/ha-minipanel`; copy `config.example.json` to `config.json` and list real entities; store a dedicated long-lived token at `~/.config/ha-minipanel/token` (mode 600, as the user the panel runs as, root on DietPi).
- Rollback to the Chromium kiosk: `sudo /boot/dietpi/dietpi-autostart 11 && sudo reboot`.
- The card was debloated; the services that were enabled before are in `screen/system/enabled-units-before-debloat.txt`.

## Touch panel quirk (QDtech MPI7002)
The 7" panel's digitizer only reports touches in a middle band of the screen: roughly Y 107-449 of 600 (X is full width). Touches in the top ~107 px and bottom ~150 px are never registered; positions inside the band are accurate (no offset), and a calibration matrix cannot help. The panel app therefore supports `"touch_band": [top, bottom]` in `config.json` (Screen uses `[112, 442]`): the full screen stays in use: the top and bottom dead zones show information only (clock, greeting, lights summary, connection status) and every control sits in the live band, in a compact layout with a drag-scrollable Lights list. Set it to `null`/omit it for a fully working touchscreen. Not yet determined whether the fault is the panel or its controller; try a different host or panel.
