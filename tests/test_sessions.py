"""IndieGala and OpiumPulses keep their session between passes, write down
the cookies the site refreshed, and remind before the sign-in cookie expires."""
import json
import time

import pytest
import requests

from test_farm import manager  # noqa: F401

from steamgiftbot.farm import base, sessions
from steamgiftbot.farm.base import cookieExpiries, parseCookies
from steamgiftbot.farm.manager import FarmManager

DAY = 86400


def connected(manager, key='indiegala', cookie='auth=old; csrftoken=tok; incap_ses_1=a'):  # noqa: F811
    platform = manager.platforms[key]
    settings = platform.settings()
    settings.update(cookie=cookie, check_wins=False)
    manager.savePlatformSettings(key, settings)
    return platform, platform.settings()


# What a Set-Cookie from the site leaves in the jar.
def siteSets(session, name, value, expires=None, domain='.indiegala.com'):
    session.cookies.set_cookie(requests.cookies.create_cookie(
        name, value, domain=domain, path='/', expires=expires))


def kept(manager, key='indiegala'):  # noqa: F811
    return manager.platformEntry(key).get(sessions.KEPT)


# ---- expiry in the paste ---------------------------------------------------------

def test_expiries_from_a_cookie_editor_export():
    exported = json.dumps([
        {'name': 'auth', 'value': 'x', 'expirationDate': 1790000000.25},
        {'name': 'csrftoken', 'value': 'y', 'session': True},
        {'name': 'ms', 'value': 'z', 'expirationDate': 1790000000123}])
    assert cookieExpiries(exported) == {'auth': 1790000000, 'ms': 1790000000}
    # The cookies themselves read as before.
    assert parseCookies(exported) == {'auth': 'x', 'csrftoken': 'y', 'ms': 'z'}
    assert cookieExpiries(json.dumps({'cookies': [{'name': 'auth', 'value': 'x',
                                                   'expirationDate': 1790000000}]})) == {
        'auth': 1790000000}


def test_expiries_from_cookies_txt():
    netscape = ("# Netscape HTTP Cookie File\n"
                "#HttpOnly_.indiegala.com\tTRUE\t/\tTRUE\t1790000000\tauth\tx\n"
                ".indiegala.com\tTRUE\t/\tTRUE\t0\tcsrftoken\ty\n")
    assert cookieExpiries(netscape) == {'auth': 1790000000}
    assert parseCookies(netscape) == {'auth': 'x', 'csrftoken': 'y'}


def test_a_cookie_line_or_curl_has_no_expiry():
    assert cookieExpiries('auth=x; csrftoken=y') == {}
    assert cookieExpiries("curl 'https://www.indiegala.com/' -b 'auth=x'") == {}
    assert cookieExpiries('') == {} and cookieExpiries('[broken') == {}


# ---- one session from pass to pass ---------------------------------------------

def test_the_session_is_kept_while_the_paste_is_the_same(manager):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    first = platform.session
    assert first.headers['Origin'] == 'https://www.indiegala.com'
    platform.connect(platform.settings())
    assert platform.session is first
    # A new paste or another User-Agent is a new browser: a new session.
    platform.updateSettings({'user_agent': 'Other/1.0'})
    platform.connect(platform.settings())
    assert platform.session is not first
    second = platform.session
    platform.updateSettings({'cookie': 'auth=new'})
    platform.connect(platform.settings())
    assert platform.session is not second
    assert base.cookieValue(platform.session.cookies, 'auth') == 'new'


def test_opiumpulses_keeps_its_session_and_its_no_retry_paths(manager):  # noqa: F811
    platform, conf = connected(manager, 'opiumpulses', cookie='PHPSESSID=1')
    platform.connect(conf)
    first = platform.session
    platform.connect(conf)
    assert platform.session is first
    adapter = first.get_adapter('https://www.opiumpulses.com/giveaways/enter/1')
    assert adapter.max_retries.total == 0


def test_refreshed_cookies_survive_a_restart(manager, tmp_path):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'fresh')
    siteSets(platform.session, 'brandnew', 'z')      # not in the paste: not kept
    platform.keepCookies()
    record = kept(manager)
    assert record['values'] == {'auth': 'fresh'}
    # The paste itself is left as the user pasted it.
    assert platform.settings()['cookie'] == 'auth=old; csrftoken=tok; incap_ses_1=a'
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    gala = again.platforms['indiegala']
    gala.connect(gala.settings())
    jar = gala.session.cookies
    assert base.cookieValue(jar, 'auth') == 'fresh'
    assert base.cookieValue(jar, 'csrftoken') == 'tok'
    assert base.cookieValue(jar, 'brandnew') is None


