"""Not spending points and requests on giveaways that cannot be won.

The numbers quoted here come from a sample of 126 live giveaways: three out of
five ask for a contributor level, the median had 554 entries.
"""
import pytest

from bs4 import BeautifulSoup
from conftest import FakeSession, fixture, makeSettings

from steamgiftbot import filters, ui
from steamgiftbot.giveaway import Giveaway, parseRow


def liveRows():
    soup = BeautifulSoup(fixture('giveaways_live.html'), 'html.parser')
    return [parseRow(item) for item
            in soup.find_all('div', {'class': 'giveaway__row-inner-wrap'})]


def make(**overrides):
    values = {'code': 'aaa11', 'name': 'Portal 2', 'cost': 30, 'appid': 620}
    values.update(overrides)
    return Giveaway(**values)


class TestReadingTheLiveRows:
    def test_entry_counts_are_read(self):
        rows = liveRows()
        assert [row.entries for row in rows] == [449, 1697, 160]

    def test_levels_are_read(self):
        # First row asks for nothing, the other two for level 1.
        assert [row.level for row in liveRows()] == [0, 1, 1]

    def test_the_region_locked_row_is_recognised(self):
        assert [row.regionLocked for row in liveRows()] == [False, False, True]

    def test_the_rest_of_the_row_still_parses(self):
        for row in liveRows():
            assert row.code and row.name and row.cost >= 0


class TestContributorLevel:
    def test_nothing_is_filtered_until_the_level_is_known(self):
        config = makeSettings(contributor_level=None)
        assert filters.reasonToSkip(make(level=10), config, 9999) is None

    def test_a_giveaway_above_your_level_is_skipped(self):
        config = makeSettings(contributor_level=2)
        assert filters.reasonToSkip(make(level=3), config, 9999) == filters.LEVEL_TOO_HIGH

    def test_your_own_level_qualifies(self):
        config = makeSettings(contributor_level=2)
        assert filters.reasonToSkip(make(level=2), config, 9999) is None

    def test_level_zero_is_a_real_answer_not_an_absent_one(self):
        # A level 0 account should still skip everything that asks for more.
        config = makeSettings(contributor_level=0)
        assert filters.reasonToSkip(make(level=1), config, 9999) == filters.LEVEL_TOO_HIGH
        assert filters.reasonToSkip(make(level=0), config, 9999) is None


class TestCrowding:
    def test_no_limit_by_default(self):
        assert filters.reasonToSkip(make(entries=5000), makeSettings(), 9999) is None

    def test_a_crowded_giveaway_is_skipped(self):
        config = makeSettings(max_entries=500)
        assert filters.reasonToSkip(make(entries=501), config, 9999) == filters.TOO_CROWDED

    def test_exactly_at_the_limit_is_fine(self):
        config = makeSettings(max_entries=500)
        assert filters.reasonToSkip(make(entries=500), config, 9999) is None

    def test_an_unknown_count_is_let_through(self):
        # The listing not saying is no reason to skip a possibly quiet giveaway.
        config = makeSettings(max_entries=500)
        assert filters.reasonToSkip(make(entries=None), config, 9999) is None


class TestRegion:
    def test_region_locked_giveaways_are_kept_by_default(self):
        # The row says the giveaway is restricted, not that you are excluded.
        assert filters.reasonToSkip(make(regionLocked=True), makeSettings(), 9999) is None

    def test_they_can_be_skipped_on_request(self):
        config = makeSettings(skip_region_locked=True)
        assert filters.reasonToSkip(make(regionLocked=True), config,
                                    9999) == filters.REGION_LOCKED


class TestTheCheapChecksComeFirst:
    def test_level_is_decided_before_the_store_is_asked(self):
        asked = []
        config = makeSettings(contributor_level=1, cards_only=True)
        reason = filters.reasonToSkip(make(level=5), config, 9999,
                                      hasCards=lambda appid: asked.append(appid) or True)
        assert reason == filters.LEVEL_TOO_HIGH
        assert asked == []

    def test_crowding_is_decided_before_the_store_is_asked(self):
        asked = []
        config = makeSettings(max_entries=100, cards_only=True)
        reason = filters.reasonToSkip(make(entries=900), config, 9999,
                                      hasCards=lambda appid: asked.append(appid) or True)
        assert reason == filters.TOO_CROWDED
        assert asked == []


class TestThroughTheBot:
    def test_the_live_page_is_filtered_by_level(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_live.html')})
        bot = makeBot(session, contributor_level=0)
        bot.updateInfo()
        bot.getGameContent()
        # Only the row that asks for no level survives.
        assert len(session.entered) == 1
        assert bot.stats.skipped[filters.LEVEL_TOO_HIGH] == 2

    def test_the_live_page_is_filtered_by_entries(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_live.html')})
        bot = makeBot(session, max_entries=500)
        bot.updateInfo()
        bot.getGameContent()
        # 1,697 entries is out; 449 and 160 stay.
        assert len(session.entered) == 2
        assert bot.stats.skipped[filters.TOO_CROWDED] == 1

    def test_nothing_is_filtered_without_the_settings(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_live.html')})
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert len(session.entered) == 3


class TestTheRecommendedValue:
    def test_it_is_the_measured_one(self):
        assert ui.RECOMMENDED_MAX_ENTRIES == 500

    def test_it_sits_above_the_point_where_too_little_qualifies(self):
        assert ui.RECOMMENDED_MAX_ENTRIES > ui.LOWEST_SENSIBLE_ENTRIES

    @pytest.mark.parametrize('text', ['0', '-5', 'many', '1.5'])
    def test_a_nonsense_entry_limit_is_refused(self, text):
        from prompt_toolkit.document import Document
        from prompt_toolkit.validation import ValidationError

        with pytest.raises(ValidationError):
            ui.NumberValidator(minimum=1).validate(Document(text))

    @pytest.mark.parametrize('text', ['1', '500', '9999', ''])
    def test_a_sensible_entry_limit_is_accepted(self, text):
        from prompt_toolkit.document import Document

        ui.NumberValidator(minimum=1).validate(Document(text))

    def test_level_zero_is_accepted_but_negative_is_not(self):
        from prompt_toolkit.document import Document
        from prompt_toolkit.validation import ValidationError

        ui.NumberValidator(minimum=0).validate(Document('0'))
        with pytest.raises(ValidationError):
            ui.NumberValidator(minimum=0).validate(Document('-1'))
