"""The bot farm: site parsers, one IndieGala pass against a fake site, the
state file, and the web panel's sign-in rules."""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from conftest import fixture

from steamgiftbot.farm import base, rules, web
from steamgiftbot.farm.base import AuthError, parseCookies
from steamgiftbot.farm.indiegala import parseListing
from steamgiftbot.farm.manager import FarmManager
from steamgiftbot.farm.opiumpulses import isSignedIn
from steamgiftbot.farm.opiumpulses import parseListing as parseOp


@pytest.fixture
def manager(tmp_path):
    (tmp_path / 'config.ini').write_text(
        "[DEFAULT]\ncookie = abc\ngift_type = All\npinned = yes\nmin_points = 10\n",
        encoding='utf-8')
    return FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')


# ---- cookies -----------------------------------------------------------------

def test_cookie_header_is_split():
    assert parseCookies('Cookie: auth=x; csrftoken=y ;  a=b=c') == {
        'auth': 'x', 'csrftoken': 'y', 'a': 'b=c'}


def test_bare_cookie_needs_a_name():
    assert parseCookies('abc', bareName='PHPSESSID') == {'PHPSESSID': 'abc'}
    assert parseCookies('abc') == {}


UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0'

CURL_BASH = f"""curl 'https://www.indiegala.com/giveaways' \\
  -H 'accept: text/html,application/xhtml+xml' \\
  -H 'accept-language: ru-RU,ru;q=0.9' \\
  -b 'auth=x; csrftoken=y; incap_ses_1=a=b' \\
  -H 'priority: u=0, i' \\
  -H 'user-agent: {UA}'"""

CURL_CMD = f"""curl ^"https://www.indiegala.com/giveaways^" ^
  -H ^"accept: text/html^" ^
  -b ^"auth=x; csrftoken=y; pct=50^%^" ^
  -H ^"user-agent: {UA}^\""""


def test_curl_from_chrome_gives_cookie_and_user_agent():
    for command in (CURL_BASH, CURL_CMD):
        jar = parseCookies(command)
        assert jar['auth'] == 'x' and jar['csrftoken'] == 'y'
        assert base.userAgentFrom(command) == UA
    assert parseCookies(CURL_BASH)['incap_ses_1'] == 'a=b'
    assert parseCookies(CURL_CMD)['pct'] == '50%'


def test_curl_from_firefox_sends_cookie_as_a_header():
    command = (f"curl 'https://www.indiegala.com/' -H 'User-Agent: {UA}' "
               "-H 'Cookie: auth=x; csrftoken=y'")
    assert parseCookies(command) == {'auth': 'x', 'csrftoken': 'y'}
    assert base.userAgentFrom(command) == UA


def test_curl_without_cookies_gives_nothing():
    assert parseCookies("curl 'https://www.indiegala.com/' -H 'accept: */*'") == {}


def test_pasted_request_headers_block():
    block = (":authority: www.indiegala.com\naccept: */*\n"
             f"cookie: auth=x; csrftoken=y\nuser-agent: {UA}")
    assert parseCookies(block) == {'auth': 'x', 'csrftoken': 'y'}
    assert base.userAgentFrom(block) == UA


def test_cookie_editor_exports():
    exported = json.dumps([
        {'domain': '.indiegala.com', 'name': 'auth', 'value': 'x', 'httpOnly': True},
        {'domain': '.indiegala.com', 'name': 'csrftoken', 'value': 'y'}])
    assert parseCookies(exported) == {'auth': 'x', 'csrftoken': 'y'}
    netscape = ("# Netscape HTTP Cookie File\n"
                "#HttpOnly_.indiegala.com\tTRUE\t/\tTRUE\t1790000000\tauth\tx\n"
                ".indiegala.com\tTRUE\t/\tTRUE\t1790000000\tcsrftoken\ty\n")
    assert parseCookies(netscape) == {'auth': 'x', 'csrftoken': 'y'}


def test_plain_cookie_has_no_user_agent():
    assert base.userAgentFrom('auth=x; csrftoken=y') is None
    assert parseCookies('cookie\nauth=x; csrftoken=y') == {'auth': 'x', 'csrftoken': 'y'}
    assert parseCookies('cookieconsent=1; auth=x') == {'cookieconsent': '1', 'auth': 'x'}


# ---- IndieGala ---------------------------------------------------------------

def test_indiegala_listing_from_the_live_site():
    tickets = parseListing(fixture('indiegala_listing.html'))
    assert [t.id for t in tickets] == ['1217743', '1217567', '1217568']
    first = tickets[0]
    assert first.name == 'Grav Blazer Squared'
    assert first.price == 4
    assert first.entries == 1605
    assert first.url.endswith('/giveaways/card/grav-blazer-squared/1217743')


