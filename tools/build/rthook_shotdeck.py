"""PyInstaller runtime hook: the two things shotdeck.sh does for a source run
that a frozen binary would otherwise miss.

Runs before main.py, so config.py sees the credentials at import time.
"""

import os

# PySide6 renders the tiles wrong under Rocky 9's wayland session.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

# ShotGrid credentials, root-owned, one file per workstation (DEPLOY-ROCKY9 §5).
# Same file shotdeck.sh sources; KEY=value lines, # comments, optional quotes.
_ENV_FILE = os.environ.get("SHOTDECK_ENV_FILE", "/etc/sgdesk/sgdesk.env")
try:
    with open(_ENV_FILE) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            os.environ.setdefault(key, value.strip().strip("'\""))
except OSError:
    pass    # No file on a dev box; SGClient reports the missing key itself.


if __name__ == "__main__":
    # python tools/build/rthook_shotdeck.py -- checks the env-file parser
    # against the shapes sgdesk.env actually takes.
    import tempfile
    sample = ("# comment\n"
              "\n"
              "SG_SCRIPT_KEY=abc123\n"
              "export SG_URL='https://x.shotgrid.autodesk.com'\n"
              'SHOTDECK_REZ_REQUEST="python-3.11 PySide6"\n'
              "  SPACED  =  value  \n"
              "novalue\n")
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write(sample)
        path = fh.name
    for key in ("SG_SCRIPT_KEY", "SG_URL", "SHOTDECK_REZ_REQUEST", "SPACED"):
        os.environ.pop(key, None)
    os.environ["SHOTDECK_ENV_FILE"] = path
    exec(open(__file__).read().split('if __name__')[0])
    assert os.environ["SG_SCRIPT_KEY"] == "abc123", os.environ["SG_SCRIPT_KEY"]
    assert os.environ["SG_URL"] == "https://x.shotgrid.autodesk.com"
    assert os.environ["SHOTDECK_REZ_REQUEST"] == "python-3.11 PySide6"
    assert os.environ["SPACED"] == "value"
    assert "novalue" not in os.environ
    os.unlink(path)
    print("rthook parser OK")
