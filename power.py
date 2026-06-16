"""Windows power helpers: detect user idle time and put the PC to sleep.

Used after the 10:35 PM send so that, if the tool woke the PC, it goes back to
sleep. We only sleep when the user has been idle for a while, so we never sleep
the machine out from under someone who is actively using it.
"""
import ctypes
import logging
import subprocess

import config

log = logging.getLogger("power")
DETACHED_PROCESS = 0x00000008


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input (large if the PC was asleep)."""
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    tick = ctypes.windll.kernel32.GetTickCount()
    return max(0, (tick - info.dwTime)) / 1000.0


def maybe_sleep(reason: str = "") -> bool:
    """Sleep the PC if enabled and the user appears away. Returns True if sleeping."""
    if not config.SLEEP_AFTER_SEND:
        log.info("auto-sleep disabled in config; leaving PC awake.")
        return False
    idle = idle_seconds()
    if idle < config.SLEEP_MIN_IDLE_SECONDS:
        log.info("user appears active (idle %.0fs < %ds) — NOT sleeping the PC.",
                 idle, config.SLEEP_MIN_IDLE_SECONDS)
        return False
    log.info("idle %.0fs — sleeping the PC now (%s).", idle, reason or "post-send")
    try:
        # Detached so this process can exit; the system then suspends.
        subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                         shell=True, creationflags=DETACHED_PROCESS)
        return True
    except Exception as e:
        log.warning("failed to sleep PC: %s", e)
        return False