class FakeIndieGala:
    """Answers like www.indiegala.com does for a signed-in user."""

    def __init__(self, silver=10, logged=True, joinStatus=None):
        self.cookies = requests.cookies.RequestsCookieJar()
        self.cookies.set('csrftoken', 'tok', domain='.indiegala.com')
        self.headers = {}
        self.silver = silver
        self.logged = logged
        self.joinStatus = joinStatus or {}
        self.joined = []
        self.csrf = []
        self.pages = {1: fixture('indiegala_listing.html')}

    def request(self, method, url, headers=None, data=None, **kwargs):
        self.csrf.append((headers or {}).get('X-CSRFToken'))
        if url.endswith('/ajax/user/get-data'):
            body = {'user_is_logged': self.logged, 'silver_coins_tot': self.silver,
                    'current_user': {'username': 'tester'}}
        elif '/giveaways/ajax/' in url:
            page = int(url.split('/giveaways/ajax/')[1].split('/')[0])
            html = self.pages.get(page, '')
            body = {'status': 'ok', 'html': html}
        elif url.endswith('/giveaways/join'):
            ident = json.loads(data)['id']
            status = self.joinStatus.get(ident, 'ok')
            if status == 'ok':
                self.joined.append(ident)
                self.silver -= {'1217743': 4, '1217567': 1, '1217568': 8}[ident]
            body = {'status': status, 'silver_tot': self.silver}
        else:
            body = {}
        response = requests.models.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response


def indiegala(manager, site, **conf):
    platform = manager.platforms['indiegala']
    settings = platform.settings()
    settings.update(cookie='auth=1', **{'sort': 'expiry', **conf})
    manager.savePlatformSettings('indiegala', settings)
    platform.session = site
    platform.pause = lambda *a, **k: True
    platform.wait = lambda *a, **k: True
    return platform, platform.settings()


def test_indiegala_pass_spends_down_to_reserve(manager):
    site = FakeIndieGala(silver=10)
    platform, conf = indiegala(manager, site, reserve=2)
    entered = platform.cycle(conf)
    # 10 - 4 = 6, then 6 - 1 = 5; the 8 iS ticket would go below the reserve.
    assert site.joined == ['1217743', '1217567']
    assert entered == 2
    assert platform.balance == 5
    assert set(site.csrf) == {'tok'}
    assert manager.state.totals('indiegala')['entered'] == 2


def test_indiegala_does_not_rejoin(manager):
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site)
    platform.cycle(conf)
    site.joined.clear()
    platform.cycle(conf)
    assert site.joined == []


def test_indiegala_refusal_is_remembered(manager):
    site = FakeIndieGala(silver=100, joinStatus={'1217743': 'level'})
    platform, conf = indiegala(manager, site)
    platform.cycle(conf)
    assert site.joined == ['1217567', '1217568']
    site.joinStatus = {}
    site.joined.clear()
    platform.cycle(conf)
    assert site.joined == []


def test_indiegala_signed_out_is_an_auth_error(manager):
    platform, conf = indiegala(manager, FakeIndieGala(logged=False))
    with pytest.raises(AuthError):
        platform.cycle(conf)


def test_indiegala_settings_hide_the_cookie(manager):
    platform, _ = indiegala(manager, FakeIndieGala())
    assert platform.publicSettings()['cookie'] is True
    # Saving the form with the secret left empty keeps the old one.
    platform.updateSettings({'cookie': '', 'max_price': '5'})
    assert platform.settings()['cookie'] == 'auth=1'
    assert platform.settings()['max_price'] == 5


# ---- OpiumPulses -------------------------------------------------------------

OP_PAGE = """<html><body><header><a href="/site/logout">Logout</a>
<span class="points-items">1,250 OP</span></header>
<div class="giveaways-page-items">
 <div class="giveaways-page-item">
   <div class="giveaways-page-item-header-points">FREE</div>
   <a href="/giveaway/9001/some-game">x</a>
   <div class="giveaways-page-item-footer-name">Some Game</div>
   <a class="giveaways-page-item-img-btn-enter" href="/giveaways/enter/9001">enter</a>
 </div>
 <div class="giveaways-page-item">
   <div class="giveaways-page-item-header-points">25 points</div>
   <div class="giveaways-page-item-footer-name">Paid Game</div>
   <a class="giveaways-page-item-img-btn-enter" href="/giveaways/enter/9002">enter</a>
 </div>
 <div class="giveaways-page-item">
   <div class="giveaways-page-item-header-points">5 points</div>
   <div class="giveaways-page-item-footer-name">Done Game</div>
   <a class="giveaways-page-item-img-btn-entered" href="/giveaways/enter/9003">entered</a>
 </div>
</div></body></html>"""


def test_opiumpulses_listing():
    giveaways, soup = parseOp(OP_PAGE, 'https://www.opiumpulses.com/giveaways')
    assert [(g.name, g.cost, g.entered) for g in giveaways] == [
        ('Some Game', 0, False), ('Paid Game', 25, False), ('Done Game', 5, True)]
    assert giveaways[0].enterURL == 'https://www.opiumpulses.com/giveaways/enter/9001'
    assert isSignedIn(OP_PAGE)
    assert not isSignedIn('<a href="/site/login">Login</a>')


# ---- state -------------------------------------------------------------------

def test_state_survives_a_restart(manager, tmp_path):
    manager.state.addEntry('indiegala', {'time': time.time(), 'name': 'A', 'cost': 3})
    manager.state.markSeen('indiegala', '42')
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    assert again.state.totals('indiegala') == {'entered': 1, 'spent': 3, 'wins': 0, 'today': 1}
    assert '42' in again.state.seen('indiegala')


# ---- the worker thread -------------------------------------------------------

def test_stop_wakes_a_sleeping_worker(manager):
    platform = manager.platforms['indiegala']
    calls = []

    def run():
        calls.append(1)
        platform.wait(3600)

    platform.run = run
    platform.configured = lambda: True
    platform.start()
    deadline = time.time() + 2
    while platform.state != base.SLEEPING and time.time() < deadline:
        time.sleep(0.01)
    assert platform.state == base.SLEEPING
    platform.stop(wait=2)
    assert not platform.running
    assert platform.state == base.STOPPED


# ---- web panel ---------------------------------------------------------------

@pytest.fixture
def panel(manager):
    manager.setPassword('secret123')
    server = web.serve(manager, '127.0.0.1', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(url, body=None, cookie=None, header=True):
    headers = {'Content-Type': 'application/json'}
    if header:
        headers['X-Requested-With'] = 'BotFarm'
    if cookie:
        headers['Cookie'] = cookie
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read() or b'{}'), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}'), error.headers


def test_panel_needs_a_password(panel):
    assert call(panel + '/api/status')[0] == 401
    assert call(panel + '/api/login', {'password': 'nope'})[0] == 401
    status, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    assert status == 200
    cookie = headers['Set-Cookie'].split(';')[0]
    assert 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
    status, data, _ = call(panel + '/api/status', cookie=cookie)
    assert status == 200
    assert [p['key'] for p in data['platforms']] == ['steamgifts', 'indiegala', 'opiumpulses',
                                                    'steamfree', 'gog', 'itch']


def test_panel_post_needs_the_header(panel):
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    assert call(panel + '/api/stop-all', {}, cookie=cookie, header=False)[0] == 403
    assert call(panel + '/api/stop-all', {}, cookie=cookie)[0] == 200


def test_panel_never_returns_cookies(panel, manager):
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    _, data, _ = call(panel + '/api/platforms/steamgifts/settings', cookie=cookie)
    assert data['values']['cookie'] is True
    assert 'abc' not in json.dumps(data)


def test_new_password_signs_everyone_out(panel, manager):
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    manager.setPassword('another1')
    assert call(panel + '/api/status', cookie=cookie)[0] == 401


# ---- shared rules ------------------------------------------------------------

def at(hour, minute=0):
    return datetime(2026, 11, 19, hour, minute, tzinfo=ZoneInfo('Europe/Kyiv'))


def test_working_hours():
    assert rules.normalizeHours(' 8-23 , 18:30–2:00') == '08:00-23:00, 18:30-02:00'
    assert rules.normalizeHours('') == ''
    for bad in ('утром', '25:00-26:00', '10:00-10:00'):
        with pytest.raises(ValueError):
            rules.parseHours(bad)
    day = rules.parseHours('08:00-23:00')
    assert rules.secondsUntilOpen(day, at(12)) == 0
    assert rules.secondsUntilOpen(day, at(7, 30)) == 30 * 60
    assert rules.secondsUntilOpen(day, at(23, 30)) == 8.5 * 3600
    night = rules.parseHours('22:00-02:00')
    assert rules.secondsUntilOpen(night, at(1)) == 0
    assert rules.secondsUntilOpen(night, at(3)) == 19 * 3600
    assert rules.secondsUntilOpen([], at(3)) == 0


def test_word_presets():
    junk = ('Fantasy Grounds - Dragons NPC Dice Pack Volume 1', 'Some Game OST',
            'Some Game - Season Pass', 'Some Game Soundtrack')
    assert all(rules.presetReason(name, skipJunk=True) for name in junk)
    assert rules.presetReason('Backpack Hero', skipJunk=True) is None
    assert rules.presetReason('Hentai Bad Girls', skipAdult=True) == '18+'
    assert rules.presetReason('Dating 18+ Edition', skipAdult=True) == '18+'
    assert rules.presetReason('Essex Story', skipAdult=True) is None
    assert rules.presetReason('Hentai Bad Girls') is None


def test_owned_games_match_by_appid_or_title():
    owned = rules.OwnedGames([{'appid': 703530, 'name': 'Grav Blazer Squared'},
                              {'appid': 388880, 'name': 'Oxenfree™'}])
    assert owned.has(appid=703530)
    assert owned.has(name='OXENFREE')
    assert not owned.has(appid=1, name='Oxenfree II')


class FakeSteam:
    def __init__(self, games):
        self.games = games
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url.rsplit('/', 3)[-3])
        if 'ResolveVanityURL' in url:
            body = {'response': {'steamid': '76561198000000001', 'success': 1}}
        else:
            body = {'response': {} if self.games is None else
                    {'game_count': len(self.games), 'games': self.games}}
        response = requests.models.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response


def test_steam_library_resolves_profile_and_caches():
    steam = FakeSteam([{'appid': 10, 'name': 'Counter-Strike'}])
    library = rules.SteamLibrary(session=steam)
    owned = library.owned('KEY', 'https://steamcommunity.com/id/someone/')
    assert owned.has(appid=10)
    assert library.owned('KEY', 'https://steamcommunity.com/id/someone/') is owned
    assert steam.calls == ['ResolveVanityURL', 'GetOwnedGames']
    assert library.owned('', 'x') is None


def test_private_steam_profile_does_not_filter():
    library = rules.SteamLibrary(session=FakeSteam(None))
    assert library.owned('KEY', '76561198000000001') is None
    assert 'Игровые данные' in library.problem


# ---- IndieGala: new rules ----------------------------------------------------

def test_indiegala_listing_knows_app_and_time_left():
    first = parseListing(fixture('indiegala_listing.html'))[0]
    assert first.appid == 703530
    assert first.minutesLeft == 6
    assert not first.guaranteed


