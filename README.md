# HomeAssistant

Version-controlled setup for my home automation, split across two Raspberry Pis on DietPi:

| Name | Hardware | Role | Lives in |
|---|---|---|---|
| **Home** | Raspberry Pi 4 (`192.168.1.218`) | Home Assistant Container (Core 2026.7.4), BirdNET camera audio bridge | repo root, `dashboards/`, `themes/`, `birdnet/` |
| **Screen** | Raspberry Pi Zero 2 W + 7" 1024x600 touchscreen | Native Qt wall panel, no browser | `screen/` |

The repo root *is* Home's HA config directory (`/mnt/dietpi_userdata/homeassistant`), so Home can `git pull`.

## Layout
- `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `themes/` - Home Assistant config. Panel Day/Night themes, colour scripts and presets, light-panel scenes.
- `dashboards/` - exported UI-managed state (not stored as YAML by HA): the `home-panel` dashboard, helpers (`input_select`, `input_text`), dashboard list.
- `birdnet/` - C120 camera 16 kHz audio bridge for BirdNET plus systemd units. Credentials come from an untracked `c120.env` (see `c120.env.example`).
- `screen/ha-minipanel/` - the native PyQt5 panel (Home / Lights / Cameras, Settings from Home; per-light colour; panel-only room editing), with tests. See `docs/PANEL_*.md`.
- `screen/system/` - the DietPi autostart supervisor and the pre-debloat service list.
- `docs/SETUP.md` - how everything fits together, restore steps, rollback.

## Not in the repo (on purpose)
`secrets.yaml`, `.storage/` (auth, tokens, integration credentials), the recorder database, logs, backups, HACS and its frontend plugins, `browser_mod`, `tapo_control`, any `.env`/token files, and the panel's `config.json`/token/preferences.
