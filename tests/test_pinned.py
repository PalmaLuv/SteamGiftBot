"""Pinned detection must not hang on one spelling of one CSS class."""
from bs4 import BeautifulSoup
from conftest import FakeSession, fixture

from steamgiftbot.giveaway import parseRow


def parsedRows(name='giveaways_pinned_variants.html'):
    soup = BeautifulSoup(fixture(name), 'html.parser')
    rows = soup.find_all('div', {'class': 'giveaway__row-inner-wrap'})
    return {row.code: row for row in (parseRow(item) for item in rows) if row}


class TestSpellings:
    def test_a_marked_row_is_pinned(self):
        assert parsedRows()['pin01'].pinned is True

    def test_a_wrapped_row_is_pinned(self):
        # The row itself carries nothing; only its container does.
        assert parsedRows()['pin02'].pinned is True

    def test_an_unnamed_extra_class_is_not_a_marker(self):
        # The bot used to read any second class as 'pinned'. A live listing
        # showed ordinary rows carrying 'has-description', so three out of four
        # giveaways on a page were being skipped.
        assert parsedRows()['desc01'].pinned is False

    def test_an_ordinary_row_stays_ordinary(self):
        assert parsedRows()['plain1'].pinned is False


class TestAgainstTheLivePage:
    def test_real_rows_are_never_mistaken_for_pinned(self):
        rows = parsedRows('giveaways_live.html')
        assert len(rows) >= 2
        assert all(row.pinned is False for row in rows.values())

    def test_real_rows_parse_completely(self):
        for row in parsedRows('giveaways_live.html').values():
            assert row.code
            assert row.name
            assert row.cost >= 0
            # Live store links look like /app/1234?utm_source=SteamGifts,
            # with no trailing slash and a query string attached.
            assert row.appid is None or row.appid > 0


class TestEnteredWins:
    def test_an_entered_row_is_never_reported_as_pinned(self):
        # 'is-faded' is an extra class too, and used to trip the old heuristic.
        html = ('<div class="giveaway__row-inner-wrap is-faded">'
                '<a class="giveaway__heading__name" href="/giveaway/x1/y">Y</a>'
                '<span class="giveaway__heading__thin">(10P)</span></div>')
        row = parseRow(BeautifulSoup(html, 'html.parser').find('div'))
        assert row.entered is True
        assert row.pinned is False


class TestThroughTheBot:
    def test_marked_rows_are_skipped_when_pinned_is_off(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_pinned_variants.html')})
        bot = makeBot(session, pinned=False)
        bot.updateInfo()
        bot.getGameContent()
        # Both pinned spellings stay out; the described row is an ordinary
        # giveaway and must be entered like any other.
        assert session.entered == ['desc01', 'plain1']

    def test_marked_rows_are_entered_when_pinned_is_on(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_pinned_variants.html')})
        bot = makeBot(session, pinned=True)
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == ['pin01', 'pin02', 'desc01', 'plain1']
