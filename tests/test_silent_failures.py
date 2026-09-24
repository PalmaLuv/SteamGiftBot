"""Failures that used to pass without a word: each one must now be seen."""
import pytest

from conftest import FakeResponse, FakeSession, fixture

from steamgiftbot import filters, notify, steam_api, ui
from steamgiftbot.bot import SessionExpired
from steamgiftbot.state import State

UNREADABLE_ROW = ('<div class="giveaway__row-inner-wrap">'
                  '<a class="giveaway__heading__name" href="/giveaway/zz{n}/odd">Odd {n}</a>'
                  '<span class="giveaway__heading__thin">(free?)</span></div>')


def unreadablePage(count):
    rows = ''.join(UNREADABLE_ROW.format(n=n) for n in range(count))
    return f'<html><body>{rows}</body></html>'


class TestTheStoreBeingDown:
    def test_an_unanswered_card_check_is_counted_apart_from_a_real_no(self, makeBot,
                                                                      monkeypatch):
        monkeypatch.setattr(steam_api, '_lookUp', lambda appid: None)
        session = FakeSession()
        bot = makeBot(session, cards_only=True)
        bot.updateInfo()
        bot.getGameContent()

        assert session.entered == []
        assert bot.stats.skipped[filters.CARDS_UNKNOWN] >= 1
        assert bot.stats.skipped[filters.NO_CARDS] == 0


class TestUnreadableRows:
    def test_they_are_counted_and_reported_once(self, makeBot, capsys):
        session = FakeSession(pages={1: unreadablePage(3)})
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()

        assert bot.stats.skipped[filters.UNREADABLE] == 3
        assert capsys.readouterr().out.count('Could not read a giveaway row') == 1
        assert filters.UNREADABLE in bot.stats.summary()


class TestWinsAndADeadSession:
    def test_a_dead_session_is_not_swallowed_by_the_wins_check(self, makeBot, monkeypatch):
        bot = makeBot()

        def expired(url):
            raise SessionExpired("gone")

        monkeypatch.setattr(bot, 'GetSoupFromPage', expired)
        with pytest.raises(SessionExpired):
            bot.announceWins()

    def test_the_run_stops_with_the_session_advice(self, makeBot, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])
        bot = makeBot(once=True, discord_webhook='https://hook')
        original = bot.GetSoupFromPage

        def expiresOnWins(url):
            if url.endswith('/giveaways/won'):
                raise SessionExpired("gone")
            return original(url)

        monkeypatch.setattr(bot, 'GetSoupFromPage', expiresOnWins)
        assert bot.start() == 1
        assert 'PHPSESSID' in sent[0]


class TestTheStateFileSpeaksUp:
    def test_a_missing_file_is_quiet(self, tmp_path, capsys):
        State(tmp_path / 'absent.json').load()
        assert capsys.readouterr().out == ''

    def test_a_damaged_file_is_reported(self, tmp_path, capsys):
        path = tmp_path / 'state.json'
        path.write_text('{not json', encoding='utf-8')
        State(path).load()
        assert 'damaged' in capsys.readouterr().out

    def test_a_failed_save_is_reported(self, tmp_path, capsys):
        # A directory where the file should be makes the write fail everywhere.
        path = tmp_path / 'state.json'
        path.mkdir()
        assert State(path).save() is False
        assert 'Could not save' in capsys.readouterr().out


class TestThePasteHotkey:
    def test_it_is_removed_even_when_the_prompt_is_interrupted(self, monkeypatch):
        removed = []

        class FakeKeyboard:
            def add_hotkey(self, *args):
                pass

            def remove_hotkey(self, name):
                removed.append(name)

        def interrupted(questions):
            raise KeyboardInterrupt

        monkeypatch.setattr(ui, 'PASTE_HOTKEY', True)
        monkeypatch.setattr(ui, 'keyboard', FakeKeyboard(), raising=False)
        monkeypatch.setattr(ui, 'prompt', interrupted)

        with pytest.raises(KeyboardInterrupt):
            ui.ask('input', 'cookie', 'Enter it')
        assert removed == ['ctrl+v']


class TestNotifyOnlyForgivesBadJson:
    def test_a_non_json_body_is_described_by_its_text(self):
        assert notify.describe(FakeResponse('<html>bad gateway</html>')) == \
            '<html>bad gateway</html>'

    def test_a_programming_error_is_not_hidden(self):
        class Broken:
            status_code = 200

            def json(self):
                raise AttributeError("bug")

        with pytest.raises(AttributeError):
            notify.checkAnswer(Broken(), 'Discord')


class TestOneSourceForTheSite:
    def test_win_links_follow_the_configured_site(self):
        from bs4 import BeautifulSoup

        from steamgiftbot import wins

        page = ('<div class="table__row-inner-wrap">'
                '<a href="/giveaway/abc12/some-game">Some Game</a></div>')
        found, _ = wins.parseWonPage(BeautifulSoup(page, 'html.parser'),
                                     'https://mirror.example')
        assert found[0].url == 'https://mirror.example/giveaway/abc12/'

    @pytest.mark.parametrize('text, expected', [
        ('<title>Just a moment...</title>', True),
        ('<script src="https://challenges.cloudflare.com/x"></script>', True),
        ('<html>maintenance</html>', False),
        (None, False),
    ])
    def test_the_cloudflare_check_is_recognised_in_one_place(self, text, expected):
        from steamgiftbot.bot import isChallenge
        assert isChallenge(text) is expected


def test_the_fixture_pages_still_read_cleanly(makeBot):
    # The real listing must not trip the unreadable counter.
    bot = makeBot(FakeSession(pages={1: fixture('giveaways.html')}))
    bot.updateInfo()
    bot.getGameContent()
    assert bot.stats.skipped[filters.UNREADABLE] == 0