def test_a_new_paste_forgets_the_old_refreshed_cookies(manager):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'fresh')
    platform.keepCookies()
    assert kept(manager)
    platform.updateSettings({'cookie': 'auth=pasted-again'})
    platform.connect(platform.settings())
    assert base.cookieValue(platform.session.cookies, 'auth') == 'pasted-again'
    assert kept(manager) is None


def test_nothing_is_written_when_nothing_changed(manager, monkeypatch):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    saves = []
    monkeypatch.setattr(manager, 'updatePlatformEntry',
                        lambda key, **changes: saves.append(changes))
    platform.keepCookies()
    assert saves == [] and kept(manager) is None


def test_a_check_or_a_dry_run_does_not_touch_the_kept_cookies(manager):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'fresh')
    platform.keepCookies()
    box = platform.sandbox()
    assert box.session is None
    # A check tries cookies that are not saved: the record stays.
    box.connect(box.trialSettings({'cookie': 'auth=trial'}))
    assert base.cookieValue(box.session.cookies, 'auth') == 'trial'
    assert kept(manager)['values'] == {'auth': 'fresh'}
    # A dry run on the saved paste starts from the refreshed values.
    dry = platform.sandbox()
    dry.connect(platform.settings())
    assert dry.session is not platform.session
    assert base.cookieValue(dry.session.cookies, 'auth') == 'fresh'


def test_a_pass_keeps_the_cookies_and_never_logs_them(manager):  # noqa: F811
    platform, conf = connected(manager)
    calls = iter([conf])
    platform.gate = lambda: next(calls, None)
    platform.wait = lambda *args, **kwargs: False

    def cycle(conf):
        siteSets(platform.session, 'auth', 'secret-value', expires=int(time.time()) + 30 * DAY)
        return 0
    platform.cycle = cycle
    platform.run()
    assert kept(manager)['values'] == {'auth': 'secret-value'}
    assert not any('secret-value' in line['text'] for line in platform.logLines())
    assert any('auth' in line['text'] for line in platform.logLines())


def test_disconnect_forgets_the_kept_cookies(manager):  # noqa: F811
    platform, conf = connected(manager)
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'fresh')
    platform.keepCookies()
    platform.disconnect()
    assert kept(manager) is None and platform.session is None


# ---- when the sign-in cookie expires ---------------------------------------------

def test_expiry_comes_from_the_paste_and_then_from_the_site(manager):  # noqa: F811
    soon = int(time.time()) + 10 * DAY
    paste = json.dumps([{'name': 'auth', 'value': 'x', 'expirationDate': soon},
                        {'name': 'csrftoken', 'value': 'y', 'expirationDate': soon + DAY}])
    platform, conf = connected(manager, cookie=paste)
    # Only the sign-in cookie counts, not the CSRF one.
    assert platform.cookieExpiry() == soon
    assert platform.snapshot()['cookieExpires'] == soon
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'renewed', expires=soon + 20 * DAY)
    platform.keepCookies()
    assert platform.cookieExpiry() == soon + 20 * DAY
    # The record holds expiries, values and which paste they belong to; no paste.
    assert set(kept(manager)) == {'paste', 'values', 'expires'}


def test_opiumpulses_reads_the_remember_me_cookie(manager):  # noqa: F811
    later = int(time.time()) + 20 * DAY
    paste = ("# Netscape HTTP Cookie File\n"
             f".opiumpulses.com\tTRUE\t/\tTRUE\t0\tPHPSESSID\ts\n"
             f".opiumpulses.com\tTRUE\t/\tTRUE\t{later}\t0123456789abcdef0123456789abcdef\tr\n")
    platform, _ = connected(manager, 'opiumpulses', cookie=paste)
    assert platform.cookieExpiry() == later


def test_unknown_expiry_shows_nothing(manager):  # noqa: F811
    platform, _ = connected(manager)
    assert platform.cookieExpiry() is None
    assert platform.snapshot()['cookieExpires'] is None
    assert 'cookieExpires' not in manager.platforms['gog'].snapshot()


@pytest.fixture
def told(manager, monkeypatch):  # noqa: F811
    sent = []
    manager.panelURLs = ['http://farm/']
    monkeypatch.setattr(manager.platforms['indiegala'], 'notify',
                        lambda text='', icon='', **card: sent.append((icon, card)))
    return sent


