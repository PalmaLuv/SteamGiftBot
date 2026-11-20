"""The farm's later additions: Telegram commands, ArchiSteamFarm, the free game
sources, presets, connection checks, history search and won keys."""
import json
import time

import pytest
import requests

from test_farm import FakeIndieGala, at, call, indiegala, manager, panel  # noqa: F401

from steamgiftbot import settings as sgSettings
from steamgiftbot.farm import asf as asfModule
from steamgiftbot.farm import gog, itch, rules, steamfree
from steamgiftbot.farm.telegram import TelegramControl


def answer(body, status=200, url='https://x/'):
    response = requests.models.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.url = url
    return response


# ---- Telegram commands -----------------------------------------------------------

class FakeTelegram:
    def __init__(self):
        self.sent = []

    def post(self, url, json=None, timeout=None):
        if url.endswith('/sendMessage'):
            self.sent.append(json)
        return answer({'ok': True, 'result': []})


def test_telegram_commands(manager):  # noqa: F811
    control = TelegramControl(manager, session=FakeTelegram())
    gala = manager.platforms['indiegala']
    settings = gala.settings()
    settings.update(cookie='auth=1')
    manager.savePlatformSettings('indiegala', settings)
    assert 'IndieGala' in control.handle('/status')
    assert 'SteamGifts' in control.handle('/status@MyBot')
    assert '/pause' in control.handle('/help')
    assert 'Не знаю площадку' in control.handle('/start nosuch')
    assert control.handle('hello') is None
    assert 'Не знаю такой команды' in control.handle('/dance')
    assert control.findSites('ind') == [gala]
    gala.run = lambda: gala.wait(3600)
    assert 'IndieGala' in control.handle('/start indiegala')
    assert gala.running
    assert 'Остановлено: IndieGala' in control.handle('/pause indiegala')
    gala.thread.join(5)


def test_telegram_answers_only_its_chat(manager):  # noqa: F811
    session = FakeTelegram()
    control = TelegramControl(manager, session=session)
    update = {'update_id': 1, 'message': {'chat': {'id': 555}, 'text': '/help'}}
    assert control.process('T', '777', update) is None
    assert session.sent == []
    assert control.process('T', '555', update)
    assert session.sent[0]['chat_id'] == '555'


def test_telegram_settings_live_in_config_ini(manager):  # noqa: F811
    manager.updateFarmSettings({'telegram_token': '123456789:' + 'A' * 35,
                                'telegram_chat': '987654321', 'telegram_commands': True})
    config = sgSettings.load(manager.configPath)
    assert config.telegram_chat == '987654321'
    values = manager.farmSettings()
    assert values['telegram_commands'] and values['telegram_token'].startswith('123456789:')
    assert manager.publicFarmSettings()['telegram_token'] is True
    assert 'telegram_token' not in manager.farm['settings']


# ---- ArchiSteamFarm -------------------------------------------------------------

class FakeASF:
    def __init__(self, detail=0, status=1, online=True):
        self.detail, self.status, self.online, self.calls = detail, status, online, []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json, headers))
        if url.endswith('/Api/Bot/ASF'):
            return answer({'Success': True, 'Result': {
                'Main Bot': {'BotName': 'Main Bot', 'IsConnectedAndLoggedOn': self.online}}})
        if url.endswith('/Redeem'):
            key = json['KeysToRedeem'][0]
            return answer({'Success': True, 'Result': {'Main Bot': {key: {
                'purchase_result_details': self.detail,
                'purchase_receipt_info': {'purchase_status': self.status, 'line_items': [
                    {'line_item_description': 'Hollow Pact'}]}}}}})
        if url.endswith('/AddLicense'):
            return answer({'Success': True, 'Result': {'Main Bot': {
                'Apps': {str(a): {'Result': 1, 'PurchaseResultDetail': 0} for a in json['Apps']},
                'Packages': {str(p): {'Result': 2, 'PurchaseResultDetail': 9}
                             for p in json['Packages']}}}})
        return answer({}, 404)


def test_asf_outcomes():
    assert asfModule.outcome(None)[0] == 'retry'
    assert asfModule.outcome({'purchase_receipt_info': {'purchase_status': 1}})[0] == 'ok'
    owned = {'purchase_result_details': 9, 'purchase_receipt_info': {'purchase_status': 2}}
    assert asfModule.outcome(owned) == ('owned', 'уже есть в библиотеке')
    limited = {'purchase_result_details': 53, 'purchase_receipt_info': {'purchase_status': 2}}
    assert asfModule.outcome(limited)[0] == 'retry'
    bad = {'purchase_result_details': 14, 'purchase_receipt_info': {'purchase_status': 2}}
    assert asfModule.outcome(bad) == ('fail', 'неверный ключ')


def test_asf_redeem_uses_password_and_online_bot(manager, tmp_path):  # noqa: F811
    config = tmp_path / 'ASF.json'
    config.write_text('{"IPCPassword": "pw"}')
    manager.asf.session = fake = FakeASF()
    manager.updateFarmSettings({'asf_password': 'secret'})
    assert manager.asf.redeem('AAAAA-BBBBB-CCCCC') == ('ok', 'активирован: Hollow Pact')
    method, url, body, headers = fake.calls[-1]
    assert url.endswith('/Api/Bot/Main%20Bot/Redeem') and headers == {'Authentication': 'secret'}
    assert asfModule.localPassword(config) == 'pw'
    fake.online = False
    with pytest.raises(ValueError):
        manager.asf.redeem('AAAAA-BBBBB-CCCCC')


def test_asf_errors_are_plain(manager):  # noqa: F811
    class Down:
        def request(self, *a, **k):
            raise requests.ConnectionError('refused')
    manager.asf.session = Down()
    with pytest.raises(ValueError, match='ASF недоступен'):
        manager.asf.check()


def test_win_key_and_redeem(manager):  # noqa: F811
    manager.asf.session = FakeASF()
    manager.notify = lambda text: []
    gala = manager.platforms['indiegala']
    gala.recordWin('Hollow Pact', 'https://x/')
    win = manager.openWins()[0]
    assert manager.setWinKey('indiegala', win['time'], 'Hollow Pact', ' aaaaa-bbbbb-ccccc ') == \
        'AAAAA-BBBBB-CCCCC'
    assert manager.openWins()[0]['cdkey'] == 'AAAAA-BBBBB-CCCCC'
    assert manager.redeemWin('indiegala', win['time'], 'Hollow Pact')[0] == 'ok'
    assert manager.openWins() == []
    stored = manager.state.findWin('indiegala', win['time'], 'Hollow Pact')
    assert stored['status'] == 'activated' and stored['redeem'].startswith('активирован')


def test_auto_redeem_on_new_key(manager):  # noqa: F811
    manager.asf.session = fake = FakeASF(detail=9, status=2)
    manager.notify = lambda text: []
    manager.updateFarmSettings({'auto_redeem': True})
    manager.platforms['indiegala'].recordWin('Old Game')
    win = manager.openWins()[0]
    manager.setWinKey('indiegala', win['time'], 'Old Game', 'AAAAA-BBBBB-CCCCC')
    assert any(url.endswith('/Redeem') for _m, url, _b, _h in fake.calls)
    assert manager.openWins() == []


# ---- free game sources ------------------------------------------------------------

def test_steam_free_feed_and_pass(manager, monkeypatch):  # noqa: F811
    assert steamfree.parseFeed("a/10\ns/20\njunk\na/10\n") == [('app', 10), ('sub', 20)]
    platform = manager.platforms['steamfree']
    assert not platform.configured()
    monkeypatch.setattr(platform, 'feed', lambda: [('app', 10), ('sub', 20), ('app', 30)])
    names = {10: 'Free Game', 20: 'Pack', 30: 'Some Soundtrack'}
    monkeypatch.setattr(platform, 'appName', lambda kind, ident: names[ident])
    manager.asf.session = FakeASF()
    conf = platform.settings()
    conf['skip_junk'] = True
    assert platform.cycle(conf) == 1
    assert [e['name'] for e in manager.state.site('steamfree')['entries']] == ['Free Game']
    seen = manager.state.seen('steamfree')
    assert {'app/10', 'sub/20', 'app/30'} <= seen
    assert platform.candidates(conf) == []


def test_steam_free_connects_through_asf(manager):  # noqa: F811
    manager.asf.session = FakeASF()
    assert manager.platforms['steamfree'].check({})['account'] == 'Main Bot'
    manager.asf.session = FakeASF(online=False)
    with pytest.raises(ValueError, match='ни один бот'):
        manager.platforms['steamfree'].check({})


