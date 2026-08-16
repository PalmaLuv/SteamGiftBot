# PyInstaller build recipe for the Windows release.
#
#   pyinstaller SteamGiftBot.spec
#
# info.json has to be listed explicitly: bot.py reads it from beside the module,
# and PyInstaller only bundles imported code, not the data next to it.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('InquirerPy')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('steamgiftbot/info.json', 'steamgiftbot')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'ruff'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SteamGiftBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
