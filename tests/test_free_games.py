"""Free games from GamerPower: read, announce once, never claimed."""
import json

import pytest
import requests

from conftest import FakeResponse, makeSettings

from steamgiftbot import settings
from steamgiftbot.feeds import FreeGame, FreeGameWatcher
from steamgiftbot.feeds.gamerpower import GamerPowerFeed
from steamgiftbot.state import State

# Shaped like a live answer from /api/filter, trimmed.
OFFER = {
    "id": 3782,
    "title": "Shogun Showdown (Epic Games) Giveaway",
    "worth": "$14.99",
    "open_giveaway_url": "https://www.gamerpower.com/open/shogun-showdown-epic-games-giveaway",
    "gamerpower_url": "https://www.gamerpower.com/shogun-showdown-epic-games-giveaway",
    "type": "Game",
    "platforms": "PC, Epic Games Store",
    "end_date": "2026-09-24 23:59:00",
    "status": "Active",
}


class FakeApi:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def get(self, url, params=None, **kwargs):
        self.asked.append((url, params))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def listing(*offers, status_code=200):
    return FakeResponse(json.dumps(list(offers)), status_code=status_code)


class TestReadingGamerPower:
    def test_an_offer_becomes_a_free_game(self):
        api = FakeApi(listing(OFFER))
        games = GamerPowerFeed(('steam', 'epic-games-store'), session=api).fetch()

        assert games == [FreeGame(
            id='3782', title='Shogun Showdown (Epic Games)',
            url=OFFER['open_giveaway_url'], worth='$14.99',
            platforms='PC, Epic Games Store', endDate='2026-09-24 23:59:00')]

    def test_it_asks_for_full_games_on_the_chosen_platforms(self):
        api = FakeApi(listing())
        GamerPowerFeed(('steam', 'gog'), session=api).fetch()
        assert api.asked[0][1] == {'platform': 'steam.gog', 'type': 'game'}

    def test_nothing_active_is_an_empty_list(self):
        quiet = FakeResponse('{"status":0,"status_message":"No active giveaways"}',
                             status_code=201)
        assert GamerPowerFeed(('steam',), session=FakeApi(quiet)).fetch() == []

    def test_ended_and_malformed_offers_are_dropped(self):
        ended = dict(OFFER, id=1, status='Expired')
        noLink = dict(OFFER, id=2, open_giveaway_url='', gamerpower_url='')
        api = FakeApi(listing(ended, noLink, 'junk', OFFER))
        assert [game.id for game in GamerPowerFeed(('pc',), session=api).fetch()] == ['3782']

    @pytest.mark.parametrize('url', ['javascript:alert(1)', 'http://plain.example/x',
                                     'ftp://x/y'])
    def test_only_https_links_are_passed_on(self, url):
        api = FakeApi(listing(dict(OFFER, open_giveaway_url=url, gamerpower_url='')))
        assert GamerPowerFeed(('pc',), session=api).fetch() == []

    def test_n_a_is_not_shown(self):
        api = FakeApi(listing(dict(OFFER, worth='N/A', end_date='N/A')))
        game = GamerPowerFeed(('pc',), session=api).fetch()[0]
        assert game.worth == '' and game.endDate == ''

    @pytest.mark.parametrize('answer', [
        requests.ConnectionError('down'),
        FakeResponse('oops', status_code=503),
        FakeResponse('<html>not json</html>'),
    ])
    def test_trouble_is_unknown_and_logged(self, answer, capsys):
        assert GamerPowerFeed(('pc',), session=FakeApi(answer)).fetch() is None
        assert 'GamerPower' in capsys.readouterr().out


class StaticFeed:
    name = 'GamerPower'

    def __init__(self, *rounds):
        self.rounds = list(rounds)

    def fetch(self):
        return self.rounds.pop(0)


def game(code):
    return FreeGame(id=code, title=f"Game {code}", url=f"https://x/{code}")


class TestAnnouncing:
    def watcher(self, tmp_path, feed, monkeypatch, **config):
        sent = []
        monkeypatch.setattr('steamgiftbot.feeds.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])
        state = State(tmp_path / 'state.json').load()
        settingsWithHook = makeSettings(
            discord_webhook='https://discord.com/api/webhooks/1/x', **config)
        return FreeGameWatcher(feed, settingsWithHook, state), sent, state

    def test_new_games_arrive_in_one_message_crediting_gamerpower(self, tmp_path, monkeypatch):
        watcher, sent, _ = self.watcher(tmp_path, StaticFeed([game('1'), game('2')]),
                                        monkeypatch)
        assert len(watcher.announce()) == 2
        assert len(sent) == 1
        assert 'via GamerPower' in sent[0]
        assert 'Game 1' in sent[0] and 'Game 2' in sent[0]

    def test_a_game_is_announced_once_even_across_runs(self, tmp_path, monkeypatch):
        watcher, sent, _ = self.watcher(tmp_path, StaticFeed([game('1')]), monkeypatch)
        watcher.announce()

        again, sentAgain, _ = self.watcher(tmp_path, StaticFeed([game('1'), game('2')]),
                                           monkeypatch)
        assert [g.id for g in again.announce()] == ['2']

    def test_ended_offers_are_forgotten(self, tmp_path, monkeypatch):
        watcher, _, state = self.watcher(
            tmp_path, StaticFeed([game('1'), game('2')], [game('2')]), monkeypatch)
        watcher.announce()
        watcher.announce()
        assert state.announcedFreeGames == {'2'}

    def test_an_unreachable_feed_changes_nothing(self, tmp_path, monkeypatch):
        watcher, sent, state = self.watcher(tmp_path, StaticFeed(None), monkeypatch)
        state.rememberFreeGame('1')
        assert watcher.announce() == []
        assert sent == [] and state.announcedFreeGames == {'1'}


class TestTheSetting:
    def test_platforms_accept_the_usual_short_names(self):
        assert settings.toPlatforms('Steam, epic, GOG, steam') == \
            ('steam', 'epic-games-store', 'gog')

    def test_an_unknown_platform_is_refused(self):
        with pytest.raises(ValueError, match='unknown platform'):
            settings.toPlatforms('steam, dreamcast')

    def test_off_by_default_and_on_when_asked(self, makeBot):
        assert makeBot().freeGames is None
        bot = makeBot(free_games=('steam',))
        assert isinstance(bot.freeGames.feed, GamerPowerFeed)


def test_an_old_state_file_still_reads_and_stays_the_same(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text('{"announced_wins": ["abc"]}', encoding='utf-8')
    state = State(path).load()
    assert state.announcedFreeGames == set()
    state.save()
    assert json.loads(path.read_text(encoding='utf-8')) == {'announced_wins': ['abc']}
