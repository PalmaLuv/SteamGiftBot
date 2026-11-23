# PyInstaller build recipe for the bot farm's Windows release.
#
#   pyinstaller BotFarm.spec
#
# The panel's page, icons and translations are data, not code, so they are
# listed here: the farm reads them from beside its modules.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules('steamgiftbot') + collect_submodules('InquirerPy')

# Windows has no time zone database: zoneinfo reads the tzdata package, which
# is imported by name at run time, so neither it nor its files are found by
# following imports. Installed only on Windows (requirements.txt).
try:
    import tzdata  # noqa: F401
    hiddenimports += collect_submodules('tzdata')
    tzfiles = collect_data_files('tzdata')
except ImportError:
    tzfiles = []

a = Analysis(
    ['botfarm.py'],
    pathex=[],
    binaries=[],
    datas=[('steamgiftbot/info.json', 'steamgiftbot'),
           ('steamgiftbot/farm/static', 'steamgiftbot/farm/static')] + tzfiles,
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
