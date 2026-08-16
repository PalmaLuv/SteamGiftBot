import pytest

from bs4 import BeautifulSoup
from conftest import fixture, makeSettings

from steamgiftbot import filters
from steamgiftbot.giveaway import Giveaway, parseRow


def rows():
    soup = BeautifulSoup(fixture('giveaways.html'), 'html.parser')
    return soup.find_all('div', {'class': 'giveaway__row-inner-wrap'})


def make(**overrides):
    values = {'code': 'aaa11', 'name': 'Portal 2', 'cost': 30, 'appid': 620}
    values.update(overrides)
    return Giveaway(**values)


class TestParsingARow:
    def test_it_reads_every_field(self):
        giveaway = parseRow(rows()[0])
        assert giveaway.code == 'aaa11'
        assert giveaway.name == 'Portal 2'
        # The last thin span is the price; the first one is the copy count.
        assert giveaway.cost == 30
        assert giveaway.appid == 620
        assert giveaway.entered is False
        assert giveaway.pinned is False

    def test_it_marks_an_entered_giveaway(self):
        assert parseRow(rows()[1]).entered is True

    def test_it_marks_a_pinned_giveaway(self):
        giveaway = parseRow(rows()[2])
        assert giveaway.pinned is True
        assert giveaway.entered is False

    def test_a_package_link_yields_no_app_id(self):
        # store.steampowered.com/sub/... is a bundle, not an app.
        assert parseRow(rows()[3]).appid is None

    @pytest.mark.parametrize('html', [
        '<div class="giveaway__row-inner-wrap"></div>',
        '<div class="giveaway__row-inner-wrap">'
        '<a class="giveaway__heading__name" href="/giveaway/x/y">No price</a></div>',
        '<div class="giveaway__row-inner-wrap">'
        '<span class="giveaway__heading__thin">(free)</span></div>',
    ])
    def test_a_row_it_cannot_read_is_skipped(self, html):
        item = BeautifulSoup(html, 'html.parser').find('div')
        assert parseRow(item) is None


class TestCost:
    def test_no_limit_by_default(self):
        assert filters.reasonToSkip(make(cost=5000), makeSettings(), 9999) is None

    def test_above_the_limit_is_skipped(self):
        config = makeSettings(max_cost=50)
        assert filters.reasonToSkip(make(cost=51), config, 9999) == filters.TOO_EXPENSIVE

    def test_exactly_at_the_limit_is_fine(self):
        config = makeSettings(max_cost=50)
        assert filters.reasonToSkip(make(cost=50), config, 9999) is None

    def test_an_unaffordable_game_is_skipped(self):
        assert filters.reasonToSkip(make(cost=30), makeSettings(), 29) == filters.NOT_ENOUGH


class TestNameLists:
    def test_a_blacklisted_word_skips_the_game(self):
        config = makeSettings(blacklist=('hentai', 'simulator'))
        assert filters.reasonToSkip(make(name='Bus Simulator 21'), config,
                                    9999) == filters.BLACKLISTED

    def test_matching_ignores_case(self):
        config = makeSettings(blacklist=('SIMULATOR',))
        assert filters.reasonToSkip(make(name='bus simulator'), config,
                                    9999) == filters.BLACKLISTED

    def test_an_unlisted_game_passes(self):
        config = makeSettings(blacklist=('hentai',))
        assert filters.reasonToSkip(make(name='Portal 2'), config, 9999) is None

    def test_a_whitelist_keeps_everything_else_out(self):
        config = makeSettings(whitelist=('portal',))
        assert filters.reasonToSkip(make(name='RimWorld'), config,
                                    9999) == filters.NOT_WHITELISTED
        assert filters.reasonToSkip(make(name='Portal 2'), config, 9999) is None

    def test_an_empty_list_filters_nothing(self):
        assert filters.reasonToSkip(make(), makeSettings(whitelist=()), 9999) is None

    def test_the_blacklist_wins_over_the_whitelist(self):
        config = makeSettings(blacklist=('portal',), whitelist=('portal',))
        assert filters.reasonToSkip(make(name='Portal 2'), config,
                                    9999) == filters.BLACKLISTED


class TestTradingCards:
    def test_the_store_is_not_asked_unless_the_setting_is_on(self):
        asked = []
        filters.reasonToSkip(make(), makeSettings(), 9999,
                             hasCards=lambda appid: asked.append(appid))
        assert asked == []

    def test_a_game_with_cards_passes(self):
        config = makeSettings(cards_only=True)
        assert filters.reasonToSkip(make(), config, 9999, hasCards=lambda appid: True) is None

    def test_a_game_without_cards_is_skipped(self):
        config = makeSettings(cards_only=True)
        assert filters.reasonToSkip(make(), config, 9999,
                                    hasCards=lambda appid: False) == filters.NO_CARDS

    def test_a_bundle_cannot_be_checked_so_it_is_skipped(self):
        config = makeSettings(cards_only=True)
        assert filters.reasonToSkip(make(appid=None), config, 9999,
                                    hasCards=lambda appid: True) == filters.UNKNOWN_APP

    def test_cheaper_reasons_are_decided_first(self):
        # A store request should not be spent on a game we cannot afford anyway.
        config = makeSettings(cards_only=True)
        asked = []

        def hasCards(appid):
            asked.append(appid)
            return True

        assert filters.reasonToSkip(make(cost=99), config, 10, hasCards) == filters.NOT_ENOUGH
        assert asked == []


class TestOrderOfChecks:
    def test_an_entered_giveaway_is_reported_as_such(self):
        assert filters.reasonToSkip(make(entered=True), makeSettings(),
                                    9999) == filters.ALREADY_ENTERED

    def test_pinned_depends_on_the_setting(self):
        assert filters.reasonToSkip(make(pinned=True), makeSettings(pinned=False),
                                    9999) == filters.PINNED
        assert filters.reasonToSkip(make(pinned=True), makeSettings(pinned=True),
                                    9999) is None
