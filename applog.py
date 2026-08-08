"""Logging for ShotDeck: one session log, one file per launched process.

Everything ShotDeck does that an artist might have to explain to a supervisor --
which command ran, with which packages, against which task -- goes through here.
Two sinks:

  * ~/.shotdeck/logs/session-<pid>.log   what ShotDeck itself did
  * ~/.shotdeck/logs/<stamp>-<name>.log  stdout+stderr of one launched DCC

The UI subscribes with `subscribe()` to mirror the session log into the Terminal
panel. This module deliberately does not import Qt, so it stays usable when
ShotDeck code is run headless (probes, cron jobs, tests).
"""

import datetime
import logging
import os
import re
import sys

LOG_DIR = os.environ.get(
    "SHOTDECK_LOG_DIR", os.path.expanduser("~/.shotdeck/logs"))

# Launch logs older than this are removed when a new session starts.
LOG_MAX_AGE_SECONDS = 14 * 24 * 3600

_log = logging.getLogger("shotdeck")
_subscribers = []
_configured = False


class _FanoutHandler(logging.Handler):
    """Pushes formatted records at anything that called subscribe()."""

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            return
        for callback in list(_subscribers):
            try:
                callback(line, record.levelno)
            except Exception:
                pass    # a broken UI must never take down a launch


def setup(verbose=False):
    """Configure the session log. Safe to call more than once."""
    global _configured
    if _configured:
        return _log

    os.makedirs(LOG_DIR, exist_ok=True)
    _prune()

    _log.setLevel(logging.DEBUG if verbose else logging.INFO)
    _log.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S")

    session_path = os.path.join(LOG_DIR, f"session-{os.getpid()}.log")
    file_handler = logging.FileHandler(session_path)
    file_handler.setFormatter(fmt)
    _log.addHandler(file_handler)

    # Console, so `python main.py` in a terminal shows the same thing.
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    _log.addHandler(stream_handler)

    fanout = _FanoutHandler()
    fanout.setFormatter(fmt)
    _log.addHandler(fanout)

    _configured = True
    _log.info("session log: %s", session_path)
    return _log


def get():
    """The shared logger, configured on first use."""
    return setup()


def subscribe(callback):
    """Call `callback(line, levelno)` for every future log record."""
    _subscribers.append(callback)


def unsubscribe(callback):
    if callback in _subscribers:
        _subscribers.remove(callback)


def launch_log_path(name):
    """A fresh log file for one launched process."""
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "app"
    return os.path.join(LOG_DIR, f"{stamp}-{safe}.log")


def _prune():
    """Drop old launch logs so ~/.shotdeck/logs does not grow without bound."""
    import time
    cutoff = time.time() - LOG_MAX_AGE_SECONDS
    try:
        names = os.listdir(LOG_DIR)
    except OSError:
        return
    for name in names:
        if not name.endswith(".log"):
            continue
        path = os.path.join(LOG_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass
