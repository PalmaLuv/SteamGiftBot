"""The farm's files survive a crash or a broken write, its settings survive
changes made at the same moment, and the panel copes with bad or slow
clients."""
import hashlib
import hmac
import http.client
import json
import logging
import os
import pathlib
import select
import shutil
import socket
import subprocess
import threading
import time

import pytest

from test_farm import call, manager, panel  # noqa: F401

from steamgiftbot.farm import __main__ as farmMain
from steamgiftbot.farm import manager as managerModule
from steamgiftbot.farm import web
from steamgiftbot.farm.manager import (DataFileError, FarmManager, FarmState, readJSON,
                                       writePrivate)

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---- writing files ---------------------------------------------------------------

def test_write_private_syncs_and_keeps_a_backup(tmp_path, monkeypatch):
    synced = []
    realSync = os.fsync
    monkeypatch.setattr(managerModule.os, 'fsync', lambda fd: (synced.append(fd), realSync(fd)))
    path = tmp_path / 'farm.json'
    writePrivate(path, {'n': 1})
    writePrivate(path, {'n': 2})
    assert json.loads(path.read_text(encoding='utf-8')) == {'n': 2}
    assert json.loads((tmp_path / 'farm.json.bak').read_text(encoding='utf-8')) == {'n': 1}
    # The file and its directory, on both writes. Windows cannot open a
    # directory to sync it, so there only the file is.
    assert len(synced) >= (4 if os.name != 'nt' else 2)
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('*.tmp'))


# ---- reading a broken file -------------------------------------------------------

