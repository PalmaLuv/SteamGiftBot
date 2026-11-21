"""OpiumPulses and itch.io: a giveaway that failed for now is tried again, a
Cloudflare check is not a dead cookie, and the site's own filters that hide
every giveaway are reported."""
import time

import pytest
import requests

from test_farm import OP_PAGE, FakeOpium, manager  # noqa: F401

from steamgiftbot.farm import itch
from steamgiftbot.farm.base import FAILED_TRIES, AuthError, RetryLater
from steamgiftbot.farm.opiumpulses import LISTING

ENTER = 'https://www.opiumpulses.com/giveaways/enter/'

FILTERED_PAGE = """<html><body><header><a href="/site/logout">Logout</a>
<span class="points-items">40 OP</span></header>
<div id="giveawaylistview" class="list-view"><div class="giveaways-page-items">
<span class="empty"><img src="/sadop.png" /><p>There are no giveaways that match your selected
filters.</p></span></div></div></body></html>"""


def opiumPass(manager, pages):  # noqa: F811
    platform = manager.platforms['opiumpulses']
    platform.session = FakeOpium({LISTING: (200, OP_PAGE), **pages})
    platform.pause = lambda *a, **k: True
    platform.balance = None
    notes = []
    platform.notify = lambda text='', icon='', **card: notes.append((icon, text, card))
    conf = platform.settings()
    conf['skip_owned'] = False
    return platform, conf, notes


def seen(manager, key):  # noqa: F811
    return manager.state.seen(key)


# ---- OpiumPulses: what is remembered ----------------------------------------------

def test_opiumpulses_retries_a_failed_entry_a_few_times(manager):  # noqa: F811
    # 9001 answers 404, 9002 'ended'; 9003 is already entered on the listing.
    ended = '<p>This giveaway has ended</p>'
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (404, 'gone'),
                                            ENTER + '9002': (200, ended)})
    platform.cycle(conf)
    # The ended one is a final answer; the 404 is tried again next pass.
    assert '9002' in seen(manager, 'opiumpulses')
    assert '9001' not in seen(manager, 'opiumpulses')
    assert manager.state.value('opiumpulses', 'tries') == {'9001': 1}
    for _ in range(FAILED_TRIES - 1):
        platform.cycle(conf)
    # Three failures in a row: given up on, its counter gone.
    assert '9001' in seen(manager, 'opiumpulses')
    assert manager.state.value('opiumpulses', 'tries') == {}


def test_opiumpulses_unconfirmed_entry_is_not_buried(manager):  # noqa: F811
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (200, OP_PAGE),
                                            ENTER + '9002': (200, 'already entered')})
    platform.cycle(conf)
    assert '9001' not in seen(manager, 'opiumpulses')
    assert '9002' in seen(manager, 'opiumpulses')


def test_opiumpulses_success_clears_the_counter(manager):  # noqa: F811
    entered = OP_PAGE.replace('giveaways-page-item-img-btn-enter" href="/giveaways/enter/9001">'
                              'enter', 'giveaways-page-item-img-btn-entered" '
                              'href="/giveaways/enter/9001">entered')
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (404, 'gone'),
                                            ENTER + '9002': (200, 'already entered')})
    platform.cycle(conf)
    assert manager.state.value('opiumpulses', 'tries') == {'9001': 1}
    platform.session.pages[ENTER + '9001'] = (200, entered)
    assert platform.cycle(conf) == 1
    assert '9001' in seen(manager, 'opiumpulses')
    assert manager.state.value('opiumpulses', 'tries') == {}


def test_opiumpulses_short_of_points_waits_without_counting(manager):  # noqa: F811
    platform, conf, _ = opiumPass(manager, {
        ENTER + '9001': (200, 'not enough points'), ENTER + '9002': (200, 'not enough points')})
    for _ in range(FAILED_TRIES + 1):
        platform.cycle(conf)
    assert not {'9001', '9002'} & seen(manager, 'opiumpulses')
    assert not manager.state.value('opiumpulses', 'tries')


def test_opiumpulses_link_that_always_errors_stops_blocking_passes(manager):  # noqa: F811
    # A 503 on the giveaway's own link ends the pass (RetryLater); counted, so
    # the same giveaway does not end every pass from now on.
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (503, 'busy'),
                                            ENTER + '9002': (200, 'already entered')})
    for _ in range(FAILED_TRIES):
        with pytest.raises(RetryLater):
            platform.cycle(conf)
    assert '9001' in seen(manager, 'opiumpulses')
    platform.cycle(conf)
    assert '9002' in seen(manager, 'opiumpulses')


# ---- OpiumPulses: the user's own filters -------------------------------------------

