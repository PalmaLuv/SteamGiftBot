"""How the farm's workers pace themselves: retries after a failure, the
jitter on their own waits, SteamGifts' back-off on idle walks and the
User-Agent it sends."""
import threading
import time

import pytest
import requests

from test_farm import UA, FakeSteamGiftBot, FixedRandom, manager  # noqa: F401

from steamgiftbot.bot import CHALLENGE_MESSAGE, SteamGift, SteamGiftError
from steamgiftbot.bot import info as botInfo
from steamgiftbot.farm import base, steamgifts
from steamgiftbot.farm.steamgifts import FarmSteamGift


# ---- retries ---------------------------------------------------------------

def runFailing(platform, tries, error=None, run=None):
    """Runs the worker with a site that always fails (by raising `error`, or
    in its own `run`); returns the waits it asked for and the alerts it sent,
    each with the time spent waiting so far."""
    waits, sent = [], []
    platform.notify = lambda text='', icon='', **card: sent.append(
        (sum(waits), icon + ' ' + (card.get('headline') or text)))

    def failing():
        raise error or offline()

    def wait(seconds, sleeping=True, reason=''):
        waits.append(seconds)
        if len(waits) >= tries:
            platform.stopFlag.set()
            return False
        return True

    platform.run, platform.wait = run or failing, wait
    # In a thread of its own: loop() marks the thread as acting for the site.
    worker = threading.Thread(target=platform.loop, daemon=True)
    worker.start()
    worker.join(5)
    assert not worker.is_alive()
    return waits, sent


def offline():
    """What a site's request() raises while DNS is not up yet."""
    try:
        raise requests.ConnectionError("Failed to resolve 'www.indiegala.com'")
    except requests.ConnectionError as error:
        try:
            raise base.RetryLater(f"IndieGala недоступна: {error}") from error
        except base.RetryLater as retry:
            return retry


def test_first_retries_are_quick_and_the_alert_still_waits_an_hour(manager):  # noqa: F811
    waits, sent = runFailing(manager.platforms['indiegala'], 9)
    # DNS not up at boot: the site is back within a minute, not a quarter hour.
    assert waits == [60, 120, 300] + [base.ERROR_RETRY_SECONDS] * 6
    # One alert, after close to an hour of trouble (it was 45 min before).
    assert len(sent) == 1
    waited, text = sent[0]
    assert waited >= 50 * 60 and text.startswith('⚠️ Не работает уже 60 мин')


@pytest.mark.parametrize('error', [KeyError('x'), requests.ConnectTimeout('slow DNS')])
def test_unexpected_errors_retry_on_the_same_steps(manager, error):  # noqa: F811
    waits, sent = runFailing(manager.platforms['indiegala'], 5, error)
    assert waits == [60, 120, 300, base.ERROR_RETRY_SECONDS, base.ERROR_RETRY_SECONDS]
    assert sent == []


# A site that answered and asked for time is not hurried: three extra visits
# within eight minutes to a site that already suspects a bot would only make
# the block worse.
@pytest.mark.parametrize('error', [
    base.RetryLater("itch.io просит притормозить (HTTP 429)."),
    base.RetryLater("IndieGala показала проверку Incapsula."),
    base.RetryLater("IndieGala ответила HTTP 503."),
    requests.exceptions.RetryError("too many 429 error responses"),
])
def test_a_site_that_asks_for_time_waits_the_full_quarter_hour(manager, error):  # noqa: F811
    waits, sent = runFailing(manager.platforms['indiegala'], 5, error)
    assert waits == [base.ERROR_RETRY_SECONDS] * 5
    # As before the quick steps: the alert after the fourth try, ~45 min in.
    assert len(sent) == 1 and sent[0][0] == 3 * base.ERROR_RETRY_SECONDS


def test_retry_later_tells_an_outage_by_its_cause():
    assert base.networkDown(offline())
    assert base.networkDown(requests.ReadTimeout())
    assert not base.networkDown(base.RetryLater("itch.io просит притормозить (HTTP 429)."))
    # The site answered: urllib3 gave up on its 429s and 5xx.
    try:
        raise base.RetryLater("x") from requests.exceptions.RetryError("too many 429")
    except base.RetryLater as error:
        assert not base.networkDown(error)


