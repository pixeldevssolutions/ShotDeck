# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Flow. Build on Rocky 9 -- see build_rocky9.sh.

    pyinstaller tools/build/flow.spec        # run from the app root

Every data folder keeps the layout the source tree uses, because the modules
find them with os.path.dirname(__file__) and that resolves inside the bundle
to the same relative place.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

# Relative paths in a spec resolve against the spec file, not the cwd, so every
# path here is anchored to the app root two levels up.
ROOT = os.path.dirname(os.path.dirname(SPECPATH))  # noqa: F821 -- PyInstaller injects SPECPATH


def root(*parts):
    return os.path.join(ROOT, *parts)


datas = [
    (root("media"), "media"),                     # ui/branding.py -> media/5and8_logo.png
    (root("envs"), "envs"),                       # config.ENVS_DIR
    (root("auth", "auth_config.yml"), "auth"),       # auth/config.py CONFIG_PATH
    # config.DCC_SOURCE_ROOT / CONTEXT_SOURCE_ROOT: put on PYTHONPATH for the
    # DCCs Flow launches, so they ship as plain files, not as imports.
    (root("rez", "flow_dcc"), "rez/flow_dcc"),
    (root("rez", "flow_context"), "rez/flow_context"),
]
datas += collect_data_files("shotgun_api3")  # bundled cacerts

a = Analysis(
    [root("main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "shotgun_api3",
        "ldap3",
        "yaml",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[root("tools", "build", "rthook_flow.py")],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "PIL", "cv2", "tkinter",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Flow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # upx mangles Qt's .so files; not worth the risk
    console=False,          # GUI app; applog still writes the log file
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Flow",
)
