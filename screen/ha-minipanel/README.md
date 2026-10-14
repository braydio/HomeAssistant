# Home Panel, native Qt edition

A functioning proof-of-concept for **Raspberry Pi Zero 2 W + 7-inch HDMI touchscreen**. The Pi 4 continues hosting Home Assistant; the Zero runs a lightweight native Python/Qt Widgets client. **No Chromium or full Home Assistant frontend is loaded.**

## What works in this prototype

- **Home**: number of enabled lights, quick scene buttons (up to 3), all-off for the selected/auto-discovered lights, camera-page shortcut.
- **Lights**: auto-discovery or explicit list of Home Assistant `light.*` entities; on/off and brightness percentage for dimmable lights, with responsive touch controls.
- **Cameras**: on-demand, periodically refreshed JPEG snapshots of **one selected** `camera.*` entity through Home Assistant's authenticated camera proxy. This is **not full-motion live video**.
- **Settings**: auto day/night from `sun.sun` or local-time fallback; manual Light / Dark override; saved preference.
- Background HTTP jobs to keep touchscreen interaction responsive; no unnecessary WebView, dashboards, animations, or transcoding processes.

**Not yet done**: true H.264 camera live video, touchscreen/input driver setup, on-device performance benchmarks, Pi Zero 2 W hardware verification, OS autostart migration from Chromium. These require your actual devices. The attached Claude packet covers them.

## Install on DietPi Zero 2 W

Your current Chromium kiosk installation should be **backed up and preserved** initially. You can test the native panel from the existing graphical/X11 session.

```bash
sudo apt update
sudo apt install --no-install-recommends python3-pyqt5
# Copy the directory to ~/ha-minipanel (or another chosen path)
cd ~/ha-minipanel
cp config.example.json config.json
```

Replace `HOME_ASSISTANT_PI4_IP` in `config.json` with the *Pi 4 server's LAN IP*, not the Zero's IP. If auto-discovery is too broad, set arrays to real entity IDs and set auto discovery flags to `false`:

```json
"lights": ["light.living_room", "light.porch"],
"scenes": ["scene.relax", "scene.night"],
"cameras": ["camera.tapo_c120"]
```

The example entity names here are placeholders, **not discoveries of your actual devices**.

Create a long-lived access token in **Home Assistant → User profile → Security → Long-Lived Access Tokens**, then save it locally with restricted permissions:

```bash
install -d -m 700 ~/.config/ha-minipanel
umask 077
nano ~/.config/ha-minipanel/token
chmod 600 ~/.config/ha-minipanel/token
```

No token belongs in `config.json`, screenshots, Git commits, or Claude messages.

Run a safe offline demo first, from a working graphical session:

```bash
/usr/bin/python3 panel.py --demo --windowed
```

For the actual Home Assistant server:

```bash
/usr/bin/python3 panel.py --windowed
```

And only after validating touch, network, device controls, and layout:

```bash
/usr/bin/python3 panel.py
```

`panel.py` uses the distribution's Python Qt5 bindings. Avoid mixing system `python3-pyqt5` with a virtual environment that does not expose system site packages. On headless SSH, the UI requires a valid X11 display/session (`DISPLAY`) and appropriate X authority. **Do not install a full desktop environment just to run this.**

## Switching from Chromium kiosk

DietPi already has working Chromium autostart. Let Claude **inspect the current X11 startup chain**, back it up, and change only the *launched application*, not the whole image. The target is to start native Qt when the graphical session is ready, without two browsers/window managers consuming RAM. Do not switch autostart before manual tests pass. Maintain an SSH recovery path and a reversible way to restore Chromium.

## Camera behavior

This prototype uses `GET /api/camera_proxy/<entity_id>` for snapshots. Some camera integrations do not expose still images without special configuration. If the endpoint fails, fix/test the integration first. Tapo RTSP live video can be investigated as a separate optional player (preferably a low-resolution H.264 substream); **this build does not claim live video works on the Zero 2 W.**

## Architecture and performance

```
Pi 4 / DietPi                         Pi Zero 2 W / DietPi
+------------------------+             +---------------------------+
| Home Assistant 2026.7.4|   LAN API   | X11 + native Qt Widgets   |
| Docker container       |<----------->| HA state/lighting controls|
| Tapo camera entities   | snapshots   | 4-page touchscreen UI     |
+------------------------+             +---------------------------+
```

- Home Assistant state polling: default 12 seconds.
- Camera JPEG polling: default 12 seconds **only on Cameras page**.
- Network requests run outside the UI thread.
- Do not load all live streams or refresh camera snapshots continuously in the background.
- No HA server containers or integrations are installed on the Zero 2 W.
- A local private network is assumed. Configure HTTPS if the network cannot be trusted.

## Test and rollback

1. Run `python3 -m unittest -v test_ha_client.py`.
2. Launch with `--demo --windowed` and verify every page/theme setting with touch.
3. Configure URL/token. Test each selected light, one scene, and one camera snapshot.
4. Benchmark idle RSS/available RAM and interaction lag *on the Zero*, not the Pi 4.
5. Back up the existing Chromium launch/config and switch autostart only after working tests.
6. If kiosk startup fails, use SSH to restore previous autostart/config and reboot the Zero.

Upstream API references:
- https://developers.home-assistant.io/docs/api/rest/
- https://developers.home-assistant.io/docs/api/websocket/
- https://www.home-assistant.io/integrations/generic/
