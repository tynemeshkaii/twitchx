# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hidden_imports = (
    collect_submodules("objc")
    + collect_submodules("AppKit")
    + collect_submodules("AVFoundation")
    + collect_submodules("AVKit")
    + collect_submodules("webview")
    + collect_submodules("curl_cffi")
)

datas = [
    ("ui/index.html", "ui"),
    ("ui/css", "ui/css"),
    ("ui/js", "ui/js"),
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TwitchX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TwitchX",
)

app = BUNDLE(
    coll,
    name="TwitchX.app",
    icon=None,
    bundle_identifier="com.twitchx.app",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "12.0",
    },
)
