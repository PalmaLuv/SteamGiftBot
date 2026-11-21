"""Secrets stay out of logs, logs and debug pages are owner-only, and the
command line bot's old log files are cleaned up after the history import."""
import logging
import os
import stat
import time

import pytest
import requests

from test_farm import manager  # noqa: F401

from steamgiftbot import logging_setup
from steamgiftbot.farm import __main__ as farmMain
from steamgiftbot.farm import rules
from steamgiftbot.farm.manager import FarmManager

KEY = 'ABCDEF0123456789ABCDEF0123456789'
BOT = '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw'

posixOnly = pytest.mark.skipif(os.name != 'posix', reason="file modes are POSIX only")


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def openUmask():
    # The usual 022: without the fix, files come out 0644.
    old = os.umask(0o022)
    yield
    os.umask(old)


# ---- masking -------------------------------------------------------------------

def test_api_key_and_tokens_are_masked():
    text = ("HTTPSConnectionPool(host='api.steampowered.com', port=443): Max retries exceeded "
            f"with url: /IPlayerService/GetOwnedGames/v1/?key={KEY}&steamid=76561198000000000"
            "&include_appinfo=1 (Caused by ...)")
    clean = logging_setup.redactSecrets(text)
    assert KEY not in clean
    assert '?key=***&steamid=76561198000000000&include_appinfo=1' in clean
    assert logging_setup.redactSecrets(
        'x?access_token=t0k&api_key=k3y&page=2&sessionid=s1d') == \
        'x?access_token=***&api_key=***&page=2&sessionid=***'
    clean = logging_setup.redactSecrets(f'for url: https://api.telegram.org/bot{BOT}/getUpdates')
    assert BOT.split(':')[1] not in clean and '/bot***/getUpdates' in clean
    # Nothing secret, nothing changed.
    plain = 'https://www.steamgifts.com/giveaways/search?page=2&q=key'
    assert logging_setup.redactSecrets(plain) == plain
    assert logging_setup.redactSecrets('') == '' and logging_setup.redactSecrets(None) is None


class FailingSteam:
    """Answers like api.steampowered.com when it is down: requests' own error,
    with the full URL and the key in it."""

    def get(self, url, params=None, timeout=None):
        prepared = requests.Request('GET', url, params=params).prepare()
        response = requests.Response()
        response.status_code = 500
        response.reason = 'Internal Server Error'
        response.url = prepared.url
        return response


def test_steam_errors_do_not_leak_the_key(caplog):
    library = rules.SteamLibrary(session=FailingSteam())
    with caplog.at_level(logging.WARNING, logger='botfarm'):
        assert library.owned(KEY, '76561198000000000') is None
    # The error is still there to read, only without the key.
    assert '500 Server Error' in library.problem and 'key=***' in library.problem
    assert KEY not in library.problem
    assert caplog.records and KEY not in caplog.text


def test_steam_status_in_the_panel_has_no_key(manager):  # noqa: F811
    manager.steam = rules.SteamLibrary(session=FailingSteam())
    manager.updateFarmSettings({'steam_api_key': KEY, 'steam_profile': '76561198000000000'})
    assert 'библиотека не загрузилась' in manager.steamCheck()
    assert KEY not in manager.steamCheck()
    status = manager.publicFarmSettings()['steam_status']
    assert status and KEY not in status