def test_truncated_farm_file_falls_back_to_the_backup(tmp_path, caplog):
    path = tmp_path / 'farm.json'
    writePrivate(path, {'settings': {'timezone': 'Europe/Moscow'}, 'web': {}, 'platforms': {}})
    writePrivate(path, {'settings': {'timezone': 'Europe/Kyiv'}, 'web': {}, 'platforms': {}})
    whole = path.read_text(encoding='utf-8')
    path.write_text(whole[:len(whole) // 2], encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger='botfarm'):
        farm = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    # The last good copy, not an empty farm.
    assert farm.farmSettings()['timezone'] == 'Europe/Moscow'
    aside = list(tmp_path.glob('farm.json.corrupt-*'))
    assert len(aside) == 1 and aside[0].read_text(encoding='utf-8') == whole[:len(whole) // 2]
    assert json.loads(path.read_text(encoding='utf-8'))['settings']['timezone'] == \
        'Europe/Moscow'
    assert any('резервной копии' in record.getMessage() for record in caplog.records)


def test_broken_file_without_backup_is_kept_aside(tmp_path, caplog):
    path = tmp_path / 'botfarm-state.json'
    path.write_text('{"indiegala": {"entries": [', encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger='botfarm'):
        state = FarmState(path)
    assert state.data == {}
    state.markSeen('indiegala', 'abc')
    # Saving the fresh state did not destroy the broken one.
    aside = list(tmp_path.glob('botfarm-state.json.corrupt-*'))
    assert len(aside) == 1
    assert aside[0].read_text(encoding='utf-8') == '{"indiegala": {"entries": ['
    assert caplog.records


def test_file_of_the_wrong_shape_counts_as_broken(tmp_path):
    path = tmp_path / 'farm.json'
    path.write_text('[1, 2]', encoding='utf-8')
    assert readJSON(path, {}) == {}
    assert list(tmp_path.glob('farm.json.corrupt-*'))


def test_broken_files_in_one_second_are_all_kept(tmp_path, monkeypatch):
    # Two quick restarts with a broken file each: the second used to be put
    # over the first, both named after the same second.
    monkeypatch.setattr(managerModule.time, 'time', lambda: 1_790_000_000.25)
    path = tmp_path / 'botfarm-state.json'
    for text in ('{"first": ', '{"second": '):
        path.write_text(text, encoding='utf-8')
        assert readJSON(path, {}) == {}
    aside = sorted(tmp_path.glob('botfarm-state.json.corrupt-*'))
    assert len(aside) == 2
    assert {item.read_text(encoding='utf-8') for item in aside} == {'{"first": ', '{"second": '}


def test_unreadable_file_stops_the_farm_instead_of_starting_empty(tmp_path, monkeypatch):
    path = tmp_path / 'farm.json'
    writePrivate(path, {'settings': {'timezone': 'Europe/Moscow'}, 'web': {}, 'platforms': {}})
    writePrivate(path, {'settings': {'timezone': 'Europe/Kyiv'}, 'web': {}, 'platforms': {}})
    before = {item.name: item.read_bytes() for item in tmp_path.iterdir()}
    realRead = pathlib.Path.read_text

    def denied(self, *args, **kwargs):
        if self.name == 'farm.json':
            raise PermissionError(13, 'Permission denied', str(self))
        return realRead(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'read_text', denied)
    # Starting empty used to make the good file the backup on the first save
    # and write the empty farm over that backup on the second.
    with pytest.raises(DataFileError, match='Permission denied'):
        FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    assert {item.name: item.read_bytes() for item in tmp_path.iterdir()} == before


def test_warning_about_a_broken_file_reaches_the_farm_log(tmp_path):
    path = tmp_path / 'farm.json'
    writePrivate(path, {'settings': {'timezone': 'Europe/Moscow'}, 'web': {}, 'platforms': {}})
    writePrivate(path, {'settings': {'timezone': 'Europe/Kyiv'}, 'web': {}, 'platforms': {}})
    path.write_text('{"settings": ', encoding='utf-8')
    farmLogger = logging.getLogger('botfarm')
    saved = (list(farmLogger.handlers), farmLogger.level, farmLogger.propagate)
    try:
        # The file is read before the log is set up; the warning used to go
        # to the journal only, never to log/botfarm.log.
        farm = farmMain.openFarm(tmp_path, tmp_path / 'config.ini')
        for handler in farmLogger.handlers:
            handler.flush()
        text = (tmp_path / 'log' / 'botfarm.log').read_text(encoding='utf-8')
    finally:
        for handler in farmLogger.handlers:
            if handler not in saved[0]:
                handler.close()
        farmLogger.handlers[:] = saved[0]
        farmLogger.setLevel(saved[1])
        farmLogger.propagate = saved[2]
    assert farm.farmSettings()['timezone'] == 'Europe/Moscow'
    assert 'данные взяты из резервной копии' in text


@pytest.mark.skipif(shutil.which('git') is None or not (ROOT / '.git').exists(),
                    reason="нужен git-checkout")
def test_backups_of_the_data_files_stay_out_of_git():
    # They hold the same secrets as farm.json: a 'git add -A' in the live
    # checkout must not pick them up.
    names = ['farm.json.bak', 'botfarm-state.json.bak', 'farm.json.corrupt-20261120-101010-123',
             'botfarm-state.json.corrupt-20261120-101010-123-2', 'farm.json.tmp']
    for name in names:
        result = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', '--no-index', name],
                                capture_output=True)
        assert result.returncode == 0, name
    docker = (ROOT / '.dockerignore').read_text(encoding='utf-8').split()
    for pattern in ('farm.json', 'botfarm-state.json', '*.bak', '*.corrupt-*'):
        assert pattern in docker


def test_missing_file_is_a_first_run(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger='botfarm'):
        assert readJSON(tmp_path / 'farm.json', {}) == {}
    assert not caplog.records
    assert not list(tmp_path.iterdir())


# ---- changes at the same moment ----------------------------------------------------

def test_blacklist_words_added_at_once_are_all_kept(manager, monkeypatch):  # noqa: F811
    gala = manager.platforms['indiegala']
    assert 'blacklist' in gala.quickLists()
    # A pause right after the settings are read, so that without one lock
    # over the read and the save every thread starts from the same list and
    # words are lost every time, not only when the scheduler happens to switch.
    realRead = manager.platformSettings

    def slowRead(key):
        stored = realRead(key)
        time.sleep(0.005)
        return stored

    monkeypatch.setattr(manager, 'platformSettings', slowRead)
    words = [f"Game {thread} {number}" for thread in range(8) for number in range(4)]
    start = threading.Barrier(8)
    problems = []

    def add(thread):
        start.wait()
        try:
            for number in range(4):
                gala.addToList('blacklist', f"Game {thread} {number}")
        except Exception as error:
            problems.append(error)

    threads = [threading.Thread(target=add, args=(thread,)) for thread in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not problems
    assert sorted(gala.settings()['blacklist']) == sorted(words)
    again = FarmManager(dataDir=manager.dataDir, configPath=manager.configPath)
    assert sorted(again.platforms['indiegala'].settings()['blacklist']) == sorted(words)


def test_farm_is_saved_from_a_copy(manager, monkeypatch):  # noqa: F811
    written = []
    monkeypatch.setattr(managerModule, 'writePrivate', lambda path, data: written.append(data))
    manager.setAutostart('gog', True)
    # What is written is a copy taken under the lock, not the live dict
    # another thread may be changing while it is dumped.
    assert written and written[-1] is not manager.farm
    assert written[-1]['platforms']['gog']['autostart'] is True
    manager.farm['platforms']['gog']['autostart'] = False
    assert written[-1]['platforms']['gog']['autostart'] is True


def test_state_site_is_made_under_the_lock(tmp_path):
    # With the GIL a lone setdefault rarely loses, so check the lock itself:
    # a new site's record waits while another thread is changing the state.
    state = FarmState(tmp_path / 'state.json')
    made = threading.Event()
    with state.lock:
        thread = threading.Thread(target=lambda: (state.site('gog'), made.set()))
        thread.start()
        assert not made.wait(0.3)
    assert made.wait(5)
    thread.join()


# ---- the panel -----------------------------------------------------------------------

def signIn(panel):  # noqa: F811
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    return headers['Set-Cookie'].split(';')[0]


def test_logout_revokes_the_cookie(panel, manager):  # noqa: F811
    mine, other = signIn(panel), signIn(panel)
    assert call(panel + '/api/status', cookie=mine)[0] == 200
    assert call(panel + '/api/logout', {}, cookie=mine)[0] == 200
    # A copy of the cookie kept after signing out no longer works...
    assert call(panel + '/api/status', cookie=mine)[0] == 401
    # ...and neither after a restart; another device stays signed in.
    again = FarmManager(dataDir=manager.dataDir, configPath=manager.configPath)
    revoked = again.revokedSessions()
    assert not web.tokenValid(again.sessionSecret(), mine.split('=', 1)[1], revoked)
    assert web.tokenValid(again.sessionSecret(), other.split('=', 1)[1], revoked)
    assert call(panel + '/api/status', cookie=other)[0] == 200


def test_old_style_cookie_still_reads():
    secret = 'k' * 64
    expires = str(int(time.time()) + 60)
    legacy = f"{expires}." + hmac.new(secret.encode(), expires.encode(),
                                       hashlib.sha256).hexdigest()
    assert web.tokenValid(secret, legacy)
    assert not web.tokenValid(secret, legacy, {legacy.split('.')[1]: int(expires)})
    assert not web.tokenValid(secret, 'garbage')


def rawPost(panel, length, body=b''):  # noqa: F811
    host, port = panel.rsplit('/', 1)[1].split(':')
    connection = http.client.HTTPConnection(host, int(port), timeout=5)
    connection.putrequest('POST', '/api/login')
    connection.putheader('X-Requested-With', 'BotFarm')
    connection.putheader('Content-Length', length)
    connection.endheaders(body)
    response = connection.getresponse()
    data = json.loads(response.read() or b'{}')
    connection.close()
    return response.status, data


def test_bad_content_length_is_refused(panel):  # noqa: F811
    # A negative length used to make the server read until the client hung up.
    assert rawPost(panel, '-5')[0] == 400
    status, data = rawPost(panel, 'abc')
    assert status == 400 and 'invalid literal' not in data['error']


def test_slow_client_is_dropped(panel, monkeypatch):  # noqa: F811
    # Without a timeout of its own the handler waited forever.
    assert web.Handler.timeout is not None and 0 < web.Handler.timeout <= 60
    # The same mechanism, quicker for the test.
    monkeypatch.setattr(web.Handler, 'timeout', 0.5)
    host, port = panel.rsplit('/', 1)[1].split(':')
    client = socket.create_connection((host, int(port)), timeout=5)
    # Half a request, then silence.
    client.sendall(b'POST /api/login HTTP/1.1\r\nHost: x\r\nX-Requested-With: BotFarm\r\n'
                   b'Content-Length: 100\r\n\r\n{"pass')
    try:
        assert client.recv(1024) == b''
    finally:
        client.close()


def test_trickling_client_is_dropped_at_the_deadline(panel, monkeypatch):  # noqa: F811
    # A byte every 0.2 s never trips the per-recv timeout; the whole request
    # still has to arrive within the deadline.
    monkeypatch.setattr(web.Handler, 'deadline', 1.0)
    assert web.Handler.timeout > 1
    host, port = panel.rsplit('/', 1)[1].split(':')
    client = socket.create_connection((host, int(port)), timeout=5)
    request = (b'POST /api/login HTTP/1.1\r\nHost: x\r\nX-Requested-With: BotFarm\r\n'
               b'Content-Length: 100\r\n\r\n' + b'x' * 100)
    started = time.monotonic()
    dropped = False
    try:
        for byte in request:
            readable, _, _ = select.select([client], [], [], 0.2)
            if readable:
                dropped = client.recv(1024) == b''
                break
            try:
                client.sendall(bytes([byte]))
            except OSError:
                dropped = True
                break
    finally:
        client.close()
    assert dropped
    assert time.monotonic() - started < 5


def test_request_cut_into_pieces_still_reads_whole(panel):  # noqa: F811
    # Lines and the body split across many recvs are put back together.
    host, port = panel.rsplit('/', 1)[1].split(':')
    client = socket.create_connection((host, int(port)), timeout=5)
    body = json.dumps({'password': 'secret123'}).encode()
    request = (b'POST /api/login HTTP/1.1\r\nHost: x\r\nX-Requested-With: BotFarm\r\n'
               b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
    try:
        for start in range(0, len(request), 7):
            client.sendall(request[start:start + 7])
            time.sleep(0.005)
        answer = b''
        while chunk := client.recv(4096):
            answer += chunk
    finally:
        client.close()
    assert answer.startswith(b'HTTP/1.0 200') and b'botfarm_session=' in answer


def test_bad_after_in_logs_is_not_a_crash(panel):  # noqa: F811
    cookie = signIn(panel)
    status, data, _ = call(panel + '/api/platforms/indiegala/logs?after=abc', cookie=cookie)
    assert status == 200 and 'lines' in data


def test_internal_error_text_stays_in_the_log(panel, manager, monkeypatch, caplog):  # noqa: F811
    cookie = signIn(panel)

    def broken(values):
        raise RuntimeError('/home/someone/secret-path')

    monkeypatch.setattr(manager, 'updateUi', broken)
    with caplog.at_level(logging.ERROR, logger='botfarm'):
        status, data, _ = call(panel + '/api/ui', {'values': {}}, cookie=cookie)
    assert status == 500
    assert 'secret-path' not in json.dumps(data) and 'RuntimeError' not in json.dumps(data)
    assert any('secret-path' in (record.exc_text or '') or record.exc_info
               for record in caplog.records)


def test_held_lines_reach_the_log_when_the_start_breaks_otherwise(tmp_path, monkeypatch):
    path = tmp_path / 'farm.json'
    writePrivate(path, {'settings': {}, 'web': {}, 'platforms': {}})
    writePrivate(path, {'settings': {}, 'web': {}, 'platforms': {}})
    path.write_text('{"settings": ', encoding='utf-8')

    def broken(self):
        raise RuntimeError('boom')
    monkeypatch.setattr(farmMain.FarmManager, 'restoreLogs', broken)
    farmLogger = logging.getLogger('botfarm')
    saved = (list(farmLogger.handlers), farmLogger.level, farmLogger.propagate)
    try:
        with pytest.raises(RuntimeError):
            farmMain.openFarm(tmp_path, tmp_path / 'config.ini')
        for handler in farmLogger.handlers:
            handler.flush()
        text = (tmp_path / 'log' / 'botfarm.log').read_text(encoding='utf-8')
    finally:
        for handler in farmLogger.handlers:
            if handler not in saved[0]:
                handler.close()
        farmLogger.handlers[:] = saved[0]
        farmLogger.setLevel(saved[1])
        farmLogger.propagate = saved[2]
    assert 'данные взяты из резервной копии' in text