def test_indiegala_smart_order_takes_the_best_chance_per_silver(manager):
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site, sort='smart')
    platform.cycle(conf)
    # 1 iS / 2604 people beats 4 iS / 1605, which beats 8 iS / 2530.
    assert site.joined == ['1217567', '1217743', '1217568']


def test_indiegala_priority_goes_first_and_may_use_the_reserve(manager):
    site = FakeIndieGala(silver=9)
    platform, conf = indiegala(manager, site, sort='smart', reserve=5, priority=['doughlings'])
    platform.cycle(conf)
    # Doughlings (8 iS) first, eating into the reserve; then nothing fits above 5.
    assert site.joined == ['1217568']


def test_indiegala_skips_owned_games(manager):
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site, skip_owned=True)
    manager.ownedGames = lambda: rules.OwnedGames([{'appid': 703530, 'name': 'x'}])
    platform.cycle(conf)
    assert site.joined == ['1217567', '1217568']


def test_indiegala_daily_limits(manager):
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site, daily_entries=1)
    platform.cycle(conf)
    assert site.joined == ['1217743']
    site.joined.clear()
    manager.state.data['indiegala']['entries'].clear()
    manager.state.data['indiegala']['recent'].clear()
    platform, conf = indiegala(manager, site, daily_entries=None, daily_spend=5)
    manager.state.seenSets['indiegala'].clear()
    platform.cycle(conf)
    # 4 iS, then 1 iS: 5 spent, the 8 iS ticket would pass the limit.
    assert site.joined == ['1217743', '1217567']


def test_indiegala_price_and_time_filters(manager):
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site, min_price=2, max_hours_left=0)
    platform.cycle(conf)
    assert site.joined == []
    platform, conf = indiegala(manager, site, min_price=2, max_hours_left=None,
                               skip_junk=True, whitelist=['grav', 'dough'])
    platform.cycle(conf)
    assert site.joined == ['1217743', '1217568']


def test_gate_waits_for_working_hours(manager):
    platform = manager.platforms['indiegala']
    manager.localNow = lambda: at(6)
    settings = platform.settings()
    settings.update(cookie='auth=1', active_hours='08:00-23:00')
    manager.savePlatformSettings('indiegala', settings)
    waits, reasons = [], []

    def wait(seconds, sleeping=True, reason=''):
        waits.append(seconds)
        reasons.append(reason)
        manager.localNow = lambda: at(8)
        return True
    platform.wait = wait
    assert platform.gate()['active_hours'] == '08:00-23:00'
    assert waits == [2 * 3600]
    assert reasons == ['Вне часов работы, откроется в 08:00']
    manager.localNow = lambda: at(6)
    platform.forced = True
    assert platform.gate() is not None
    assert waits == [2 * 3600]


# ---- farm settings and report ------------------------------------------------

def test_farm_settings_validate_and_hide_the_key(manager):
    manager.updateFarmSettings({'steam_api_key': 'K' * 32, 'steam_profile': '7656',
                                'timezone': 'Europe/Kyiv', 'report_hour': '9'})
    assert manager.farmSettings()['report_hour'] == 9
    assert manager.publicFarmSettings()['steam_api_key'] is True
    for bad in ({'timezone': 'Mars/Olympus'}, {'report_hour': '25'}):
        with pytest.raises(ValueError):
            manager.updateFarmSettings(bad)
    platform = manager.platforms['indiegala']
    with pytest.raises(ValueError):
        platform.updateSettings({'active_hours': 'всегда'})


def test_daily_report_goes_out_once(manager):
    sent = []
    manager.notify = lambda text: sent.append(text) or []
    manager.state.addEntry('indiegala', {'time': time.time(), 'name': 'Oxenfree', 'cost': 8})
    manager.state.addWin('indiegala', {'time': time.time(), 'name': 'Oxenfree'})
    manager.updateFarmSettings({'daily_report': True, 'report_hour': '21'})
    manager.localNow = lambda: at(20)
    assert not manager.reportTick()
    manager.localNow = lambda: at(21, 5)
    assert manager.reportTick()
    assert not manager.reportTick()
    assert 'IndieGala: 1 вх., потрачено 8' in sent[0]
    assert 'выигрыши: Oxenfree' in sent[0]


def test_steamgifts_farm_rules(manager):
    from steamgiftbot.farm.steamgifts import FarmPause
    from steamgiftbot.giveaway import Giveaway
    platform = manager.platforms['steamgifts']
    platform.updateSettings({'skip_owned': True, 'skip_junk': True, 'daily_entries': '1'})
    assert platform.settings()['skip_junk'] is True
    assert 'skip_junk' not in (manager.configPath.read_text())
    platform.extra = platform.settings()
    manager.ownedGames = lambda: rules.OwnedGames([{'appid': 10, 'name': 'Counter-Strike'}])
    assert platform.extraReason(Giveaway('a', 'Counter-Strike', 5, appid=10))
    assert platform.extraReason(Giveaway('b', 'Game Soundtrack', 5))
    assert platform.extraReason(Giveaway('c', 'Fine Game', 5)) is None
    manager.state.addEntry('steamgifts', {'time': time.time(), 'name': 'x', 'cost': 5})
    with pytest.raises(FarmPause):
        platform.extraReason(Giveaway('c', 'Fine Game', 5))