def test_log_lines_and_tracebacks_are_masked(tmp_path):
    logger = logging.getLogger('botfarm.test-secrets')
    logger.propagate = False
    handler = logging_setup.privateLogHandler(tmp_path / 'x.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    try:
        logger.warning("Telegram: %s", f"404 for url: https://api.telegram.org/bot{BOT}/x")
        try:
            raise requests.ConnectionError(f"Max retries exceeded with url: /v1/?key={KEY}")
        except requests.ConnectionError:
            logger.exception(f"failed ?key={KEY}")
    finally:
        logger.removeHandler(handler)
        handler.close()
    text = (tmp_path / 'x.log').read_text(encoding='utf-8')
    assert KEY not in text and BOT not in text
    assert 'failed ?key=***' in text and 'Traceback' in text
    assert 'ConnectionError: Max retries exceeded with url: /v1/?key=***' in text


def test_panel_log_lines_are_masked(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    platform.logger.warning(f"Ошибка: 500 for url: https://x/?token={KEY}")
    lines = [line['text'] for line in platform.logLines()]
    assert any('token=***' in line for line in lines)
    assert not any(KEY in line for line in lines)


# ---- owner-only files ------------------------------------------------------------

@posixOnly
def test_command_line_log_is_private_and_rolls_over_private(tmp_path, openUmask):
    path = logging_setup.configure(True, tmp_path)
    try:
        assert mode(path) == 0o600
        handler = logging_setup.getLogger().handlers[0]
        handler.maxBytes = 50
        for _ in range(5):
            logging_setup.getLogger().info("x" * 40)
        rotated = sorted(tmp_path.glob('log-*.log*'))
        assert len(rotated) > 1
        assert all(mode(item) == 0o600 for item in rotated)
    finally:
        logging_setup.configure(False, tmp_path)


@pytest.fixture
def farmLogger():
    logger = logging.getLogger('botfarm')
    before = list(logger.handlers)
    yield logger
    for handler in list(logger.handlers):
        if handler not in before:
            logger.removeHandler(handler)
            handler.close()
    logger.propagate = True


@posixOnly
def test_farm_log_is_private_and_masked(tmp_path, openUmask, farmLogger, capsys):
    farmMain.configureLogging(tmp_path)
    farmLogger.warning(f"Библиотека: 500 for url: /x?key={KEY}")
    path = tmp_path / 'log' / 'botfarm.log'
    assert mode(path) == 0o600
    for handler in farmLogger.handlers:
        handler.flush()
    assert 'key=***' in path.read_text(encoding='utf-8')
    assert KEY not in path.read_text(encoding='utf-8')
    # The journal gets stdout: masked there too.
    out = capsys.readouterr().out
    assert 'key=***' in out and KEY not in out


@posixOnly
def test_files_already_on_disk_become_private(tmp_path):
    (tmp_path / 'log').mkdir()
    (tmp_path / 'debug').mkdir()
    exposed = [tmp_path / 'log' / 'botfarm.log', tmp_path / 'log' / 'botfarm.log.2',
               tmp_path / 'log' / 'log-01.11.2026-10.00.00.log',
               tmp_path / 'debug' / 'opiumpulses-enter-unconfirmed.html']
    other = tmp_path / 'log' / 'notes.txt'
    for path in exposed + [other]:
        path.write_text('x', encoding='utf-8')
        os.chmod(path, 0o644)
    assert farmMain.protectFiles(tmp_path) == len(exposed)
    assert all(mode(path) == 0o600 for path in exposed)
    assert mode(other) == 0o644
    assert farmMain.protectFiles(tmp_path) == 0


@posixOnly
def test_opiumpulses_debug_page_is_private(manager, openUmask):  # noqa: F811
    platform = manager.platforms['opiumpulses']
    path = manager.dataDir / 'debug' / 'opiumpulses-listing.html'
    path.parent.mkdir()
    path.write_text('old', encoding='utf-8')
    os.chmod(path, 0o644)
    platform.keepForDebugging('listing', '<html>signed in</html>')
    assert path.read_text(encoding='utf-8') == '<html>signed in</html>'
    assert mode(path) == 0o600
    platform.keepForDebugging('new', '<html/>')
    assert mode(path.parent / 'opiumpulses-new.html') == 0o600


# ---- old command line logs ---------------------------------------------------------

def ageFile(path, days):
    moment = time.time() - days * 86400
    os.utime(path, (moment, moment))


def oldLogs(logDir):
    logDir.mkdir(exist_ok=True)
    files = {
        'old': logDir / 'log-01.09.2026-10.00.00.log',
        'oldRotated': logDir / 'log-01.09.2026-10.00.00.log.1',
        'fresh': logDir / 'log-15.11.2026-10.00.00.log',
        'farm': logDir / 'botfarm.log',
        'farmRotated': logDir / 'botfarm.log.3',
    }
    files['old'].write_text("[INFO:2026-09-01 10:00:05,123] One more game Alpha\n"
                            "[INFO:2026-09-01 10:05:05,123] One more game Beta\n",
                            encoding='utf-8')
    for name in ('oldRotated', 'fresh', 'farm', 'farmRotated'):
        files[name].write_text('x\n', encoding='utf-8')
    for name in ('old', 'oldRotated', 'farm', 'farmRotated'):
        ageFile(files[name], 45)
    ageFile(files['fresh'], 5)
    return files


def test_old_cli_logs_go_after_the_history_import(tmp_path):
    files = oldLogs(tmp_path / 'log')
    farm = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'none.ini')
    # The import read the old file before anything was deleted.
    assert farm.state.site('steamgifts')['totalEntered'] == 2
    assert farm.pruneCliLogs() == 2
    assert not files['old'].exists() and not files['oldRotated'].exists()
    assert files['fresh'].exists()
    # The farm's own log is never touched, however old.
    assert files['farm'].exists() and files['farmRotated'].exists()


def test_cli_logs_stay_until_the_history_is_imported(tmp_path, monkeypatch):
    files = oldLogs(tmp_path / 'log')
    # The import did not happen (it failed, or this is a build without it).
    monkeypatch.setattr(FarmManager, 'importCliHistory', lambda self: None)
    farm = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'none.ini')
    assert not farm.state.flag('steamgifts', 'cli_imported')
    assert farm.pruneCliLogs() == 0
    assert all(path.exists() for path in files.values())
    # Once it has run, the next start cleans up.
    monkeypatch.undo()
    farm.importCliHistory()
    assert farm.state.flag('steamgifts', 'cli_imported')
    assert farm.pruneCliLogs() == 2


