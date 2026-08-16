"""Watching the won page, and telling you about it exactly once."""
from bs4 import BeautifulSoup
from conftest import FakeSession, fixture

from steamgiftbot import wins
from steamgiftbot.state import State, defaultPath


def parseFixture(name='won.html'):
    return wins.parseWonPage(BeautifulSoup(fixture(name), 'html.parser'))


class TestReadingTheWonPage:
    def test_it_finds_every_win(self):
        found, recognised = parseFixture()
        assert recognised is True
        assert [win.code for win in found] == ['win001', 'win002', 'win003']

    def test_it_takes_the_name_from_the_link(self):
        found, _ = parseFixture()
        assert found[0].name == 'Hollow Knight'

    def test_an_empty_link_falls_back_to_the_slug(self):
        found, _ = parseFixture()
        assert found[2].name == 'Stardew Valley'

    def test_a_giveaway_link_outside_a_row_is_not_a_win(self):
        # The sidebar links to a giveaway too. Counting it would announce a game
        # that was never won.
        found, _ = parseFixture()
        assert 'nav999' not in [win.code for win in found]

    def test_an_unknown_layout_reports_nothing_rather_than_guessing(self):
        found, recognised = parseFixture('won_unknown_layout.html')
        assert found == []
        assert recognised is False

    def test_the_link_points_back_at_the_giveaway(self):
        found, _ = parseFixture()
        assert found[0].url == 'https://www.steamgifts.com/giveaway/win001/'

    def test_the_announcement_carries_name_and_link(self):
        found, _ = parseFixture()
        text = wins.announcement(found[0])
        assert 'Hollow Knight' in text
        assert 'win001' in text


class TestRemembering:
    def test_a_win_is_announced_once_and_not_again(self, makeBot, tmp_path):
        sent = []
        session = FakeSession(won=fixture('won.html'))
        statePath = tmp_path / 'state.json'

        bot = makeBot(session, statePath=statePath, telegram_token='T',
                      telegram_chat='42')
        bot.session = session
        bot.notifySpy = sent

        import steamgiftbot.bot as botModule
        original = botModule.notify.send
        botModule.notify.send = lambda config, text, session=None: sent.append(text) or []
        try:
            first = bot.announceWins()
            second = bot.announceWins()
        finally:
            botModule.notify.send = original

        assert [win.code for win in first] == ['win001', 'win002', 'win003']
        assert second == []
        assert len(sent) == 3

    def test_the_memory_survives_a_restart(self, makeBot, tmp_path, monkeypatch):
        session = FakeSession(won=fixture('won.html'))
        statePath = tmp_path / 'state.json'
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: [])

        first = makeBot(session, statePath=statePath, telegram_token='T', telegram_chat='42')
        first.session = session
        assert len(first.announceWins()) == 3

        # A fresh process, reading the same state file.
        second = makeBot(session, statePath=statePath, telegram_token='T', telegram_chat='42')
        second.session = session
        assert second.announceWins() == []

    def test_wins_show_up_in_the_summary(self, makeBot, tmp_path, monkeypatch):
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: [])
        session = FakeSession(won=fixture('won.html'))
        bot = makeBot(session, statePath=tmp_path / 'state.json')
        bot.announceWins()
        assert "You won 3 giveaways!" in bot.stats.summary()

    def test_checking_can_be_switched_off(self, makeBot, tmp_path):
        session = FakeSession(won=fixture('won.html'))
        bot = makeBot(session, statePath=tmp_path / 'state.json', check_wins=False)
        assert bot.announceWins() == []
        assert not any('won' in url for url in session.requested)


class TestTheStateFile:
    def test_it_starts_empty(self, tmp_path):
        state = State(tmp_path / 'state.json').load()
        assert state.announcedWins == set()
        assert state.isNew('anything') is True

    def test_it_round_trips(self, tmp_path):
        path = tmp_path / 'state.json'
        state = State(path).load()
        state.remember('abc12')
        assert state.save() is True

        assert State(path).load().isNew('abc12') is False

    def test_a_damaged_file_is_not_fatal(self, tmp_path):
        path = tmp_path / 'state.json'
        path.write_text('{ this is not json', encoding='utf-8')
        # Worst case is one repeated message; losing the run would be worse.
        assert State(path).load().announcedWins == set()

    def test_it_sits_next_to_the_config(self, tmp_path):
        assert defaultPath(tmp_path / 'config.ini').parent == tmp_path


class TestFailingSafely:
    def test_a_broken_won_page_does_not_stop_the_run(self, makeBot, tmp_path):
        session = FakeSession(won=fixture('won_unknown_layout.html'))
        bot = makeBot(session, statePath=tmp_path / 'state.json')
        assert bot.announceWins() == []

    def test_the_run_continues_when_the_won_page_errors(self, makeBot, tmp_path, capsys):
        from conftest import FakeResponse

        session = FakeSession()
        session.get = lambda url, **kwargs: FakeResponse('boom', status_code=500)
        bot = makeBot(session, statePath=tmp_path / 'state.json')
        assert bot.announceWins() == []