def test_panel_farm_settings(panel, manager):
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    assert call(panel + '/api/farm/settings', {'values': {'steam_api_key': 'SECRETKEY'}},
                cookie=cookie)[0] == 200
    status, data, _ = call(panel + '/api/farm/settings', cookie=cookie)
    assert status == 200 and data['values']['steam_api_key'] is True
    assert 'SECRETKEY' not in json.dumps(data)
    assert call(panel + '/api/farm/settings', {'values': {'timezone': 'nope'}},
                cookie=cookie)[0] == 400


def test_indiegala_looks_past_pages_already_entered(manager):
    # Page 1 and 2 hold only giveaways already joined (no join button); the
    # live list looked exactly like this after the first big pass.
    entered = re.sub(r'<a class="items-list-item-ticket-click"[^>]*></a>', '',
                     fixture('indiegala_listing.html'))
    site = FakeIndieGala(silver=100)
    site.pages = {1: entered, 2: entered, 3: fixture('indiegala_listing.html')}
    platform, conf = indiegala(manager, site, max_pages=1)
    platform.cycle(conf)
    assert site.joined == ['1217743', '1217567', '1217568']


# ---- panel helpers: dry run, quick lists, chart, wins --------------------------

def test_indiegala_preview_enters_nothing(manager, monkeypatch):
    site = FakeIndieGala(silver=9)
    platform, _ = indiegala(manager, site, reserve=2)
    monkeypatch.setattr(type(platform), 'connect',
                        lambda self, conf: setattr(self, 'session', site))
    platform.stop()
    result = platform.runPreview()
    assert site.joined == []
    assert manager.state.totals('indiegala')['entered'] == 0
    assert result['balance'] == 9
    rows = [(item['name'][:10], item['enter'], item['reason']) for item in result['items']]
    # 9 - 4 = 5, 5 - 1 = 4, and the 8 iS ticket would dip under the reserve.
    assert [enter for _, enter, _ in rows] == [True, True, False]
    assert rows[2][2] == 'не хватает iS'
    # The real worker keeps its own session and stop flag.
    assert platform.session is site and platform.stopped


def test_preview_refuses_without_settings(manager):
    with pytest.raises(ValueError):
        manager.platforms['opiumpulses'].runPreview()


def test_add_to_quick_lists(manager):
    gala = manager.platforms['indiegala']
    assert gala.quickLists() == ['blacklist', 'priority']
    assert manager.platforms['opiumpulses'].quickLists() == ['blacklist']
    assert gala.addToList('blacklist', '  Sex   Chess ')
    assert not gala.addToList('blacklist', 'sex chess')
    assert gala.settings()['blacklist'] == ['Sex Chess']
    with pytest.raises(ValueError):
        manager.platforms['opiumpulses'].addToList('priority', 'x')
    steam = manager.platforms['steamgifts']
    assert steam.addToList('blacklist', 'Bad Game')
    assert 'Bad Game' in steam.loadConfig().blacklist


def test_summary_counts_by_day_and_backfills(manager, tmp_path):
    platform = manager.platforms['indiegala']
    platform.recordEntry('A', 4)
    platform.recordEntry('B', 1)
    platform.recordWin('A')
    summary = manager.summary(7)
    assert len(summary['days']) == 7
    site = next(item for item in summary['sites'] if item['key'] == 'indiegala')
    assert site['entries'][-1] == 2 and site['spentByDay'][-1] == 5 and site['winsByDay'][-1] == 1
    assert site['unit'] == 'iS' and site['today'] == 2 and site['winsWeek'] == 1
    # A state file written before the per-day counts gets them from its history.
    data = json.loads((tmp_path / 'botfarm-state.json').read_text())
    del data['indiegala']['daily']
    (tmp_path / 'botfarm-state.json').write_text(json.dumps(data))
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    site = next(item for item in again.summary(7)['sites'] if item['key'] == 'indiegala')
    assert site['entries'][-1] == 2


def test_win_status(manager):
    manager.platforms['indiegala'].recordWin('Prize', 'https://x/')
    wins = manager.openWins()
    assert [(win['name'], win['key'], win['status']) for win in wins] == \
        [('Prize', 'indiegala', '')]
    assert manager.state.setWinStatus('indiegala', wins[0]['time'], 'Prize', 'received')
    assert manager.openWins() == []
    assert not manager.state.setWinStatus('indiegala', 1, 'Prize', 'activated')
    with pytest.raises(ValueError):
        manager.state.setWinStatus('indiegala', wins[0]['time'], 'Prize', 'lost')


def test_snapshot_shows_limits_and_reason(manager):
    platform = manager.platforms['indiegala']
    manager.localNow = lambda: at(6)
    settings = platform.settings()
    settings.update(daily_entries=5, active_hours='08:00-23:00')
    manager.savePlatformSettings('indiegala', settings)
    platform.recordEntry('A', 4)
    snap = platform.snapshot()
    assert snap['limits']['entries'] == {'used': 1, 'max': 5}
    assert snap['limits']['spend'] == {'used': 4, 'max': None}
    assert snap['limits']['opensAt'] == '08:00'
    platform.waitReason = 'Ждёт'
    assert platform.snapshot()['reason'] == 'Ждёт'
    assert manager.platforms['steamgifts'].snapshot()['limits']['entries']['max'] is None


