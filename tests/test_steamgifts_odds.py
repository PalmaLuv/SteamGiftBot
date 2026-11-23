"""SteamGifts in the farm: the site's own filters on the listing address,
the best chance per point entered first, and saving up before spending."""
import pytest
from bs4 import BeautifulSoup

from test_farm import FakeSteamGiftBot, manager  # noqa: F401

from steamgiftbot.farm import steamgifts
from steamgiftbot.farm.steamgifts import FarmSteamGift, siteQuery
from steamgiftbot.giveaway import Giveaway, parseRow
from steamgiftbot.providers.base import EntryResult, Outcome


def row(code, cost, entries, copies=1):
    copiesTag = (f'<span class="giveaway__heading__thin">({copies} Copies)</span>'
                 if copies > 1 else '')
    return (f'<div class="giveaway__row-outer-wrap"><div class="giveaway__row-inner-wrap">'
            f'<a class="giveaway__heading__name" href="/giveaway/{code}/game">Game {code}</a>'
            f'{copiesTag}<span class="giveaway__heading__thin">({cost}P)</span>'
            f'<div class="giveaway__links"><a href="/giveaway/{code}/game/entries">'
            f'<span>{entries:,} entries</span></a></div></div></div>')


def page(*rows):
    return BeautifulSoup('<html><body>' + ''.join(rows) + '</body></html>', 'html.parser')


def test_copies_are_read_and_odds_count_them():
    soup = page(row('a1', 10, 99, copies=5), row('b2', 10, 99))
    first, second = [parseRow(r) for r in soup.find_all('div', class_='giveaway__row-inner-wrap')]
    assert (first.copies, second.copies) == (5, 1)
    assert first.odds == pytest.approx(5 / 100 / 10)
    assert first.odds > second.odds
    # A cheap crowded one against a dear quiet one: per point.
    assert Giveaway('c', 'c', 1, entries=999).odds == pytest.approx(1 / 1000)
    assert Giveaway('d', 'd', 50, entries=9).odds == pytest.approx(1 / 10 / 50)
    assert Giveaway('e', 'e', 5).odds < 0            # unknown entries go last


class Config:
    contributor_level = 0
    max_entries = 500
    max_cost = None


def test_site_filters_follow_the_settings():
    assert siteQuery(Config, {}, 45, 30) == '&level_max=0&entry_max=500&point_max=15'
    Config.max_cost = 10
    assert siteQuery(Config, {}, 45, 30).endswith('&point_max=10')
    Config.max_cost = None
    # Nothing to spare: no price filter (the walk waits for points anyway).
    assert 'point_max' not in siteQuery(Config, {}, 30, 30)
    assert siteQuery(Config, {'site_filters': False}, 45, 30) == ''


class Session:
    """The listing pages by number; records what was asked."""

    def __init__(self, pages):
        self.pages, self.asked = pages, []


def walkingBot(manager, monkeypatch, pages, points=100, **conf):  # noqa: F811
    platform = manager.platforms['steamgifts']
    platform.extra = {'max_pages': 10, **conf}
    bot = FarmSteamGift(platform, platform.loadConfig(), manager.dataDir / 'sg-state.json')
    bot.points, bot.min_points = points, 0
    asked, entered = [], []

    def getSoup(url):
        asked.append(url)
        number = int(url.split('page=')[1].split('&')[0])
        return page(*pages.get(number, []))
    monkeypatch.setattr(bot.provider, 'getSoup', getSoup)

    def enter(giveaway):
        entered.append(giveaway.code)
        bot.points -= giveaway.cost
        return EntryResult(Outcome.ENTERED)
    monkeypatch.setattr(bot.provider, 'enter', enter)
    monkeypatch.setattr(steamgifts, 'sleep', lambda *a: None, raising=False)
    monkeypatch.setattr('steamgiftbot.bot.sleep', lambda *a: None)
    platform.extraReason = lambda giveaway, points=None, minPoints=None: None
    return bot, asked, entered