def test_opiumpulses_filters_that_hide_everything_are_reported_daily(manager):  # noqa: F811
    platform, conf, notes = opiumPass(manager, {})
    platform.session.pages[LISTING] = (200, FILTERED_PAGE)
    warned = []
    platform.warn = warned.append
    platform.cycle(conf)
    platform.cycle(conf)
    # Logged every pass, sent to Telegram once.
    assert len(warned) == 2 and 'opiumpulses.com/giveaways' in warned[0]
    assert len(notes) == 1 and notes[0][0] == '⚠️'
    assert notes[0][2]['buttons'] == [('Открыть раздачи', 'https://www.opiumpulses.com/giveaways')]
    # A day later it is said again.
    manager.state.setFlag('opiumpulses', 'filter_notified_at', time.time() - 25 * 3600)
    platform.cycle(conf)
    assert len(notes) == 2
    # Known cause: no page kept for debugging.
    assert not (manager.dataDir / 'debug' / 'opiumpulses-giveaways.html').exists()


def test_opiumpulses_preview_names_the_filters(manager):  # noqa: F811
    platform = manager.platforms['opiumpulses']
    settings = platform.settings()
    settings.update(cookie='PHPSESSID=1', skip_owned=False)
    manager.savePlatformSettings('opiumpulses', settings)
    fake = FakeOpium({LISTING: (200, FILTERED_PAGE)})
    original = platform.sandbox

    def sandbox():
        box = original()
        box.connect = lambda conf: setattr(box, 'session', fake)
        return box
    platform.sandbox = sandbox
    result = platform.preview()
    assert result['items'] == [] and 'фильтры' in result['note']


# ---- itch.io ------------------------------------------------------------------------

class FakeItch:
    def __init__(self, status=200, text='{}', url=None, headers=None):
        self.answer = (status, text, url, headers or {})
        self.cookies = requests.cookies.RequestsCookieJar()

    def request(self, method, url, **kwargs):
        status, text, final, headers = self.answer
        response = requests.models.Response()
        response.status_code = status
        response._content = text.encode()
        response.url = final or url
        response.headers.update(headers)
        return response


def itchWith(manager, session):  # noqa: F811
    platform = manager.platforms['itch']
    platform.session = session
    return platform


CF_PAGE = ('<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>'
           '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1"></script>'
           '</body></html>')


def test_itch_cloudflare_check_is_retried_not_a_dead_cookie(manager):  # noqa: F811
    platform = itchWith(manager, FakeItch(403, CF_PAGE, headers={'cf-mitigated': 'challenge'}))
    with pytest.raises(RetryLater, match='Cloudflare') as caught:
        platform.whoami()
    assert not isinstance(caught.value, AuthError)
    assert 'User-Agent' in str(caught.value)
    # The same page without the header still reads as a check.
    platform = itchWith(manager, FakeItch(503, CF_PAGE))
    with pytest.raises(RetryLater, match='Cloudflare'):
        platform.request('GET', 'https://author.itch.io/game/data.json')


def test_itch_login_redirect_is_a_dead_cookie(manager):  # noqa: F811
    platform = itchWith(manager, FakeItch(200, '<form>', url='https://itch.io/login?return_to=x'))
    with pytest.raises(AuthError, match='cookie'):
        platform.whoami()
    # A bare 403 that is no check page and no sign-in page: try again later.
    platform = itchWith(manager, FakeItch(403, 'forbidden'))
    with pytest.raises(RetryLater) as caught:
        platform.whoami()
    assert not isinstance(caught.value, AuthError)
    platform = itchWith(manager, FakeItch(200, '{"games": []}',
                                          url=itch.LIBRARY + '?format=json'))
    assert platform.whoami() is True


def test_itch_cloudflare_rule_skips_the_itchclaim_list(manager):  # noqa: F811
    # The ItchClaim list is not itch.io: its broken answer is its own error.
    platform = itchWith(manager, FakeItch(403, CF_PAGE))
    with pytest.raises(RetryLater, match='список раздач'):
        platform.active()


def test_itch_failed_claim_is_retried_a_few_times(manager):  # noqa: F811
    platform = manager.platforms['itch']
    platform.pause = lambda *a, **k: True
    platform.active = lambda: [('7', 'Tiny Game', 'https://a.itch.io/tiny'),
                               ('8', 'Over Game', 'https://a.itch.io/over')]
    platform.stillFree = lambda url: 'tiny' in url
    claims = []
    platform.claim = lambda url: claims.append(url) and False
    conf = platform.settings()
    platform.cycle(conf)
    # The ended sale is settled; the failed claim is not.
    assert '8' in seen(manager, 'itch') and '7' not in seen(manager, 'itch')
    for _ in range(FAILED_TRIES - 1):
        platform.cycle(conf)
    assert '7' in seen(manager, 'itch')
    assert len(claims) == FAILED_TRIES
    platform.cycle(conf)
    assert len(claims) == FAILED_TRIES


# ---- site-wide trouble is not one giveaway's fault ----------------------------------