def test_panel_lists_wins_summary_and_preview(panel, manager):
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    base = panel + '/api/platforms/indiegala/'
    status, data, _ = call(base + 'list', {'list': 'blacklist', 'value': 'Junk'}, cookie=cookie)
    assert status == 200 and data['added']
    assert manager.platforms['indiegala'].settings()['blacklist'] == ['Junk']
    assert call(base + 'list', {'list': 'whitelist', 'value': 'x'}, cookie=cookie)[0] == 400
    manager.platforms['indiegala'].recordWin('Prize')
    _, status_data, _ = call(panel + '/api/status', cookie=cookie)
    win = status_data['wins'][0]
    assert call(base + 'win', {'time': win['time'], 'name': 'Prize', 'status': 'activated'},
                cookie=cookie)[0] == 200
    _, history, _ = call(base + 'history', cookie=cookie)
    assert history['wins'][0]['status'] == 'activated' and history['lists'] == ['blacklist',
                                                                                 'priority']
    status, summary, _ = call(panel + '/api/summary?days=14', cookie=cookie)
    assert status == 200 and len(summary['days']) == 14
    status, data, _ = call(panel + '/api/platforms/opiumpulses/preview', {}, cookie=cookie)
    assert status == 400 and 'cookie' in data['error']


# ---- fixes from the 19.11 audit ----------------------------------------------

def test_stop_pressed_during_a_pass_is_not_lost(manager):
    """Stop arrives while the pass runs; the interval wait after it must not
    swallow it and sleep for an hour."""
    platform = manager.platforms['indiegala']
    passing = threading.Event()

    def run():
        passing.set()
        while not platform.stopped:      # 'the pass' notices the stop ...
            time.sleep(0.01)
        platform.wait(3600)              # ... and the run then goes to sleep

    platform.run = run
    platform.start()
    assert passing.wait(2)
    platform.stop(wait=2)
    assert not platform.running
    assert platform.state == base.STOPPED


def test_run_now_during_a_pass_skips_the_next_wait(manager):
    platform = manager.platforms['indiegala']
    platform.forced = True
    result = []
    # In a thread, so the bug (sleeping the full hour) fails the test
    # instead of hanging it.
    waiter = threading.Thread(target=lambda: result.append(platform.wait(3600)), daemon=True)
    waiter.start()
    waiter.join(1)
    assert result == [True]


class FakeSteamGiftBot:
    """Stands in for FarmSteamGift in SteamGiftsPlatform.run."""

    instances = []

    def __init__(self, platform, config, statePath):
        self.platform, self.points, self.pointsWait = platform, 100, 900
        self.running, self.walks, self.waitedForPoints = True, 0, False
        FakeSteamGiftBot.instances.append(self)

    def updateInfo(self):
        pass

    def announceWins(self):
        return []

    def getGameContent(self):
        self.walks += 1            # walked to the end, nothing suitable
        if self.walks >= 3:
            # The bug this guards against: walking again at once, for ever.
            # Stop here so the test fails instead of hanging.
            self.platform.stopFlag.set()

    def stop(self):
        self.running = False


def test_steamgifts_pauses_when_nothing_suits(manager, monkeypatch):
    from steamgiftbot.farm import steamgifts
    monkeypatch.setattr(steamgifts, 'FarmSteamGift', FakeSteamGiftBot)
    platform = manager.platforms['steamgifts']
    waits = []

    def wait(seconds, sleeping=True, reason=''):
        waits.append(seconds)
        platform.stopFlag.set()
        return False

    platform.wait = wait
    platform.run()
    bot = FakeSteamGiftBot.instances[-1]
    assert bot.walks == 1
    assert waits == [900]


def test_steamgifts_empty_min_points_is_refused(manager):
    platform = manager.platforms['steamgifts']
    with pytest.raises(ValueError):
        platform.updateSettings({'min_points': ''})
    assert platform.settings()['min_points'] == 10
    # A config.ini an older farm left with 'None' in it still loads.
    text = manager.configPath.read_text().replace('min_points = 10', 'min_points = None')
    manager.configPath.write_text(text)
    assert platform.settings()['min_points'] is None
    assert not platform.configured()


def test_steamgifts_remembers_final_refusals(manager, monkeypatch):
    from steamgiftbot.bot import SteamGift
    from steamgiftbot.farm.steamgifts import FarmSteamGift, SteamGiftsPlatform
    from steamgiftbot.giveaway import Giveaway

    answers = {'dlc1': 'Missing Base Game', 'own1': 'Exists in Account',
               'poor': 'Not Enough Points'}

    def entry(self, code, cost):
        self.lastRejection = answers[code]
        return False

    monkeypatch.setattr(SteamGift, 'entryGIFT', entry)
    platform = manager.platforms['steamgifts']
    bot = object.__new__(FarmSteamGift)
    bot.platform = platform
    for code in answers:
        bot.entryGIFT(code, 5)
    seen = manager.state.seen('steamgifts')
    assert {'no:dlc1', 'no:own1'} <= seen and 'no:poor' not in seen
    reason = SteamGiftsPlatform.budgetReason
    assert reason(Giveaway('dlc1', 'DLC', 5), 100, 0, None, seen) == 'SteamGifts уже отказал'
    assert reason(Giveaway('poor', 'Game', 5), 100, 0, None, seen) is None


def test_steamgifts_reserve_counts_after_the_entry():
    from steamgiftbot.farm.steamgifts import SteamGiftsPlatform
    from steamgiftbot.giveaway import Giveaway
    reason = SteamGiftsPlatform.budgetReason
    assert reason(Giveaway('a', 'Big', 50), 60, 30, None, set())
    assert reason(Giveaway('b', 'Fits', 30), 60, 30, None, set()) is None


