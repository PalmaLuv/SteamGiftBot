"""The runner must not care which site it is working: a second site is one class."""
import pytest

from conftest import makeSettings

from steamgiftbot import filters, providers
from steamgiftbot.bot import SteamGift
from steamgiftbot.errors import SessionExpired
from steamgiftbot.giveaway import Giveaway
from steamgiftbot.providers.base import EntryResult, Outcome, Unreadable
from steamgiftbot.providers.steamgifts import SteamGiftsProvider
from steamgiftbot.wins import Win


class ToyProvider:
    """A site with no HTTP at all, scripted entirely in memory."""

    name = 'ToySite'

    def __init__(self, pages, points=100, outcomes=None, won=None):
        self.pages    = pages
        self.points   = points
        self.outcomes = list(outcomes or [])
        self.won      = won or []
        self.entered  = []
        self.session  = None
        self.xsrfToken = None

    def refresh(self):
        pass

    def listGiveaways(self, page):
        return self.pages.get(page, [])

    def enter(self, giveaway):
        self.entered.append(giveaway.code)
        outcome = self.outcomes.pop(0) if self.outcomes else EntryResult(Outcome.ENTERED)
        if outcome.outcome is Outcome.ENTERED:
            self.points -= giveaway.cost
        return outcome

    def fetchWins(self):
        return self.won, True

    def hasCards(self, appid):
        return True


def game(code, cost=10, **extra):
    return Giveaway(code=code, name=f"Game {code}", cost=cost, **extra)


@pytest.fixture
def runWith(monkeypatch, tmp_path):
    from steamgiftbot import bot as botModule
    monkeypatch.setattr(botModule, 'sleep', lambda *args, **kwargs: None)

    def factory(provider, **overrides):
        options = {'once': True, 'check_wins': True}
        options.update(overrides)
        return SteamGift(makeSettings(**options), statePath=tmp_path / 'state.json',
                         provider=provider)

    return factory


def test_the_runner_enters_through_any_provider(runWith):
    toy = ToyProvider({1: [game('a'), game('b', entered=True), game('c')]})
    bot = runWith(toy)
    assert bot.start() == 0
    assert toy.entered == ['a', 'c']
    assert bot.stats.entered == 2
    assert bot.stats.skipped[filters.ALREADY_ENTERED] == 1


def test_filters_apply_the_same_way(runWith):
    toy = ToyProvider({1: [game('cheap', cost=5), game('dear', cost=50)]})
    runWith(toy, max_cost=10).start()
    assert toy.entered == ['cheap']


def test_rate_limits_and_rejections_are_the_runners_business(runWith, monkeypatch):
    from steamgiftbot import bot as botModule
    waited = []
    monkeypatch.setattr(botModule, 'sleep', waited.append)

    toy = ToyProvider({1: [game('a'), game('b')]},
                      outcomes=[EntryResult(Outcome.RATE_LIMITED, wait=42),
                                EntryResult(Outcome.REJECTED, message='nope')])
    bot = runWith(toy)
    bot.start()
    assert 42 in waited
    assert bot.stats.rateLimited == 1
    assert bot.stats.rejected == 1


def test_unreadable_rows_are_named_after_the_site(runWith, capsys):
    toy = ToyProvider({1: [Unreadable('garbled'), game('a')]})
    bot = runWith(toy)
    bot.start()
    assert bot.stats.skipped[filters.UNREADABLE] == 1
    assert 'ToySite layout' in capsys.readouterr().out


def test_dry_run_spends_nothing_on_the_site(runWith):
    toy = ToyProvider({1: [game('a'), game('b')]})
    bot = runWith(toy, dry_run=True)
    bot.start()
    assert toy.entered == []
    assert bot.stats.entered == 2


def test_wins_come_from_the_provider(runWith, tmp_path):
    # A bot that has run before; a first run only writes history down.
    (tmp_path / 'state.json').write_text('{"announced_wins": []}', encoding='utf-8')
    toy = ToyProvider({1: []}, won=[Win(code='w1', name='Prize', base='https://toy.example')])
    bot = runWith(toy)
    assert [win.code for win in bot.announceWins()] == ['w1']
    # Remembered: the second look finds nothing new.
    assert bot.announceWins() == []


def test_a_dead_session_on_any_site_stops_the_run(runWith):
    class Expiring(ToyProvider):
        def refresh(self):
            raise SessionExpired("gone")

    assert runWith(Expiring({})).start() == 1


def test_steamgifts_satisfies_the_interface():
    provider = SteamGiftsProvider(makeSettings())
    for method in ('refresh', 'listGiveaways', 'enter', 'fetchWins', 'hasCards'):
        assert callable(getattr(provider, method))
    assert provider.name == 'SteamGifts'


def test_the_registry_builds_steamgifts_and_refuses_the_unknown():
    assert isinstance(providers.build(makeSettings()), SteamGiftsProvider)
    with pytest.raises(ValueError, match='unknown giveaway site'):
        providers.build(makeSettings(), 'nowhere')