def test_opiumpulses_slow_down_is_not_held_against_the_giveaway(manager):  # noqa: F811
    # A 429 is about the whole site: three such passes leave 9001 untouched.
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (429, 'slow down'),
                                            ENTER + '9002': (200, 'already entered')})
    for _ in range(FAILED_TRIES):
        with pytest.raises(RetryLater, match='429'):
            platform.cycle(conf)
    assert '9001' not in seen(manager, 'opiumpulses')
    assert not manager.state.value('opiumpulses', 'tries')


def test_opiumpulses_dropped_connection_is_not_held_against_the_giveaway(manager):  # noqa: F811
    platform, conf, _ = opiumPass(manager, {ENTER + '9002': (200, 'already entered')})
    original = platform.session.get

    def get(url, **kwargs):
        if url == ENTER + '9001':
            raise requests.ConnectionError('connection reset')
        return original(url, **kwargs)
    platform.session.get = get
    for _ in range(FAILED_TRIES):
        with pytest.raises(RetryLater, match='недоступен'):
            platform.cycle(conf)
    assert '9001' not in seen(manager, 'opiumpulses')
    assert not manager.state.value('opiumpulses', 'tries')


def test_opiumpulses_counter_goes_once_the_listing_shows_it_entered(manager):  # noqa: F811
    entered = OP_PAGE.replace('giveaways-page-item-img-btn-enter" href="/giveaways/enter/9001">'
                              'enter', 'giveaways-page-item-img-btn-entered" '
                              'href="/giveaways/enter/9001">entered')
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (200, 'no word on it'),
                                            ENTER + '9002': (200, 'already entered')})
    platform.cycle(conf)
    assert manager.state.value('opiumpulses', 'tries') == {'9001': 1}
    # The unconfirmed entry went through after all: the listing says so.
    platform.session.pages[LISTING] = (200, entered)
    platform.cycle(conf)
    assert manager.state.value('opiumpulses', 'tries') == {}
    assert '9001' in seen(manager, 'opiumpulses')


def test_giving_up_does_not_claim_failures_in_a_row(manager):  # noqa: F811
    # The counter keeps every failure, not only back-to-back ones.
    platform, conf, _ = opiumPass(manager, {ENTER + '9001': (404, 'gone'),
                                            ENTER + '9002': (200, 'already entered')})
    lines = []
    platform.info = lines.append
    for _ in range(FAILED_TRIES):
        platform.cycle(conf)
    last = [line for line in lines if 'больше не пробую' in line]
    assert len(last) == 1 and 'подряд' not in last[0]
    itchy = manager.platforms['itch']
    itchy.pause = lambda *a, **k: True
    itchy.active = lambda: [('7', 'Tiny Game', 'https://a.itch.io/tiny')]
    itchy.stillFree = lambda url: True
    itchy.claim = lambda url: False
    lines.clear()
    itchy.info = lines.append
    for _ in range(FAILED_TRIES):
        itchy.cycle(itchy.settings())
    assert 'больше не пробую' in lines[-1] and 'подряд' not in lines[-1]


class ItchPages(FakeItch):
    """itch.io answering per URL: {url: (status, text)}."""
    def __init__(self, pages):
        super().__init__()
        self.pages = pages

    def request(self, method, url, **kwargs):
        self.answer = self.pages[url] + (None, {})
        return super().request(method, url, **kwargs)


def test_itch_bad_gateway_on_the_sale_does_not_bury_the_game(manager):  # noqa: F811
    # Cloudflare's own 502 on data.json says nothing about the sale.
    data = 'https://a.itch.io/game/data.json'
    platform = manager.platforms['itch']
    platform.session = ItchPages({data: (502, '<html><h1>502 Bad Gateway</h1></html>')})
    platform.pause = lambda *a, **k: True
    platform.active = lambda: [('7', 'Some Game', 'https://a.itch.io/game')]
    claims = []
    platform.claim = lambda url: claims.append(url) and False
    conf = platform.settings()
    platform.cycle(conf)
    assert '7' not in seen(manager, 'itch')
    assert manager.state.value('itch', 'tries') == {'7': 1}
    assert claims == []
    # A real answer that the sale is over is final.
    platform.session.pages[data] = (200, '{"price": "$4.99", "sale": {"rate": 50}}')
    platform.cycle(conf)
    assert '7' in seen(manager, 'itch')
    assert manager.state.value('itch', 'tries') == {}


def test_itch_still_free_reads_only_real_answers(manager):  # noqa: F811
    data = 'https://a.itch.io/game/data.json'
    platform = manager.platforms['itch']
    for answer, expected in (((200, '{"price": "$0.00"}'), True),
                             ((200, '{"price": "$1.00", "sale": {"rate": 100}}'), True),
                             ((200, '{"price": "$1.00"}'), False),
                             ((503, 'busy'), None),
                             ((404, '{"errors": ["invalid game"]}'), None),
                             ((200, '{"errors": ["not found"]}'), None),
                             ((200, '<html>oops</html>'), None)):
        platform.session = ItchPages({data: answer})
        assert platform.stillFree('https://a.itch.io/game') is expected, answer