def test_steamgifts_spend_limit_skips_instead_of_pausing(manager):
    from steamgiftbot.giveaway import Giveaway
    platform = manager.platforms['steamgifts']
    platform.updateSettings({'daily_spend': '10'})
    platform.extra = platform.settings()
    # 10 P left today: the 50 P giveaway is skipped, the 5 P one still fits.
    assert platform.extraReason(Giveaway('x', 'Pricey', 50), 100, 0) == 'дневной лимит трат'
    assert platform.extraReason(Giveaway('y', 'Cheap', 5), 100, 0) is None


def test_daily_limits_count_past_the_history_length(manager, tmp_path):
    now = time.time()
    for number in range(base.HISTORY_LENGTH + 100):
        manager.state.addEntry('indiegala', {'time': now - number, 'name': 'g', 'cost': 1})
    count, spent, _oldest = manager.state.usage('indiegala')
    assert (count, spent) == (base.HISTORY_LENGTH + 100, base.HISTORY_LENGTH + 100)
    assert len(manager.state.data['indiegala']['entries']) == base.HISTORY_LENGTH
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    assert again.state.usage('indiegala')[0] == base.HISTORY_LENGTH + 100


class FakeOpium:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}

    def mount(self, prefix, adapter):
        pass

    def get(self, url, **kwargs):
        status, text = self.pages[url]
        response = requests.models.Response()
        response.status_code = status
        response._content = text.encode()
        response.url = url
        return response


def opium(manager, pages):
    from steamgiftbot.farm.opiumpulses import OpGiveaway
    platform = manager.platforms['opiumpulses']
    platform.session = FakeOpium(pages)
    url = 'https://www.opiumpulses.com/giveaways/enter/9001'
    return platform, OpGiveaway('9001', 'Some Game', 0, url, False,
                                'https://www.opiumpulses.com/giveaway/9001')


def test_opiumpulses_counts_only_confirmed_entries(manager):
    url = 'https://www.opiumpulses.com/giveaways/enter/9001'
    platform, giveaway = opium(manager, {url: (404, 'gone')})
    assert platform.enter(giveaway) == (False, 'сайт ответил HTTP 404')

    platform, giveaway = opium(manager, {url: (200, '<p>This giveaway has ended</p>')})
    assert platform.enter(giveaway)[0] is False

    # Sent back to the listing, where the giveaway now reads 'entered'.
    entered = OP_PAGE.replace('giveaways-page-item-img-btn-enter" href="/giveaways/enter/9001">'
                              'enter', 'giveaways-page-item-img-btn-entered" '
                              'href="/giveaways/enter/9001">entered')
    platform, giveaway = opium(manager, {url: (200, entered)})
    assert platform.enter(giveaway) == (True, '')

    # The same listing with the button unchanged: not confirmed, kept for debugging.
    platform, giveaway = opium(manager, {url: (200, OP_PAGE)})
    ok, reason = platform.enter(giveaway)
    assert ok is False and 'не подтверждён' in reason
    assert (manager.dataDir / 'debug' / 'opiumpulses-enter-unconfirmed.html').exists()


def test_opiumpulses_empty_keys_table_is_not_a_win(manager):
    from steamgiftbot.farm.opiumpulses import WON_KEYS

    def table(*names):
        rows = ''.join(f'<tr><td>{name}</td><td><a href="/user/key/{number}">show</a></td></tr>'
                       for number, name in enumerate(names))
        return f'<table><tbody>{rows}</tbody></table>'

    empty = '<table><tbody><tr><td colspan="4">No results found.</td></tr></tbody></table>'
    platform = manager.platforms['opiumpulses']
    notes = []
    platform.notify = notes.append
    for page in (table('Old Game'), empty, table('Old Game', 'Cool Game')):
        platform.session = FakeOpium({WON_KEYS: (200, page)})
        platform.checkWins()
    # The first look only learns 'Old Game'; the empty table (the site's
    # 'No results found.' row) is not a win; 'Cool Game' is.
    assert len(notes) == 1 and 'Cool Game' in notes[0]


def test_steamgifts_walk_stops_after_max_pages(manager, monkeypatch):
    from steamgiftbot.bot import SteamGift
    from steamgiftbot.farm.steamgifts import FarmSteamGift
    asked = []
    monkeypatch.setattr(SteamGift, 'GetSoupFromPage', lambda self, url: asked.append(url) or 'soup')
    platform = manager.platforms['steamgifts']
    platform.extra = {'max_pages': 3}
    bot = object.__new__(FarmSteamGift)
    bot.platform = platform
    base_url = 'https://www.steamgifts.com/giveaways/search?page=%d'
    assert bot.GetSoupFromPage(base_url % 3) == 'soup'
    assert bot.GetSoupFromPage(base_url % 4) is None
    # Other pages (the won list) are never cut.
    assert bot.GetSoupFromPage('https://www.steamgifts.com/giveaways/won') == 'soup'
    assert len(asked) == 2


