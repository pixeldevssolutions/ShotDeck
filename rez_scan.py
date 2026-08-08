"""Discover launchable DCCs by reading the rez package tree.

The studio's released packages live under one root, one folder per package and
one folder per version inside it:

    /software/packages/dcc/
        maya/2026
        houdini/20.5
        houdini/21.0.596
        nuke/16.0v7

Nothing here talks to rez itself -- listing directories is enough, and it keeps
the UI responsive without spawning `rez search` on every project open.
"""

import os
import re

import config


def scan(root=None):
    """Return [(package, [versions, newest first]), ...] sorted by package name.

    Packages with no version folders are skipped: there would be nothing to
    launch. Loose files in the tree (installers, archives) are ignored.
    """
    root = root or config.DCC_PACKAGES_ROOT
    if not os.path.isdir(root):
        return []

    out = []
    for name in sorted(os.listdir(root)):
        pkg_dir = os.path.join(root, name)
        if not os.path.isdir(pkg_dir) or name.startswith("."):
            continue
        versions = [
            v for v in os.listdir(pkg_dir)
            if not v.startswith(".") and os.path.isdir(os.path.join(pkg_dir, v))
        ]
        if not versions:
            continue
        versions.sort(key=version_key, reverse=True)
        out.append((name, versions))
    return out


def version_key(version):
    """Sort key that orders 21.0.596 above 20.5, and 16.0v7 above 16.0v2.

    Splits into runs of digits and non-digits so numeric chunks compare as
    numbers; the string chunks keep suffixes like 'v' or 'beta' ordered
    consistently rather than by ASCII against digits.
    """
    parts = re.findall(r"\d+|\D+", version)
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]


def command_for(package):
    """The executable to run inside `rez env <package>`.

    Defaults to the package name, which is what most rez packages alias. The
    exceptions live in config.DCC_COMMANDS.
    """
    return config.DCC_COMMANDS.get(package, package)


def request(package, version=None):
    """The rez request string for a package, e.g. 'maya-2026'."""
    return f"{package}-{version}" if version else package
