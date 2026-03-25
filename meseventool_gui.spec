# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('reference/*.json', 'reference'),
        ('reference/*.xdf',  'reference'),
    ],
    hiddenimports=[
        'meseventool',
        'meseventool.rom',
        'meseventool.needle',
        'meseventool.dpp',
        'meseventool.checksum',
        'meseventool.maps',
        'meseventool.patches',
        'meseventool.profiles',
        'meseventool.ecu_id',
        'meseventool.xdf',
        'meseventool.xdf_parser',
        'meseventool.kwp',
        'meseventool.known_roms',
        'meseventool.version',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter','matplotlib','numpy','scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MESevenTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