def test_one_reminder_three_days_before(manager, told):  # noqa: F811
    now = time.time()
    expiry = int(now) + 2 * DAY
    paste = json.dumps([{'name': 'auth', 'value': 'x', 'expirationDate': expiry}])
    platform, _ = connected(manager, cookie=paste)
    assert platform.remindExpiry(now)
    assert not platform.remindExpiry(now + 3600)
    assert len(told) == 1
    icon, card = told[0]
    assert icon == '🔑' and card['title'] == 'COOKIE СКОРО ИСТЕЧЁТ'
    assert card['buttons'] == [('Подключить заново', 'http://farm/#/connect/indiegala')]
    # The site renewed the cookie: the new expiry gets its own card in time.
    platform.connect(platform.settings())
    siteSets(platform.session, 'auth', 'renewed', expires=expiry + 30 * DAY)
    platform.keepCookies()
    assert not platform.remindExpiry(now)
    assert platform.remindExpiry(now + 30 * DAY)
    assert len(told) == 2


def test_no_reminder_far_ahead_or_after_the_fact(manager, told):  # noqa: F811
    now = time.time()
    for expiry in (now + 5 * DAY, now - DAY):
        paste = json.dumps([{'name': 'auth', 'value': 'x', 'expirationDate': expiry}])
        platform, _ = connected(manager, cookie=paste)
        assert not platform.remindExpiry(now)
    assert told == []


def test_a_dry_run_sends_no_reminder(manager, told):  # noqa: F811
    paste = json.dumps([{'name': 'auth', 'value': 'x',
                         'expirationDate': time.time() + DAY}])
    platform, _ = connected(manager, cookie=paste)
    assert not platform.sandbox().remindExpiry()
    assert told == []


def test_a_sliding_cookie_is_told_about_once(manager, told):  # noqa: F811
    # The site re-sends the sign-in cookie with a one-day Max-Age on every
    # answer: each pass saves a slightly later expiry.
    platform, conf = connected(manager)
    now = time.time()
    for step in range(40):
        moment = now + step * 2 * 3600
        platform.connect(conf)
        siteSets(platform.session, 'auth', f'v{step}', expires=int(moment) + DAY)
        platform.keepCookies()
        platform.remindExpiry(moment)
    assert len(told) == 1
    # A renewal far ahead is a new expiry, told about when its time comes.
    platform.connect(conf)
    siteSets(platform.session, 'auth', 'renewed', expires=int(moment) + 30 * DAY)
    platform.keepCookies()
    assert not platform.remindExpiry(moment)
    assert platform.remindExpiry(moment + 28 * DAY)
    assert len(told) == 2


def test_a_pass_reminds_and_another_failure_keeps_the_cookies(manager, told):  # noqa: F811
    platform, conf = connected(manager)
    platform.wait = lambda *args, **kwargs: False

    def flaky(conf):
        siteSets(platform.session, 'auth', 'renewed', expires=int(time.time()) + DAY)
        raise base.RetryLater("IndieGala не отвечает.")
    platform.gate = iter([conf]).__next__
    platform.cycle = flaky
    with pytest.raises(base.RetryLater):
        platform.run()
    assert kept(manager)['values'] == {'auth': 'renewed'} and told == []
    session = platform.session
    platform.gate = iter([conf, None]).__next__
    platform.cycle = lambda conf: 0
    platform.run()
    assert platform.session is session
    assert [icon for icon, _card in told] == ['🔑']


@pytest.mark.parametrize('key, cookie', [('indiegala', 'auth=old; csrftoken=tok'),
                                         ('opiumpulses', 'PHPSESSID=old')])
def test_a_turned_down_session_starts_again_from_the_paste(manager, key, cookie):  # noqa: F811
    platform, conf = connected(manager, key, cookie=cookie)
    name = cookie.split('=')[0]
    domain = '.' + platform.sessionDomain.lstrip('.')
    platform.wait = lambda *args, **kwargs: False
    platform.connect(conf)
    siteSets(platform.session, name, 'refreshed', domain=domain)
    platform.keepCookies()
    assert kept(manager, key)

    def signedOut(conf):
        siteSets(platform.session, name, '', domain=domain)
        raise base.AuthError("Сайт просит войти заново.")
    platform.gate = iter([conf]).__next__
    platform.cycle = signedOut
    with pytest.raises(base.AuthError):
        platform.run()
    # Neither the sign-out nor the values from before it are kept.
    assert platform.session is None and kept(manager, key) is None
    platform.connect(platform.settings())
    assert base.cookieValue(platform.session.cookies, name) == 'old'