def test_odds_order_enters_the_best_chance_first(manager, monkeypatch):  # noqa: F811
    pages = {1: [row('crowd', 5, 4000), row('quiet', 20, 9)],
             2: [row('multi', 10, 300, copies=10), row('crowd', 5, 4000)]}
    bot, asked, entered = walkingBot(manager, monkeypatch, pages, points=100)
    bot.getGameContent()
    # quiet 1/10/20 = .005, multi 10/301/10 = .0033, crowd 1/4001/5 = .00005
    assert entered == ['quiet', 'multi', 'crowd']
    assert len(asked) == 3                       # pages 1, 2 and the empty 3


def test_site_order_keeps_the_listing_order(manager, monkeypatch):  # noqa: F811
    pages = {1: [row('crowd', 5, 4000), row('quiet', 20, 9)]}
    bot, asked, entered = walkingBot(manager, monkeypatch, pages, order='site')
    bot.getGameContent()
    assert entered == ['crowd', 'quiet']


def test_the_walk_asks_the_site_to_filter(manager, monkeypatch):  # noqa: F811
    bot, asked, entered = walkingBot(manager, monkeypatch, {1: [row('a', 5, 10)]}, points=45)
    bot.config.contributor_level, bot.min_points = 0, 30
    bot.getGameContent()
    assert asked[0].endswith('search?page=1&level_max=0&point_max=15')
    # The address is put back for the next walk.
    assert '&' not in bot.provider.filterURL['All']


def test_a_filter_that_leaves_nothing_is_not_an_error(manager, monkeypatch):  # noqa: F811
    bot, asked, entered = walkingBot(manager, monkeypatch, {}, order='site')
    bot.config.contributor_level = 0
    bot.getGameContent()                         # the bot would raise 'Page is empty'
    assert entered == []


def test_points_running_out_end_the_odds_walk(manager, monkeypatch):  # noqa: F811
    pages = {1: [row('a', 30, 1), row('b', 30, 2), row('c', 30, 3)]}
    bot, asked, entered = walkingBot(manager, monkeypatch, pages, points=70)
    bot.min_points = 20
    waited = []
    monkeypatch.setattr(bot, 'waitForPoints', lambda: waited.append(bot.points))
    bot.getGameContent()
    assert entered == ['a', 'b'] and waited == [10]


# ---- saving up -----------------------------------------------------------------

def test_saving_waits_for_the_target_then_spends_down(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    conf = {'save_up_to': 300}
    assert platform.savingFor(120, conf) == 300
    assert platform.savingFor(310, conf) is None and platform.spending
    assert platform.savingFor(200, conf) is None          # still spending
    platform.spending = False                              # spent down
    assert platform.savingFor(200, conf) == 300
    assert platform.savingFor(500, {'save_up_to': 900}) is None   # capped at 400
    assert platform.savingFor(10, {}) is None and not platform.spending


class SavingBot(FakeSteamGiftBot):
    def getGameContent(self):
        self.walks += 1
        self.points = 20                          # spent down to the reserve
        self.waitedForPoints = True


def test_a_pass_while_saving_does_not_walk(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(steamgifts, 'FarmSteamGift', SavingBot)
    platform = manager.platforms['steamgifts']
    settings = platform.settings()
    settings['save_up_to'] = 300
    platform.updateSettings(settings)
    reasons = []
    points = iter([100, 350, 20, 20])

    def wait(seconds, sleeping=True, reason=''):
        reasons.append(reason)
        bot = SavingBot.instances[-1]
        bot.points = next(points, 20)
        if len(reasons) >= 4:
            platform.stopFlag.set()
        return True
    platform.wait = wait
    platform.gate = lambda: None if platform.stopFlag.is_set() else platform.settings()
    SavingBot.instances.clear()
    platform.run()
    bot = SavingBot.instances[-1]
    assert reasons[0] == 'Копит поинты: 100 из 300 P'
    assert bot.walks == 1                         # only once the target was reached
    assert reasons[-1].startswith('Копит поинты')
