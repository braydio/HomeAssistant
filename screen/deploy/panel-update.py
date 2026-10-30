#!/usr/bin/env python3
"""Pull-only native Qt panel updater for the Screen (Pi Zero 2 W).

No inbound ports or GitHub credentials. Only the native panel's Python
sources are deployed. The existing config.json and root-held HA token
remain local. Run as root through the systemd timer shipped alongside.
"""
import argparse
import fcntl
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = Path("/home/braydenchaffee/ha-minipanel")
STATE = Path("/var/lib/ha-minipanel-updater")
REPO = STATE / "checkout"
BACKUPS = APP.parent / ".ha-minipanel-rollback"  # same filesystem as APP for atomic swaps
ORIGIN = "https://github.com/braydio/HomeAssistant.git"
PANEL_PATH = "screen/ha-minipanel"
TESTS = ("test_layout_model", "test_colors", "test_core",
         "test_ha_client", "test_health", "test_ui_offscreen")
PYTHON = "/usr/bin/python3"


def info(message):
    print("[panel-updater] " + message, flush=True)


def command(argv, *, cwd=None, env=None, timeout=180):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True,
                            timeout=timeout, check=False)
    if result.returncode:
        tail = (result.stdout + "\n" + result.stderr).strip()[-2500:]
        raise RuntimeError("Command failed (exit %d): %s\n%s" %
                           (result.returncode, " ".join(argv), tail))
    return result.stdout.strip()


def atomic_write(path, content):
    temp = path.with_suffix(".tmp")
    temp.write_text(content + "\n", encoding="utf-8")
    os.replace(temp, path)


def read_marker(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def process_args(pid):
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        return [os.fsdecode(part) for part in raw.split(b"\x00") if part]
    except (OSError, ValueError):
        return []


def processes():
    panel = str(APP / "panel.py")
    supervisors, clients = [], []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        args = process_args(pid)
        if not args:
            continue
        executable = Path(args[0]).name
        if executable == "xinit" and panel in args:
            supervisors.append(pid)
        if executable.startswith("python") and panel in args:
            clients.append(pid)
    return supervisors, clients


def fetch_head():
    if not (REPO / ".git").is_dir():
        info("Creating shallow, sparse repository checkout")
        command(["git", "clone", "--depth=1", "--filter=blob:none", "--sparse",
                 "--branch", "main", ORIGIN, str(REPO)], timeout=120)
        command(["git", "-C", str(REPO), "sparse-checkout", "set", PANEL_PATH])
    command(["git", "-C", str(REPO), "fetch", "--depth=1", "origin", "main"], timeout=120)
    command(["git", "-C", str(REPO), "checkout", "--force", "FETCH_HEAD"])
    sha = command(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    source = REPO / PANEL_PATH
    if not (source / "panel.py").is_file():
        raise RuntimeError("Repository is missing the native Qt panel")
    return sha, source


def hashes(directory):
    """Only managed top-level Python files; no local configuration or secrets."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.glob("*.py") if p.is_file() and not p.is_symlink()}


def stage(source, parent):
    candidate = parent / "app"
    shutil.copytree(APP, candidate, symlinks=False)
    for f in candidate.glob("*.py"):
        f.unlink()
    for f in source.glob("*.py"):
        if f.is_symlink():
            raise RuntimeError("Refusing a symlinked source: " + f.name)
        shutil.copy2(f, candidate / f.name)
    if not (candidate / "config.json").is_file():
        raise RuntimeError("Local config.json did not survive staging")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
    info("Compiling and testing the candidate release (Qt offscreen)")
    command([PYTHON, "-m", "compileall", "-q", str(candidate)], timeout=120)
    command([PYTHON, "-m", "unittest", *TESTS], cwd=candidate, env=env, timeout=240)
    return candidate


def terminate_panel(supervisors):
    for pid in supervisors:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def healthy_after(previous_pids, seconds=55):
    """Confirm a newly launched native Qt process stays alive for 8 seconds.

    This checks process stability, not touchscreen/camera quality.
    """
    deadline = time.monotonic() + seconds
    start_seen = None
    fresh = set()
    while time.monotonic() < deadline:
        _, current = processes()
        new = set(current) - set(previous_pids)
        if new and new == fresh:
            if start_seen is not None and time.monotonic() - start_seen >= 8:
                return True
        elif new:
            fresh, start_seen = new, time.monotonic()
        else:
            fresh, start_seen = set(), None
        time.sleep(2)
    return False


def install_release(candidate, sha):
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(BACKUPS, 0o700)
    supervisors, previous_pids = processes()
    if not supervisors or not previous_pids:
        info("No running native Qt panel/xinit supervisor; skipping deployment")
        return False
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / ("previous-" + stamp + "-" + sha[:8])
    failed = BACKUPS / ("failed-" + stamp + "-" + sha[:8])
    info("Swapping panel files; retaining existing local config and backup")
    os.rename(APP, backup)
    try:
        os.rename(candidate, APP)
    except Exception:
        os.rename(backup, APP)
        raise

    try:
        terminate_panel(supervisors)
        if not healthy_after(previous_pids):
            raise RuntimeError("New panel process did not remain alive after restart")
        info("New Qt panel process started and remained alive")
    except Exception:
        info("Health check failed; restoring the previous panel release")
        # Keep the failed release privately for investigation.
        os.rename(APP, failed)
        os.rename(backup, APP)
        supervisors, _ = processes()
        terminate_panel(supervisors)
        raise

    # Retain two previous releases; do not remove the just-deployed app.
    previous = sorted(BACKUPS.glob("previous-*"), key=lambda p: p.stat().st_mtime,
                      reverse=True)
    for old in previous[2:]:
        shutil.rmtree(old)
    return True


def main():
    parser = argparse.ArgumentParser(description="Auto-update the native Qt touchscreen from main")
    parser.add_argument("--force", action="store_true",
                        help="Retry the currently rejected SHA for manual recovery")
    args = parser.parse_args()
    if os.geteuid():
        raise SystemExit("Must run as root: systemd timer runs with root permissions")
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    lockfile = STATE / "update.lock"
    with lockfile.open("w") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            info("Another update is running")
            return
        sha, source = fetch_head()
        current, rejected = read_marker(STATE / "deployed.sha"), read_marker(STATE / "rejected.sha")
        if current == sha and not args.force:
            return
        if rejected == sha and not args.force:
            info("Commit " + sha[:12] + " previously failed; awaiting a newer commit")
            return
        if not (APP / "panel.py").is_file() or not (APP / "config.json").is_file():
            info("Native Qt panel or local config missing; refusing to change the kiosk")
            return
        if hashes(source) == hashes(APP) and not args.force:
            atomic_write(STATE / "deployed.sha", sha)
            info("No Python panel changes at " + sha[:12] + "; no restart")
            return
        supervisors, clients = processes()
        if not supervisors or not clients:
            info("Panel supervisor not active; refusing to deploy to an unverified session")
            return
        parent = Path(tempfile.mkdtemp(prefix=".panel-update-", dir=APP.parent))
        os.chmod(parent, 0o700)
        try:
            try:
                candidate = stage(source, parent)
                if install_release(candidate, sha):
                    atomic_write(STATE / "deployed.sha", sha)
                    (STATE / "rejected.sha").unlink(missing_ok=True)
                    info("Deployed main@" + sha[:12])
            except Exception as exc:
                atomic_write(STATE / "rejected.sha", sha)
                raise RuntimeError("Rejected main@%s: %s" % (sha[:12], exc)) from exc
        finally:
            shutil.rmtree(parent, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        info("ERROR: " + str(exc))
        sys.exit(1)
