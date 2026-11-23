# PyInstaller build recipe for the bot farm's Windows release.
#
#   pyinstaller BotFarm.spec
#
# The panel's page, icons and translations are data, not code, so they are
# listed here: the farm reads them from beside its modules.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('steamgiftbot') + collect_submodules('InquirerPy')

a = Analysis(
    ['botfarm.py'],
    pathex=[],
    binaries=[],
    datas=[('steamgiftbot/info.json', 'steamgiftbot'),
           ('steamgiftbot/farm/static', 'steamgiftbot/farm/static')],
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
    name='BotFarm',
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