def test_command_line_history_is_imported_once(tmp_path):
    (tmp_path / 'log').mkdir()
    (tmp_path / 'log' / 'log-01.11.2026-10.00.00.log').write_text(
        "[INFO:2026-11-01 10:00:05,123] One more game Alpha\n"
        "[INFO:2026-11-01 10:01:05,123] Entry rejected: Missing Base Game\n"
        "[INFO:2026-11-01 11:00:05,123] One more game Beta\n"
        "[INFO:2026-11-02 09:00:05,123] One more game Gamma\n"
        "[INFO:2026-11-03 09:00:05,123]  Entered 3 giveaways for 30 points.\n", encoding='utf-8')
    # The farm's own entry on 2 Nov at 08:00 local server time: Gamma (09:00) is after it.
    farmTime = time.mktime(time.strptime('2026-11-02 08:00:00', '%Y-%m-%d %H:%M:%S'))
    (tmp_path / 'botfarm-state.json').write_text(json.dumps({'steamgifts': {
        'entries': [{'time': farmTime, 'name': 'Farm', 'cost': 5}], 'totalEntered': 1,
        'totalSpent': 5}}), encoding='utf-8')
    manager = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'none.ini')
    site = manager.state.site('steamgifts')
    assert site['totalEntered'] == 3 and site['totalSpent'] == 5
    imported = {day: counts['cli'] for day, counts in site['daily'].items() if counts.get('cli')}
    assert sum(imported.values()) == 2
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'none.ini')
    assert again.state.site('steamgifts')['totalEntered'] == 3
    days = again.summary(90)
    sg = next(item for item in days['sites'] if item['key'] == 'steamgifts')
    assert sum(sg['importedByDay']) == 2 and sum(sg['entries']) >= 2


def test_panel_log_survives_a_restart(manager):
    (manager.dataDir / 'log').mkdir(exist_ok=True)
    (manager.dataDir / 'log' / 'botfarm.log').write_text(
        "[INFO 2026-11-20 10:00:00,001 botfarm.indiegala] Вошёл: Alpha за 2 iS\n"
        "[WARNING 2026-11-20 10:05:00,001 botfarm.indiegala] IndieGala недоступна\n"
        "[INFO 2026-11-20 10:06:00,001 botfarm] Веб-панель: http://x/\n"
        "[INFO 2026-11-20 10:07:00,001 botfarm.nosuchsite] ignored\n", encoding='utf-8')
    assert manager.restoreLogs() == 2
    lines = manager.platforms['indiegala'].logLines()
    assert [line['text'] for line in lines] == ['Вошёл: Alpha за 2 iS', 'IndieGala недоступна']
    assert all(line['restored'] for line in lines) and lines[1]['level'] == 'WARNING'


def test_log_lines_carry_entry_details_and_skip_reasons(manager):
    import collections
    platform = manager.platforms['indiegala']
    platform.balance = 8
    platform.passStartedAt = time.time() - 5
    platform.info("Вошёл: Alpha за 2 iS")
    platform.recordEntry('Alpha', 2, 'https://www.indiegala.com/giveaways/card/alpha/1', entries=40)
    skipped = collections.Counter()
    platform.skip(skipped, 'дороже лимита', 'Beta', cost='9 iS', entries=None)
    platform.finishPass("Проход окончен: вошёл в 1")
    lines = platform.logLines()
    entry = next(line for line in lines if line['text'].startswith('Вошёл'))
    assert entry['details']['cost'] == '2 iS' and entry['details']['entries'] == 40
    assert entry['details']['balance'] == '8 iS'
    skip = next(line for line in lines if line['level'] == 'DEBUG')
    assert skip['text'] == 'Пропуск: Beta — дороже лимита' and 'entries' not in skip['details']
    assert skipped['дороже лимита'] == 1
    assert re.search(r'Проход окончен: вошёл в 1 · за \d+ с', lines[-1]['text'])


def test_panel_look_is_checked_and_shared(panel, manager):
    status, data, _ = call(panel + '/api/session')
    assert status == 200 and data['ui']['lang'] == 'ru' and data['ui']['tour'] is False
    assert call(panel + '/api/ui', {'values': {'theme': 'light'}})[0] == 401
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    status, data, _ = call(panel + '/api/ui', {'values': {'theme': 'light', 'lang': 'en',
                                                         'accent': '#2ec27e', 'tour': True}},
                           cookie=cookie)
    assert status == 200 and data['ui']['theme'] == 'light' and data['ui']['lang'] == 'en'
    for bad in ({'theme': 'neon'}, {'accent': 'red;}'}, {'scale': 300}, {'lang': 'xx'}):
        assert call(panel + '/api/ui', {'values': bad}, cookie=cookie)[0] == 400
    assert manager.uiSettings()['accent'] == '#2ec27e'
    assert call(panel + '/api/session')[1]['ui']['theme'] == 'light'


def test_command_line_wins_are_imported_as_received(tmp_path):
    (tmp_path / 'log').mkdir()
    (tmp_path / 'log' / 'log-03.09.2026-08.57.51.log').write_text(
        "[INFO:2026-09-03 08:57:51,998] You won Patrician Iii! "
        "https://www.steamgifts.com/giveaway/8caCY/\n"
        "[INFO:2026-09-03 08:58:12,291]  You won 1 giveaways! Entered 4 giveaways for 13 points.\n"
        "[INFO:2026-09-04 08:57:51,998] You won Patrician Iii! "
        "https://www.steamgifts.com/giveaway/8caCY/\n", encoding='utf-8')
    manager = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'none.ini')
    wins = manager.state.site('steamgifts')['wins']
    assert [(win['name'], win['status']) for win in wins] == [('Patrician Iii', 'received')]
    assert manager.state.totals('steamgifts')['wins'] == 1
    assert manager.openWins() == []