def test_gog_name_and_claim(manager):  # noqa: F811
    html = '<div class="giveaway__content-header">Claim Tiny Farm and don\'t miss</div>'
    assert gog.giveawayName(html) == 'Tiny Farm'
    assert gog.giveawayName('<p>nothing</p>') == ''
    platform = manager.platforms['gog']

    class Site:
        def __init__(self, body, status=200):
            self.body, self.status = body, status

        def get(self, url, timeout=None):
            return answer(self.body, self.status)
    platform.session = Site({})
    assert platform.claim()[0] == 'claimed'
    platform.session = Site({'message': 'Already claimed'})
    assert platform.claim()[0] == 'already'
    platform.session = Site({'message': 'Giveaway has ended'})
    assert platform.claim()[0] == 'none'
    platform.session = Site({'message': 'Unauthorized'}, 401)
    with pytest.raises(base_auth_error()):
        platform.claim()


def base_auth_error():
    from steamgiftbot.farm.base import AuthError
    return AuthError


def test_itch_active_sales_and_filters(manager):  # noqa: F811
    now = 1_000_000
    data = [{'id': 1, 'name': 'Free Game', 'url': 'https://a.itch.io/g', 'claimable': True,
             'sales': [{'start': now - 10, 'end': now + 10}]},
            {'id': 2, 'name': 'Over', 'url': 'https://a.itch.io/o', 'claimable': True,
             'sales': [{'start': now - 20, 'end': now - 10}]},
            {'id': 3, 'name': 'Paid', 'url': 'https://a.itch.io/p', 'claimable': False}]
    assert itch.activeSales(data, now) == [('1', 'Free Game', 'https://a.itch.io/g')]
    platform = manager.platforms['itch']
    conf = platform.settings()
    conf.update(blacklist=['demo'], skip_adult=True)
    assert platform.skipReason(conf, 'Demo Land', set(), '9') == 'в чёрном списке'
    assert platform.skipReason(conf, 'Hentai Quest', set(), '9') == '18+'
    assert platform.skipReason(conf, 'Fine', {'9'}, '9') == 'уже в библиотеке'
    assert platform.skipReason(conf, 'Fine', set(), '9') is None


def test_itch_needs_its_session_cookie(manager):  # noqa: F811
    with pytest.raises(ValueError, match='itchio'):
        manager.platforms['itch'].check({'cookie': 'other=1'})


# ---- catalog, presets, connecting ---------------------------------------------------

def test_presets_only_touch_known_fields(manager):  # noqa: F811
    gala = manager.platforms['indiegala']
    names = [preset['name'] for preset in gala.presets()]
    assert names == ['balanced', 'economy', 'maximum', 'games']
    gala.applyPreset('economy')
    conf = gala.settings()
    assert conf['sort'] == 'smart' and conf['reserve'] == 20 and conf['skip_adult']
    opium = {p['name']: p['values'] for p in manager.platforms['opiumpulses'].presets()}
    assert 'sort' not in opium['economy'] and opium['economy']['free_only'] is True
    with pytest.raises(ValueError):
        gala.applyPreset('nope')


def test_indiegala_check_and_disconnect(manager, monkeypatch):  # noqa: F811
    site = FakeIndieGala(silver=7)
    gala, _ = indiegala(manager, site)
    monkeypatch.setattr(type(gala), 'connect', lambda self, conf: setattr(self, 'session', site))
    assert gala.check({'cookie': 'sessionid=1'}) == {'account': 'tester', 'balance': 7}
    with pytest.raises(ValueError):
        gala.check({'cookie': 'nocookie'})
    manager.setAutostart('indiegala', True)
    gala.disconnect()
    assert not gala.configured() and not manager.autostart('indiegala')


def test_guides_for_every_site(manager):  # noqa: F811
    for platform in manager.platforms.values():
        steps = platform.guide()
        assert len(steps) >= 3 and all(step['title'] and step['text'] for step in steps)
        assert platform.category in ('points', 'free')


def test_steamgifts_takes_the_session_from_curl(manager):  # noqa: F811
    steam = manager.platforms['steamgifts']
    steam.updateSettings({'cookie': "curl 'https://www.steamgifts.com/' -H 'cookie: a=1; "
                                    "PHPSESSID=abcdef123; b=2'"})
    assert sgSettings.load(manager.configPath).cookie == 'abcdef123'


# ---- history and wishlist -----------------------------------------------------------

def test_history_search_pages_and_csv(manager):  # noqa: F811
    gala = manager.platforms['indiegala']
    for number in range(60):
        gala.recordEntry(f'Game {number}', 1, f'https://x/{number}')
    manager.platforms['steamgifts'].recordEntry('Other "quoted"', 5)
    page = manager.historyPage(page=2)
    assert page['total'] == 61 and page['pages'] == 2 and len(page['rows']) == 11
    # every word must match: 'Game 5', 'Game 15' … 'Game 59'
    assert manager.historyPage(query='game 5')['total'] == 15
    assert manager.historyPage(site='steamgifts')['rows'][0]['title'] == 'SteamGifts'
    csv = manager.historyCSV(site='steamgifts')
    assert csv.startswith('﻿Когда;') and '"Other ""quoted"""' in csv
    with pytest.raises(ValueError):
        manager.historyPage(kind='bad')


