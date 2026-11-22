"""SteamGifts' restart on a settings save, safe even when the old worker is
slow to stop; its entries counted from the bot itself, not its log; and the
daily-limit wording every site shares."""
import threading
import time

from test_farm import manager  # noqa: F401
from test_steamgifts_odds import page, row

from steamgiftbot.bot import SteamGift
from steamgiftbot.farm import base, web
from steamgiftbot.farm.base import dailyReason
from steamgiftbot.farm.steamgifts import FarmSteamGift


def until(check, seconds=3):
    deadline = time.time() + seconds
    while not check() and time.time() < deadline:
        time.sleep(0.01)
    return check()


# ---- restart -----------------------------------------------------------------

def slowWorker(platform):
    """A worker whose first run does not hear the stop until `release` is
    set (a request that has not timed out yet); later runs just sleep."""
    runs, release = [], threading.Event()

    def run():
        runs.append(1)
        if len(runs) == 1:
            release.wait(5)
        else:
            platform.wait(3600)

    platform.run = run
    platform.configured = lambda: True
    return runs, release


def test_slow_stop_during_a_settings_save_still_ends_running(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base, 'RESTART_WAIT', 0.05)
    platform = manager.platforms['steamgifts']
    runs, release = slowWorker(platform)
    assert platform.start()
    assert until(lambda: runs)
    # The old worker is still busy when the wait runs out ...
    assert web.Handler.reloadSettings(platform) is True
    assert platform.running and platform.restartPending
    # ... and a second save meanwhile does not start a second worker.
    assert web.Handler.reloadSettings(platform) is True
    release.set()
    assert until(lambda: len(runs) == 2 and platform.state == base.SLEEPING)
    assert platform.running and not platform.stopped and not platform.restartPending
    time.sleep(0.1)
    assert len(runs) == 2
    platform.stop(wait=2)
    assert not platform.running


def test_stop_pressed_while_the_restart_waits_wins(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base, 'RESTART_WAIT', 0.05)
    platform = manager.platforms['steamgifts']
    runs, release = slowWorker(platform)
    platform.start()
    assert until(lambda: runs)
    assert platform.restart() is True
    platform.stop()
    release.set()
    assert until(lambda: not platform.running)
    time.sleep(0.1)
    assert len(runs) == 1 and not platform.running and platform.state == base.STOPPED


def test_stop_during_the_restart_wait_answers_at_once(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base, 'RESTART_WAIT', 3)
    platform = manager.platforms['steamgifts']
    runs, release = slowWorker(platform)
    platform.start()
    assert until(lambda: runs)
    result = []
    restarting = threading.Thread(target=lambda: result.append(platform.restart()))
    restarting.start()
    assert until(lambda: platform.restartPending)
    # The panel's Stop (or Telegram /stop) does not wait out the restart's join.
    began = time.time()
    platform.stop()
    assert time.time() - began < 1
    release.set()
    restarting.join(5)
    assert result == [False]
    time.sleep(0.1)
    assert len(runs) == 1 and not platform.running and not platform.restartPending


def test_start_during_the_restart_wait_starts_one_worker(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base, 'RESTART_WAIT', 3)
    platform = manager.platforms['steamgifts']
    runs, release = slowWorker(platform)
    platform.start()
    assert until(lambda: runs)
    result = []
    restarting = threading.Thread(target=lambda: result.append(platform.restart()))
    restarting.start()
    assert until(lambda: platform.restartPending)
    assert platform.start() is True
    release.set()
    restarting.join(5)
    assert result == [True]
    assert until(lambda: len(runs) == 2 and platform.state == base.SLEEPING)
    time.sleep(0.1)
    assert len(runs) == 2 and not platform.restartPending
    platform.stop(wait=2)


