# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = SPECPATH

# Locate llama_cpp native libraries for bundling
_site_packages = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
_llama_lib_dir = _site_packages / "llama_cpp" / "lib"

llama_binaries = []
if _llama_lib_dir.exists():
    for dylib in _llama_lib_dir.glob("*.dylib"):
        llama_binaries.append((str(dylib), "llama_cpp/lib"))

a = Analysis(
    ["main.py"],
    pathex=[PROJECT_ROOT],
    binaries=[
        (os.path.join(PROJECT_ROOT, "bin", "ffmpeg"), "bin"),
        (os.path.join(PROJECT_ROOT, "bin", "ffprobe"), "bin"),
    ] + llama_binaries,
    datas=[
        (os.path.join(PROJECT_ROOT, "models", "qwen2.5-coder-0.5b-instruct-q8_0.gguf"), "models"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "llama_cpp",
        "llama_cpp.llama",
        "llama_cpp.llama_cpp",
        "llama_cpp.llama_chat_format",
        "llama_cpp.llama_grammar",
        "llama_cpp.llama_tokenizer",
        "llama_cpp.llama_types",
        "llama_cpp._internals",
        "llama_cpp._ctypes_extensions",
        "llama_cpp._ggml",
        "llama_cpp._logger",
        "llama_cpp._utils",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["hooks/hook-fix-permissions.py"],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy.testing",
        "scipy",
        "PIL",
        "IPython",
        "jupyter",
        "notebook",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtNetworkAuth",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtPrintSupport",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtTest",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "PySide6.QtXml",
    ],
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
    name="AI-ncoder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    name="AI-ncoder",
)

app = BUNDLE(
    coll,
    name="AI-ncoder.app",
    icon=None,
    bundle_identifier="com.ai-ncoder.app",
    info_plist={
        "CFBundleDisplayName": "AI-ncoder",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
)