# 'Could not reach SteamGifts' is an outage only when the network was down:
# urllib3 giving up on 429s comes through the same way.
@pytest.mark.parametrize('failure, down', [
    (requests.ConnectionError('no DNS'), True),
    (requests.exceptions.RetryError('too many 429 error responses'), False),
])
def test_steamgifts_unreachable_is_a_network_error(manager, monkeypatch,  # noqa: F811
                                                   failure, down):
    bot = SteamGift(manager.platforms['steamgifts'].loadConfig())

    def get(url, timeout=None):
        raise failure

    monkeypatch.setattr(bot.session, 'get', get)
    with pytest.raises(SteamGiftError) as caught:
        bot.updateInfo()
    try:
        raise base.RetryLater(str(caught.value)) from caught.value
    except base.RetryLater as error:
        assert base.networkDown(error) is down


class CheckedBot(FakeSteamGiftBot):
    """SteamGifts shows a Cloudflare check instead of its front page."""

    def updateInfo(self):
        raise SteamGiftError(CHALLENGE_MESSAGE)


def test_steamgifts_cloudflare_check_is_not_hurried(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(steamgifts, 'FarmSteamGift', CheckedBot)
    platform = manager.platforms['steamgifts']
    waits, sent = runFailing(platform, 2, run=platform.run)
    assert waits == [base.ERROR_RETRY_SECONDS] * 2


def test_a_good_pass_starts_the_quick_steps_again(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    platform.notify = lambda text='', icon='', **card: None
    assert [platform.retryDelay('x', quick=True) for _ in range(5)] == [60, 120, 300, 900, 900]
    platform.passStartedAt = time.time()
    platform.finishPass("Проход окончен: вошёл в 0")
    assert platform.retryDelay('x', quick=True) == 60
    # A site that never finishes a pass (GOG) gets the same once a try has
    # been working for a while.
    assert platform.retryDelay('x', quick=True) == 120
    platform.triedAt = time.time() - base.ERROR_RETRY_SECONDS
    assert platform.retryDelay('x', quick=True) == 60


def test_a_site_that_asked_for_time_ends_the_quick_steps(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    platform.notify = lambda text='', icon='', **card: None
    assert platform.retryDelay('x', quick=True) == 60
    assert platform.retryDelay('429') == 900
    # The same run of trouble: an outage after the 429 is not hurried either.
    assert platform.retryDelay('x', quick=True) == 900
    assert platform.failures == 3


def test_a_restart_starts_the_quick_steps_again(manager, monkeypatch):  # noqa: F811
    platform = manager.platforms['indiegala']
    monkeypatch.setattr(platform, 'notify', lambda text='', icon='', **card: None)
    for _ in range(6):
        platform.retryDelay('x', quick=True)
    assert platform.retryDelay('x', quick=True) == 900
    # The real stop and start, with a site that only fails once.
    monkeypatch.setattr(platform, 'run', lambda: None)
    platform.start()
    platform.thread.join(5)
    assert platform.retryDelay('x', quick=True) == 60


# ---- jitter ----------------------------------------------------------------

def test_own_waits_vary_by_a_fifth(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    seen = {platform.jittered(900) for _ in range(200)}
    assert min(seen) >= 720 and max(seen) <= 1080 and len(seen) > 20
    platform.rng = FixedRandom(1)
    assert platform.jittered(900) == 1080
    platform.rng = FixedRandom(-1)
    assert platform.jittered(900) == 720


def test_waiting_for_points_is_jittered(manager, tmp_path):  # noqa: F811
    platform = manager.platforms['steamgifts']
    platform.rng = FixedRandom(1)
    waits = []
    platform.wait = lambda seconds, sleeping=True, reason='': waits.append(seconds) or True
    bot = FarmSteamGift(platform, platform.loadConfig(), tmp_path / 'state.json')
    bot.points, bot.pointsWait = 5, 900
    bot.waitForPoints()
    assert waits == [1080]


def test_nothing_suits_pause_is_jittered(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(steamgifts, 'FarmSteamGift', FakeSteamGiftBot)
    platform = manager.platforms['steamgifts']
    platform.rng = FixedRandom(-1)
    waits = []

    def wait(seconds, sleeping=True, reason=''):
        waits.append(seconds)
        platform.stopFlag.set()
        return False

    platform.wait = wait
    platform.run()
    assert waits == [720]


# ---- idle walks --------------------------------------------------------------

class IdleBot(FakeSteamGiftBot):
    """Each walk takes its balance and entry count from the platform's script."""

    def getGameContent(self):
        points, entries = self.platform.script[self.walks]
        self.walks += 1
        self.points = points
        self.platform.sessionEntered += entries


def test_idle_walks_back_off_until_something_changes(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(steamgifts, 'FarmSteamGift', IdleBot)
    platform = manager.platforms['steamgifts']
    platform.rng = FixedRandom()
    platform.script = [
        (35, 0), (35, 0), (40, 0), (40, 0),   # balance stands still (+5 is not enough)
        (46, 0), (46, 0),                     # +11 since the run began: back to 15 min
        (30, 1),                              # an entry: back to 15 min
        (30, 0), (30, 0),
    ]
    waits = []

    def wait(seconds, sleeping=True, reason=''):
        waits.append(seconds)
        return len(waits) < len(platform.script)

    platform.wait = wait
    platform.run()
    assert waits == [900, 1800, 3600, 3600, 900, 1800, 900, 900, 1800]
    text = '\n'.join(line['text'] for line in platform.logLines())
    assert 'Проходов подряд без входов: 3, баланс не вырос на 10 P. ' \
           'Пауза увеличена до 60 мин.' in text
    assert 'Баланс вырос на 11 P: пауза между проходами снова 15 мин.' in text
    assert 'Был вход: пауза между проходами снова 15 мин.' in text


def test_idle_back_off_respects_a_longer_points_wait(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    platform.rng = FixedRandom()
    # points_wait set to two hours: never shortened, never stretched past it.
    assert [platform.idleWait(50, 0, 7200) for _ in range(3)] == [7200, 7200, 7200]
    platform.rng = FixedRandom(1)
    assert platform.idleWait(50, 0, 7200) == 7200 - 1440


def test_idle_back_off_jitter_stays_under_the_hour(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    for _ in range(2):
        platform.idleWait(50, 0, 900)
    # At the ceiling now: the jitter never takes the pause past 60 min, and
    # it still varies there.
    seen = {platform.idleWait(50, 0, 900) for _ in range(200)}
    assert max(seen) <= steamgifts.IDLE_MAX_WAIT and min(seen) >= 0.8 * steamgifts.IDLE_MAX_WAIT
    assert len(seen) > 20
    platform.rng = FixedRandom(1)
    assert platform.idleWait(50, 0, 900) == 2880
    # The log tells the wait it really is.
    text = [line['text'] for line in platform.logLines()][-1]
    assert text.endswith('Пауза увеличена до 48 мин.')


# ---- User-Agent ------------------------------------------------------------

CURL_SG = f"""curl 'https://www.steamgifts.com/' \\
  -b 'PHPSESSID=sess123; _ga=x' \\
  -H 'user-agent: {UA}'"""


def test_steamgifts_sends_the_browsers_user_agent(manager, tmp_path):  # noqa: F811
    platform = manager.platforms['steamgifts']
    assert platform.settings()['user_agent'] == base.DEFAULT_USER_AGENT
    bot = FarmSteamGift(platform, platform.loadConfig(), tmp_path / 'state.json')
    assert bot.session.headers['User-Agent'] == base.DEFAULT_USER_AGENT
    # The cURL the cookie came in also brings its browser's User-Agent.
    platform.updateSettings({'cookie': CURL_SG})
    assert platform.loadConfig().cookie == 'sess123'
    assert platform.settings()['user_agent'] == UA
    bot = FarmSteamGift(platform, platform.loadConfig(), tmp_path / 'state.json')
    assert bot.session.headers['User-Agent'] == UA
    # Typed in by hand it is kept; a new paste brings its own again, even
    # though the form sends the old field back along with it.
    platform.updateSettings({'user_agent': 'Firefox/150'})
    assert platform.settings()['user_agent'] == 'Firefox/150'
    platform.updateSettings({'cookie': CURL_SG, 'user_agent': 'Firefox/150'})
    assert platform.settings()['user_agent'] == UA
    # The field sits in the form next to the cookie.
    names = [item['name'] for item in platform.schema()]
    assert names.index('user_agent') == names.index('contributor_level') + 1


def test_steamgifts_check_uses_the_pasted_user_agent(manager, monkeypatch):  # noqa: F811
    agents = []
    monkeypatch.setattr(SteamGift, 'updateInfo',
                        lambda self: agents.append(self.session.headers['User-Agent']))
    platform = manager.platforms['steamgifts']
    platform.check({'cookie': CURL_SG})
    platform.check({'cookie': 'sess123'})
    assert agents == [UA, base.DEFAULT_USER_AGENT]


def test_command_line_bot_keeps_info_json_agent(manager):  # noqa: F811
    bot = SteamGift(manager.platforms['steamgifts'].loadConfig())
    assert bot.session.headers['User-Agent'] == botInfo['userAgent']
