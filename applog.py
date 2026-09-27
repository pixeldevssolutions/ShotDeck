"""Logging for Flow: one session log, one file per launched process.

Everything Flow does that an artist might have to explain to a supervisor --
which command ran, with which packages, against which task -- goes through here.
Two sinks:

  * ~/.flow/logs/session-<pid>.log   what Flow itself did
  * ~/.flow/logs/<stamp>-<name>.log  stdout+stderr of one launched DCC

The UI subscribes with `subscribe()` to mirror the session log into the Terminal
panel. This module deliberately does not import Qt, so it stays usable when
Flow code is run headless (probes, cron jobs, tests).
"""

import datetime
import faulthandler
import logging
import os
import re
import sys

LOG_DIR = os.environ.get(
    "FLOW_LOG_DIR", os.path.expanduser("~/.flow/logs"))

# Launch logs older than this are removed when a new session starts.
LOG_MAX_AGE_SECONDS = 14 * 24 * 3600

_log = logging.getLogger("flow")
_subscribers = []
_configured = False
_crash_file = None      # kept open for faulthandler, see _enable_crash_dump()


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

    _enable_crash_dump()

    _configured = True
    _log.info("session log: %s", session_path)
    return _log


def _enable_crash_dump():
    """Write a Python traceback to crash-<pid>.log on a hard crash.

    A segfault inside Qt gives the artist "exit code 139" and nothing else.
    faulthandler turns that into the Python stack of every thread at the
    moment of the fault, which is usually enough to name the widget.
    """
    global _crash_file
    try:
        _crash_file = open(os.path.join(LOG_DIR, f"crash-{os.getpid()}.log"),
                           "w")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        faulthandler.enable(all_threads=True)


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
    """Drop old launch logs so ~/.flow/logs does not grow without bound."""
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
