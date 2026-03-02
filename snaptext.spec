# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[
        (r'C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe', '.'),
        (r'C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffprobe.exe', '.'),
    ],
    datas=[
        ('templates', 'templates'),
        (r'C:\Windows\Fonts\arialbd.ttf', '.'),
    ],
    hiddenimports=['flask', 'werkzeug', 'jinja2', 'click'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='SnapText',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    upx=True,
    upx_exclude=[],
    name='SnapText',
)
