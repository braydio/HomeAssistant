# Claude implementation packet: Pi Zero 2 W native Home Assistant panel

## Goal

Deploy the accompanying runnable **PyQt5 Qt Widgets** prototype (`panel.py` + `ha_client.py`) on the user's Pi Zero 2 W. Replace the sluggish Chromium frontend **only after successful validation**, retaining the Pi 4 as the Home Assistant server (Container, Core 2026.7.4). The 7-inch HDMI touch panel is landscape. Maintain the user's approved minimal four-page concept, with auto dark mode.

**Execute the work, not just a plan.** Use the provided source as the initial implementation, adjust it where required, and report verified results vs. limitations.

## Guardrails

- Do not reinstall DietPi or touch the Pi 4's production Home Assistant installation.
- The Zero's SD card may temporarily be booted or mounted on the Pi 4 for cleanup. Determine active root filesystem (`findmnt -no SOURCE /`, `lsblk -f`) before issuing system-modifying commands.
- Preserve SSH, Wi-Fi, HDMI, touch input, and working Chromium kiosk rollback.
- Before changes: back up autostart scripts, `/boot/dietpi.txt`, X11 configuration, and any target files. Never overwrite unexplained customizations.
- Never print/copy credentials into logs, terminal transcript, output, repo, or responses. Set up private on-device token storage with mode 0600; do not bake the token into config.json.
- Inspect the real X11/DietPi startup method. Do **not** assume an existing desktop, `DISPLAY=:0`, or a particular systemd user.
- Do not perform broad package purges, disable networking, or alter Home Assistant camera privacy/recording settings.
- Avoid GPU-disable flag cargo cult: evaluate actual rendering and resource use.

## Phase 1. Establish state and baseline

Inspect CPU architecture (`uname -m`), OS, X11 compositor/window manager, current Chromium autostart chain, display resolution (`xrandr` when available), `/dev/input` touchscreen enumeration, CPU/RAM/swap and active services. Confirm the X server runs on the Pi Zero without Chromium, and determine how to start a Qt app in its session.

Measure actual UI responsiveness and RAM consumption on the Pi Zero. Results measured with the card booted on the Pi 4 do not count as Zero performance.

## Phase 2. Deploy native Qt prototype and demo

Install only prerequisites needed for native Qt on DietPi, ideally `python3-pyqt5` from the distro repository. Prefer existing minimal X11 server/window manager; no full desktop. Copy supplied app into an appropriately permissioned user directory, run unit tests, and launch `panel.py --demo --windowed` in the working X session.

Test the four pages with **touch**, not just mouse clicks. Verify UI layout at the display's real native resolution (e.g., 1024x600 or 800x480, don't assume). Fix any PyQt package/Qt platform plugin issues.

## Phase 3. Connect real Home Assistant data

Use the HA Pi 4's LAN URL and locally stored dedicated HA token. Inventory current `light.*`, `scene.*`, `camera.*`, and `sun.sun` entities. Populate `config.json` with a curated, minimal entity set and meaningful order. No dummy device names left in production.

Check lighting features. Turn a single harmless light on/off and change brightness after confirming supported color modes. Validate responsive UI and actual HA state changes. Ensure controls reflect external changes with polling. Handle unavailable entities and disconnected HA gracefully.

## Phase 4. Finish visual design

Maintain minimal design with clear spacing, 7-inch touch-friendly controls, no unnecessary gradients/animations, and no global dashboard home screen crammed with controls.

Four pages:
1. **Home:** greeting, lights-on summary, 3 favorite scenes, Camera shortcut, All Off.
2. **Lights:** up to 3-5 visible large room controls at once; scroll as needed; toggle/brightness.
3. **Cameras:** one selected camera at a time; view snapshots first; camera switching.
4. **Settings:** Auto/Light/Dark theme, connection and display status.

Auto theme reads `sun.sun` from HA; local time fallback when offline. Manual override survives restart.

## Phase 5. Camera feasibility, separately

Snapshot mode must work first through HA's authenticated camera proxy if supported. Verify resolution and interval are lightweight. Evaluate true live view **only if feasible** without freezing the touchscreen. For live video, investigate a separate minimal H.264-capable player (e.g. mpv/gstreamer supported on that specific Pi OS/kernel) using the C120's low-res stream and hardware decode. Do not embed a browser or 3 simultaneous streams. Treat credentials securely and avoid leaking camera URLs in process arguments, config files, or logs. Report measured CPU/RAM and a yes/no recommendation. Real-time video is intentionally NOT implemented by this starter.

## Phase 6. Autostart migration

Only after the native UI succeeds manually, back up the old Chromium launch path and change the graphical-session **application entry point** to run `/usr/bin/python3 /path/to/panel.py`. Make sure Chromium is not left resident or launched alongside native Qt. Start the Qt app after network readiness, provide crash restart policy without endless rapid restart, preserve SSH recovery, and explicitly document how to revert to Chromium.

Do a full physical Zero reboot and confirm UI starts reliably with no keyboard/mouse required and touch remains responsive.

## Phase 7. Real benchmarks and delivery

Before/after RAM free/available, process RSS, CPU use, input-to-visible-update lag, HA action confirmation delay, camera snapshot load time, Pi CPU temperature, uptime after 20 minutes, Wi-Fi reconnect, and boot-to-touch-ready.

Deliver working app, changed files, installed packages, exact working dashboard, verified device list, known limitations, and a copy-paste rollback procedure. State clearly if the Zero 2 W cannot meet minimum usability and propose a fallback rather than pretending it does.

## Acceptance criteria

- Chromium is not running concurrently with the native panel.
- One-finger tap and slider input work at native resolution.
- All configured lights and scene buttons perform HA actions.
- Auto dark mode switches at sun state changes; manual mode persists.
- Camera snapshot is only fetched while viewing Cameras; no decoding when hidden.
- On disconnect the app indicates offline instead of freezing.
- On boot the native panel starts autonomously and can be rolled back to Chromium.

Start with read-only inspection and backup, then progress to implementation and testing with no unnecessary approval pauses. Request user input only for credentials or permission-sensitive operations that cannot be resolved otherwise.