def test_farm_start_prunes_after_import(tmp_path, monkeypatch, farmLogger):
    order = []
    realImport, realPrune = FarmManager.importCliHistory, FarmManager.pruneCliLogs
    monkeypatch.setattr(FarmManager, 'importCliHistory',
                        lambda self: order.append('import') or realImport(self))
    monkeypatch.setattr(FarmManager, 'pruneCliLogs',
                        lambda self: order.append('prune') or realPrune(self))
    # Stop main() right after the start-up work, before it serves anything.
    monkeypatch.setattr(farmMain, 'startLogFile', lambda *args: None)

    class Stop(Exception):
        pass

    def stop(self):
        raise Stop
    monkeypatch.setattr(FarmManager, 'hasPassword', stop)
    files = oldLogs(tmp_path / 'log')
    with pytest.raises(Stop):
        farmMain.main(['--data', str(tmp_path), '--no-autostart'])
    assert order == ['import', 'prune']
    assert not files['old'].exists() and files['farm'].exists()


def test_lines_restored_from_an_old_log_are_masked(manager):  # noqa: F811
    # botfarm.log written before the fix still has the key in it.
    (manager.dataDir / 'log').mkdir(exist_ok=True)
    (manager.dataDir / 'log' / 'botfarm.log').write_text(
        "[WARNING 2026-11-20 10:05:00,001 botfarm.indiegala] Ошибка: 500 for url: "
        f"https://x/?api_key={KEY}&page=1\n", encoding='utf-8')
    assert manager.restoreLogs() == 1
    text = manager.platforms['indiegala'].logLines()[-1]['text']
    assert KEY not in text and 'api_key=***&page=1' in text


def test_telegram_cards_and_the_panel_mask_secrets_in_error_texts(manager):  # noqa: F811
    from steamgiftbot.farm import cards
    error = ("HTTPSConnectionPool: Max retries exceeded with url: "
             "/IPlayerService/GetOwnedGames/v1/?key=ABCDEF0123456789&steamid=1")
    card = manager.translateCard(cards.Card('⚠️', headline='x', lines=[error], block=[error]))
    assert 'ABCDEF0123456789' not in card.html() and 'key=***' in card.html()
    platform = manager.platforms['indiegala']
    platform.lastError = error
    assert 'ABCDEF0123456789' not in platform.snapshot()['error']
