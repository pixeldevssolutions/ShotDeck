#!/usr/bin/env python
"""Build step for the shotdeck_context rez package.

rez runs this from the package folder with REZ_BUILD_SOURCE_PATH pointing here
and REZ_BUILD_INSTALL_PATH pointing at the version folder being built. The job
is only to copy the payload into place -- there is nothing to compile.

Layout produced:

    <install>/python/shotdeck_context/__init__.py

which matches the PYTHONPATH.prepend("{root}/python") in package.py.
"""

import os
import shutil
import sys

PAYLOAD = "shotdeck_context"     # source folder next to this script


def main():
    source_root = os.environ.get("REZ_BUILD_SOURCE_PATH") or \
        os.path.dirname(os.path.abspath(__file__))
    build_path = os.environ.get("REZ_BUILD_PATH")
    install_path = os.environ.get("REZ_BUILD_INSTALL_PATH")
    installing = os.environ.get("REZ_BUILD_INSTALL") == "1"

    src = os.path.join(source_root, PAYLOAD)
    if not os.path.isdir(src):
        sys.exit("Payload not found: {0}".format(src))

    # Always stage into the build dir so `rez build` alone is a real check.
    targets = []
    if build_path:
        targets.append(build_path)
    if installing and install_path:
        targets.append(install_path)
    if not targets:
        sys.exit("Neither REZ_BUILD_PATH nor REZ_BUILD_INSTALL_PATH is set — "
                 "run this through `rez build`, not directly.")

    for target in targets:
        dest = os.path.join(target, "python", PAYLOAD)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(os.path.dirname(dest))
        shutil.copytree(src, dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print("installed {0} -> {1}".format(PAYLOAD, dest))


if __name__ == "__main__":
    main()
