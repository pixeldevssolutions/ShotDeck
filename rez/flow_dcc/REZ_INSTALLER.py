#!/usr/bin/env python
"""Build step for the flow_dcc rez package.

Same shape as flow_context's installer: rez runs this with
REZ_BUILD_SOURCE_PATH pointing at this folder and REZ_BUILD_INSTALL_PATH at the
version folder. Nothing compiles; the job is to put two trees where package.py
says they are.

Layout produced:

    <install>/python/flow_dcc/...      on PYTHONPATH, so `import flow_dcc`
    <install>/startup/maya/userSetup.py    on PYTHONPATH when maya is resolved
    <install>/startup/nuke/init.py         on NUKE_PATH when nuke is resolved
    <install>/startup/houdini/scripts/     on HOUDINI_PATH when houdini is
    <install>/startup/blender/startup/     BLENDER_USER_SCRIPTS for blender
    <install>/startup/substance/           Painter's plugins path
    <install>/startup/3de/                 3DE's custom scripts dir; the menu
                                           *is* these files
    <install>/startup/rhino/README.txt     no menu API -- run by name
    <install>/startup/silhouette/          not wired yet -- see package.py
    <install>/probe_silhouette.py          run inside Silhouette to find its hook
    <install>/verify_maya.py               run inside Maya to check the menu loaded
"""

import os
import shutil
import sys

# (source, destination-relative-to-install)
PAYLOADS = [
    ("flow_dcc", "python/flow_dcc"),
    ("startup", "startup"),
]
FILES = ["probe_silhouette.py", "verify_maya.py"]


def main():
    source_root = os.environ.get("REZ_BUILD_SOURCE_PATH") or \
        os.path.dirname(os.path.abspath(__file__))
    build_path = os.environ.get("REZ_BUILD_PATH")
    install_path = os.environ.get("REZ_BUILD_INSTALL_PATH")
    installing = os.environ.get("REZ_BUILD_INSTALL") == "1"

    # Always stage into the build dir so `rez build` alone is a real check.
    targets = []
    if build_path:
        targets.append(build_path)
    if installing and install_path:
        targets.append(install_path)
    if not targets:
        sys.exit("Neither REZ_BUILD_PATH nor REZ_BUILD_INSTALL_PATH is set — "
                 "run this through `rez build`, not directly.")

    for payload, relative in PAYLOADS:
        src = os.path.join(source_root, payload)
        if not os.path.isdir(src):
            sys.exit("Payload not found: {0}".format(src))
        for target in targets:
            dest = os.path.join(target, *relative.split("/"))
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            parent = os.path.dirname(dest)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            shutil.copytree(src, dest,
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          "*.pyc"))
            print("installed {0} -> {1}".format(payload, dest))

    for name in FILES:
        src = os.path.join(source_root, name)
        if not os.path.isfile(src):
            continue
        for target in targets:
            shutil.copy2(src, os.path.join(target, name))
            print("installed {0} -> {1}".format(name, target))


if __name__ == "__main__":
    main()