def test_start_while_still_stopping_is_not_lost(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    runs, release = slowWorker(platform)
    platform.start()
    assert until(lambda: runs)
    platform.stop()
    assert platform.start() is True          # used to say False and stay stopped
    release.set()
    assert until(lambda: len(runs) == 2 and platform.state == base.SLEEPING)
    platform.stop(wait=2)


def test_settings_save_leaves_a_stopped_site_stopped(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    slowWorker(platform)
    assert web.Handler.reloadSettings(platform) is False
    assert not platform.running


def test_quick_restart_starts_at_once(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    runs = []

    def run():
        runs.append(1)
        platform.wait(3600)

    platform.run = run
    platform.start()
    assert until(lambda: runs)
    assert platform.restart(wait=2) is True
    assert not platform.restartPending
    assert until(lambda: len(runs) == 2)
    platform.stop(wait=2)


# ---- entries -----------------------------------------------------------------

def enteringBot(manager, monkeypatch, pages):  # noqa: F811
    """A FarmSteamGift whose site answers every entry with success."""
    platform = manager.platforms['steamgifts']
    platform.extra = {'max_pages': 10, 'order': 'site'}
    platform.extraReason = lambda giveaway, points=None, minPoints=None: None
    bot = FarmSteamGift(platform, platform.loadConfig(), manager.dataDir / 'sg-state.json')
    bot.points, bot.min_points = 100, 0
    posted = []

    def getSoup(url):
        number = int(url.split('page=')[1].split('&')[0])
        return page(*pages.get(number, []))

    def entry(self, code, cost):
        posted.append(code)
        self.points -= cost
        return True

    monkeypatch.setattr(bot, 'GetSoupFromPage', getSoup)
    monkeypatch.setattr(SteamGift, 'entryGIFT', entry)
    monkeypatch.setattr('steamgiftbot.bot.sleep', lambda *a: None)
    return platform, bot, posted


def test_entry_is_recorded_once_with_cost_and_url(manager, monkeypatch):  # noqa: F811
    platform, bot, posted = enteringBot(manager, monkeypatch,
                                        {1: [row('abc12', 15, 42), row('def34', 5, 7)]})
    bot.getGameContent()
    assert posted == ['abc12', 'def34']
    entries = manager.state.data['steamgifts']['entries']
    assert [(e['name'], e['cost'], e['url'], e['entries']) for e in entries] == [
        ('Game abc12', 15, 'https://www.steamgifts.com/giveaway/abc12/', 42),
        ('Game def34', 5, 'https://www.steamgifts.com/giveaway/def34/', 7)]
    assert (platform.sessionEntered, platform.sessionSpent) == (2, 20)
    # The bot's own line stays, with the details under it. (Earlier tests'
    # sites still listen to the shared logger, so the line may come twice.)
    line = [item for item in platform.logLines()
            if item['text'] == 'One more game Game abc12'][-1]
    assert line['details']['cost'] == '15 P'
    assert line['details']['url'] == 'https://www.steamgifts.com/giveaway/abc12/'


def test_the_log_line_alone_records_nothing(manager):  # noqa: F811
    from steamgiftbot.console import log
    log("One more game Ghost", "green")
    assert manager.state.data.get('steamgifts', {}).get('entries', []) == []
    assert any(item['text'] == 'One more game Ghost'
               for item in manager.platforms['steamgifts'].logLines())


def test_dry_run_records_nothing(manager, monkeypatch):  # noqa: F811
    platform, bot, posted = enteringBot(manager, monkeypatch, {1: [row('abc12', 15, 42)]})
    bot.dryRun = True
    bot.getGameContent()
    assert posted == [] and platform.sessionEntered == 0
    assert manager.state.data.get('steamgifts', {}).get('entries', []) == []


def test_refused_entry_records_nothing(manager, monkeypatch):  # noqa: F811
    platform, bot, posted = enteringBot(manager, monkeypatch, {1: [row('abc12', 15, 42)]})
    monkeypatch.setattr(SteamGift, 'entryGIFT', lambda self, code, cost: False)
    bot.getGameContent()
    assert platform.sessionEntered == 0


# ---- daily limits --------------------------------------------------------------

def test_daily_reason_words_both_limits():
    assert dailyReason(5, None, None) is None
    assert dailyReason(5, 0, None) == 'дневной лимит входов'
    assert dailyReason(5, 0, 1) == 'дневной лимит входов'     # the entry limit first
    assert dailyReason(5, 3, 4) == 'дневной лимит трат'
    assert dailyReason(5, 3, 5) is None
    assert dailyReason(0, 3, 0) is None                         # a free one still fits


def test_sites_share_the_daily_wording(manager):  # noqa: F811
    from steamgiftbot.farm.indiegala import IndieGalaPlatform
    from steamgiftbot.farm.steamgifts import SteamGiftsPlatform
    from steamgiftbot.giveaway import Giveaway

    class Ticket:
        price = 10

    conf = {'priority_reserve': True, 'reserve': 0}
    assert IndieGalaPlatform.budgetReason(conf, Ticket, False, 100, 0, None) == \
        'дневной лимит входов'
    assert IndieGalaPlatform.budgetReason(conf, Ticket, False, 100, None, 5) == \
        'дневной лимит трат'
    assert SteamGiftsPlatform.budgetReason(Giveaway('a', 'A', 10), 100, 0, 5, set()) == \
        'дневной лимит трат'
    # SteamGifts' refusal still comes before the limit, as it did.
    assert SteamGiftsPlatform.budgetReason(Giveaway('a', 'A', 10), 100, 0, 5, {'no:a'}) == \
        'SteamGifts уже отказал'
