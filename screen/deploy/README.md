# Native Qt panel auto-update (Screen only)

This adds a small **outbound-only updater** to the Pi Zero 2 W. No extra web server, webhook receiver, Docker, Chromium, or GitHub credentials are needed.

## Existing setup detected in repository

- Screen: Pi Zero 2 W, DietPi, native Qt panel at `/home/braydenchaffee/ha-minipanel`.
- Startup: DietPi `custom.sh` running `xinit /usr/bin/python3 /home/braydenchaffee/ha-minipanel/panel.py`. It relaunches the panel when `xinit` exits.
- Root's local Home Assistant token is outside the checkout, under `/root/.config/ha-minipanel/token`.
- The running app's `config.json`, preferences, layout and camera credentials are **not synced from GitHub**.

## First-time installation (required, on Screen)

The files committed to GitHub **do not install a service on the Pi by themselves**. After this pull request has been reviewed and merged, open SSH into **Screen**, not Home (Pi 4). Assuming `git` and the currently running native panel are installed:

```bash
# Run on Screen / Pi Zero 2 W
git clone --depth 1 --filter=blob:none --sparse https://github.com/braydio/HomeAssistant.git ~/ha-panel-bootstrap
git -C ~/ha-panel-bootstrap sparse-checkout set screen/deploy
sudo bash ~/ha-panel-bootstrap/screen/deploy/install.sh
systemctl list-timers ha-minipanel-update.timer
```

The installer refuses to touch a device without the expected native Qt program, `config.json`, DietPi `custom.sh`, `git`, system Python and Qt bindings. It only installs the updater script and systemd service/timer; it does not restart the panel or switch kiosk modes. On first poll, unchanged Python files are not redeployed.

To run one scan immediately:

```bash
sudo systemctl start ha-minipanel-update.service
sudo journalctl -u ha-minipanel-update.service -n 80 --no-pager
```

## Automation behavior

1. A **non-draft pull request from braydio in this repository** that changes **only** `screen/ha-minipanel/*` qualifies for unattended merging. It must complete `Native Qt panel tests` successfully, have a fresh tested head SHA and be mergeable under GitHub branch-protection rules. The privileged merge workflow never executes untrusted PR code.
2. GitHub Actions then merges the tested PR into `main`. This is implemented by `.github/workflows/native-panel-merge.yml`, not GitHub's built-in auto-merge toggle (which is currently disabled).
3. The Pi's `ha-minipanel-update.timer` checks the public repo after boot and roughly every **three minutes**. A shallow sparse checkout fetches only the native panel directory.
4. If managed Python sources changed, the updater copies the existing panel to a temporary same-filesystem candidate, keeps the *local* `config.json`, installs Python changes into the candidate, and runs compile + core + Qt offscreen tests on Screen.
5. With a healthy existing supervisor, it atomically renames the current release to a protected local backup, swaps the candidate into the existing app path, and terminates **only the matching panel xinit process** so DietPi's existing supervisor relaunches it. It verifies that a newly launched Python panel process survives at least 8 seconds.
6. If the new process fails to start/stay running, the prior app release is restored and restarted. The failed SHA is marked as rejected and is not retried until a new main commit or an explicit `--force` run. The updater retains two previous releases.

The timer's only ongoing work is a brief git fetch. It does **not** continually poll cameras, restart on docs-only changes or run a browser.

**Limitations:** This is a **process startup check**, not proof that every camera and touch control works after deployment. Offscreen tests cannot verify the actual dead-zone hardware or snapshot integration. The Pi must be online and the native-panel supervisor must already be active. A power loss during a two-directory swap, loss of the supervisor, or OS damage may require SSH recovery. Branch permissions may prevent the GitHub merge action from writing until Actions `GITHUB_TOKEN` write permissions are enabled.

## Operational commands

```bash
# Timer status and deploy log
systemctl status ha-minipanel-update.timer
sudo journalctl -u ha-minipanel-update.service -n 100 --no-pager

# Stop all future automatic pulls (does not stop the currently running panel)
sudo systemctl disable --now ha-minipanel-update.timer

# Retry a rejected current commit, after diagnosing the issue
sudo /usr/local/sbin/ha-minipanel-update --force

# If a release needs manual rollback:
sudo systemctl disable --now ha-minipanel-update.timer
sudo ls -ld /home/braydenchaffee/.ha-minipanel-rollback/previous-*
# Identify the desired previous release before running an atomic restore.
```

Existing emergency Chromium rollback remains `sudo /boot/dietpi/dietpi-autostart 11 && sudo reboot` and is unaffected.

## GitHub permissions and scope

The repository currently reports `allow_auto_merge: false`. The custom workflow can still merge eligible PRs using `GITHUB_TOKEN` if the repository's Actions policy allows `contents: write` and `pull-requests: write`. It does not enable auto-merge for unrelated PRs, and cannot merge the bootstrap PR containing `.github/workflows/` or `screen/deploy/` changes. Approve and merge that bootstrap PR manually after CI and hardware considerations.

To prevent unattended merges temporarily, disable the `Merge verified native Qt panel PRs` workflow, or keep proposed PRs in Draft.
