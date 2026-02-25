"""Cross-platform scheduler for claude-news daily pipeline.

macOS:  launchd plist at ~/Library/LaunchAgents/com.claude-news.plist
Linux:  systemd user unit (timer + service), with cron fallback
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


_LAUNCHD_LABEL = "com.claude-news"
_SYSTEMD_SERVICE = "claude-news.service"
_SYSTEMD_TIMER = "claude-news.timer"
_CRON_MARKER = "# claude-news"


def _validate_time(time: str) -> tuple[int, int]:
    """Parse and validate HH:MM time string. Raises ValueError on bad input."""
    parts = time.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{time}', expected HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time '{time}': hour must be 0-23, minute 0-59")
    return hour, minute


def detect_platform() -> str:
    """Return 'macos', 'linux', or 'unsupported'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    return "unsupported"


# ---------------------------------------------------------------------------
# launchd (macOS)
# ---------------------------------------------------------------------------

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"


def _launchd_plist_content(run_sh_path: str, time: str) -> str:
    hour, minute = _validate_time(time)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{run_sh_path}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{int(hour)}</integer>
        <key>Minute</key>
        <integer>{int(minute)}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/claude-news-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/claude-news-stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>"""


def _install_launchd(run_sh_path: str, time: str) -> bool:
    plist = _launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_launchd_plist_content(run_sh_path, time))
    result = subprocess.run(["launchctl", "load", str(plist)], capture_output=True)
    return result.returncode == 0


def _uninstall_launchd() -> bool:
    plist = _launchd_plist_path()
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink()
    return True


# ---------------------------------------------------------------------------
# systemd (Linux)
# ---------------------------------------------------------------------------

def _systemd_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemd_service_content(run_sh_path: str) -> str:
    return f"""[Unit]
Description=claude-news daily pipeline

[Service]
Type=oneshot
ExecStart={run_sh_path}
"""


def _systemd_timer_content(time: str) -> str:
    return f"""[Unit]
Description=claude-news daily timer

[Timer]
OnCalendar=*-*-* {time}:00
Persistent=true

[Install]
WantedBy=timers.target
"""


def _install_systemd(run_sh_path: str, time: str) -> bool:
    d = _systemd_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / _SYSTEMD_SERVICE).write_text(_systemd_service_content(run_sh_path))
    (d / _SYSTEMD_TIMER).write_text(_systemd_timer_content(time))
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", _SYSTEMD_TIMER],
        capture_output=True,
    )
    return result.returncode == 0


def _uninstall_systemd() -> bool:
    d = _systemd_dir()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", _SYSTEMD_TIMER],
        capture_output=True,
    )
    for f in (_SYSTEMD_SERVICE, _SYSTEMD_TIMER):
        p = d / f
        if p.exists():
            p.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return True


# ---------------------------------------------------------------------------
# cron (Linux fallback)
# ---------------------------------------------------------------------------

def _crontab_entry(run_sh_path: str, time: str) -> str:
    hour, minute = _validate_time(time)
    return f"{minute} {hour} * * * {run_sh_path}  {_CRON_MARKER}"


def _install_cron(run_sh_path: str, time: str) -> bool:
    entry = _crontab_entry(run_sh_path, time)
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
        lines = [l for l in existing.splitlines() if _CRON_MARKER not in l]
        lines.append(entry)
        new_crontab = "\n".join(lines) + "\n"
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        return True
    except Exception:
        return False


def _uninstall_cron() -> bool:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return True
        lines = [l for l in result.stdout.splitlines() if _CRON_MARKER not in l]
        new_crontab = "\n".join(lines) + "\n" if lines else ""
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_scheduler(time: str, run_sh_path: str) -> bool:
    """Install platform-appropriate scheduler. Returns True on success."""
    plat = detect_platform()
    if plat == "macos":
        return _install_launchd(run_sh_path, time)
    elif plat == "linux":
        if shutil.which("systemctl"):
            return _install_systemd(run_sh_path, time)
        return _install_cron(run_sh_path, time)
    return False


def uninstall_scheduler() -> bool:
    """Remove scheduled job. Returns True on success."""
    plat = detect_platform()
    if plat == "macos":
        return _uninstall_launchd()
    elif plat == "linux":
        ok = _uninstall_systemd()
        _uninstall_cron()
        return ok
    return False


def get_scheduler_status() -> dict:
    """Return {installed: bool, platform: str}."""
    plat = detect_platform()
    installed = False
    if plat == "macos":
        installed = _launchd_plist_path().exists()
    elif plat == "linux":
        sd = _systemd_dir()
        installed = (sd / _SYSTEMD_TIMER).exists()
        if not installed:
            try:
                result = subprocess.run(
                    ["crontab", "-l"], capture_output=True, text=True
                )
                installed = _CRON_MARKER in result.stdout
            except Exception:
                pass
    return {"installed": installed, "platform": plat}
