"""Small per-user UI choices that should survive a restart.

One JSON file (config.UI_STATE_PATH): the app each task was last launched in,
whether the projects section is folded away. Read and written whole on every
change -- it holds a handful of keys, not data.
"""

import json
import os

import applog
import config

log = applog.get()


def _load():
    try:
        with open(config.UI_STATE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key, default=None):
    return _load().get(key, default)


def put(key, value):
    data = _load()
    data[key] = value
    try:
        os.makedirs(os.path.dirname(config.UI_STATE_PATH), exist_ok=True)
        with open(config.UI_STATE_PATH, "w") as f:
            json.dump(data, f)
    except OSError as e:
        log.warning("could not save UI state: %s", e)