class FakeWishlist:
    def get(self, url, params=None, timeout=None):
        return answer({'response': {'items': [{'appid': 703530, 'priority': 1}]}})


def test_wishlist_goes_first_on_indiegala(manager):  # noqa: F811
    library = rules.SteamLibrary(session=FakeWishlist())
    assert library.wishlist('', '76561198000000001') == {703530}
    manager.steam = library
    manager.updateFarmSettings({'wishlist_first': True, 'steam_profile': '76561198000000001'})
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site)
    platform.cycle(conf)
    # 703530 is the 4 iS ticket; on the wishlist it goes first even in expiry order.
    assert site.joined[0] == '1217743'


# ---- panel ------------------------------------------------------------------------

def test_panel_static_files_and_new_routes(panel, manager):  # noqa: F811
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    with urllib_get(panel + '/manifest.webmanifest') as response:
        assert json.loads(response.read())['short_name'] == 'Бот-ферма'
    manager.platforms['indiegala'].recordEntry('A', 1)
    status, data, _ = call(panel + '/api/history?kind=entries&site=indiegala', cookie=cookie)
    assert status == 200 and data['rows'][0]['name'] == 'A'
    status, data, _ = call(panel + '/api/platforms/indiegala/settings', cookie=cookie)
    assert data['guide'] and data['connectFields'] == ['cookie'] and data['presets']
    status, data, _ = call(panel + '/api/platforms/indiegala/preset', {'name': 'games'},
                           cookie=cookie)
    assert status == 200 and data['title'] == 'Только игры'
    status, data, _ = call(panel + '/api/platforms/indiegala/check', {'values': {'cookie': ''}},
                           cookie=cookie)
    assert status == 400
    status, data, _ = call(panel + '/api/platforms/steamfree/settings',
                           {'values': {}, 'connect': True}, cookie=cookie)
    assert status == 200 and manager.platforms['steamfree'].configured()


def urllib_get(url):
    import urllib.request
    return urllib.request.urlopen(url)


def test_daily_report_reminds_about_unmarked_wins(manager):  # noqa: F811
    manager.platforms['steamgifts'].recordWin('Prize')
    assert 'Не отмечено, что ключ получен: 1' in manager.report(now=time.time())
    assert at(8).hour == 8


# ---- settings page helpers ----------------------------------------------------------

def test_settings_info_and_helpers(manager, monkeypatch):  # noqa: F811
    info = manager.settingsInfo()
    assert 'Europe/Kyiv' in info['zones'] and not any(z.startswith('Etc/') for z in info['zones'])
    assert info['zone'] == 'Europe/Kyiv'
    with pytest.raises(ValueError, match='токен'):
        manager.telegramChats()
    from steamgiftbot import notify
    monkeypatch.setattr(notify, 'findChats', lambda token: [{'id': 5, 'type': 'private',
                                                             'first_name': 'Me'}])
    assert manager.telegramChats('123:abc') == [{'id': '5', 'title': 'Me', 'type': 'private'}]
    with pytest.raises(ValueError, match='профиль'):
        manager.steamCheck()
    manager.steam = rules.SteamLibrary(session=FakeWishlist())
    manager.updateFarmSettings({'steam_profile': '76561198000000001'})
    assert 'в списке желаемого 1' in manager.steamCheck()


def test_panel_logout_everywhere(panel, manager):  # noqa: F811
    _, _, first = call(panel + '/api/login', {'password': 'secret123'})
    old = first['Set-Cookie'].split(';')[0]
    _, _, second = call(panel + '/api/login', {'password': 'secret123'})
    mine = second['Set-Cookie'].split(';')[0]
    status, data, headers = call(panel + '/api/logout-all', {}, cookie=mine)
    assert status == 200
    assert call(panel + '/api/status', cookie=old)[0] == 401
    assert call(panel + '/api/status', cookie=headers['Set-Cookie'].split(';')[0])[0] == 200
    status, data, _ = call(panel + '/api/farm/settings', cookie=headers['Set-Cookie'].split(';')[0])
    assert 'Europe/Kyiv' in data['info']['zones']
