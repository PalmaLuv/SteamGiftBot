"""A first run and a dry run must not flood the chat.

Found live: the first container run announced every game won months ago, and a
dry run sent real messages. A first run now writes history down quietly, and a
dry run neither sends nor saves anything.
"""
import json

import pytest

from conftest import FakeSession

from steamgiftbot.feeds import FreeGame, FreeGameWatcher
from steamgiftbot.state import State

HOOK = 'https://discord.com/api/webhooks/1/abc'


def wonPage(*codes):
    rows = ''.join(f'<div class="table__row-inner-wrap"><a href="/giveaway/{code}/game-{code}">'
                   f'Game {code}</a></div>' for code in codes)
    # An empty row keeps the page 'recognised' even with no wins on it.
    return f'<html><body>{rows}<div class="table__row-inner-wrap"></div></body></html>'


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('steamgiftbot.notify.send',
                        lambda config, text, session=None: messages.append(text) or [])
    return messages


def remembered(path):
    return set(json.loads(path.read_text(encoding='utf-8'))['announced_wins'])


class TestTheFirstRun:
    def test_old_wins_are_remembered_not_announced(self, makeBot, tmp_path, sent, capsys):
        statePath = tmp_path / 'state.json'
        bot = makeBot(FakeSession(won=wonPage('a1', 'b2', 'c3')), statePath=statePath,
                      discord_webhook=HOOK)

        assert bot.announceWins() == []
        assert sent == []
        assert remembered(statePath) == {'a1', 'b2', 'c3'}
        assert 'remembered 3 earlier wins' in capsys.readouterr().out
        assert bot.stats.won == 0

    def test_after_that_only_new_wins_are_announced(self, makeBot, tmp_path, sent):
        statePath = tmp_path / 'state.json'
        makeBot(FakeSession(won=wonPage('a1', 'b2')), statePath=statePath,
                discord_webhook=HOOK).announceWins()

        later = makeBot(FakeSession(won=wonPage('a1', 'b2', 'new9')), statePath=statePath,
                        discord_webhook=HOOK)
        assert [win.code for win in later.announceWins()] == ['new9']
        assert len(sent) == 1 and 'new9' in sent[0]

    def test_a_new_win_in_the_same_run_is_still_announced(self, makeBot, tmp_path, sent):
        session = FakeSession(won=wonPage('a1'))
        bot = makeBot(session, statePath=tmp_path / 'state.json', discord_webhook=HOOK)
        bot.announceWins()

        session.won = wonPage('a1', 'new9')
        assert [win.code for win in bot.announceWins()] == ['new9']

    def test_no_wins_yet_still_marks_the_first_run_done(self, makeBot, tmp_path, sent):
        statePath = tmp_path / 'state.json'
        makeBot(FakeSession(won=wonPage()), statePath=statePath).announceWins()
        assert statePath.exists()

        later = makeBot(FakeSession(won=wonPage('first1')), statePath=statePath,
                        discord_webhook=HOOK)
        assert [win.code for win in later.announceWins()] == ['first1']

    def test_a_damaged_memory_is_treated_like_a_first_run(self, makeBot, tmp_path, sent):
        statePath = tmp_path / 'state.json'
        statePath.write_text('{ not json', encoding='utf-8')
        bot = makeBot(FakeSession(won=wonPage('a1', 'b2')), statePath=statePath,
                      discord_webhook=HOOK)
        assert bot.announceWins() == []
        assert sent == []

    def test_state_knows_whether_it_read_anything(self, tmp_path):
        path = tmp_path / 'state.json'
        assert State(path).load().fresh is True
        path.write_text('{"announced_wins": []}', encoding='utf-8')
        assert State(path).load().fresh is False


class TestADryRunTouchesNothing:
    def test_it_sends_no_win_message_and_saves_nothing(self, makeBot, tmp_path, sent,
                                                        capsys):
        statePath = tmp_path / 'state.json'
        statePath.write_text('{"announced_wins": ["a1"]}', encoding='utf-8')
        bot = makeBot(FakeSession(won=wonPage('a1', 'new9')), statePath=statePath,
                      discord_webhook=HOOK, dry_run=True)

        assert bot.announceWins() == []
        assert sent == []
        assert remembered(statePath) == {'a1'}
        assert 'Would announce: you won Game new9' in capsys.readouterr().out

    def test_a_first_dry_run_leaves_the_first_real_run_its_job(self, makeBot, tmp_path, sent):
        statePath = tmp_path / 'state.json'
        makeBot(FakeSession(won=wonPage('a1')), statePath=statePath,
                dry_run=True).announceWins()
        assert not statePath.exists()

    def test_the_summary_stays_on_screen(self, makeBot, tmp_path, sent, capsys):
        bot = makeBot(statePath=tmp_path / 'state.json', discord_webhook=HOOK,
                      dry_run=True, once=True)
        bot.start()
        assert sent == []
        assert 'no message was sent' in capsys.readouterr().out

    def test_free_games_are_only_shown(self, tmp_path, sent, capsys):
        from conftest import makeSettings

        class Feed:
            name = 'GamerPower'

            def fetch(self):
                return [FreeGame(id='7', title='Free Thing', url='https://x/7')]

        state = State(tmp_path / 'state.json').load()
        watcher = FreeGameWatcher(Feed(), makeSettings(discord_webhook=HOOK, dry_run=True),
                                  state)
        assert watcher.announce() == []
        assert sent == []
        assert state.announcedFreeGames == set()
        assert not (tmp_path / 'state.json').exists()
        assert 'Would announce free to keep: Free Thing' in capsys.readouterr().out
