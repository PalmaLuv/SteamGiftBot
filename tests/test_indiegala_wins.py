"""IndieGala does not tell a win: the farm presses 'Check all' in the library
and reads 'Completed won', keeping each new win and its key."""
import json
import os
import time

import requests

from test_farm import FakeIndieGala, fixture, indiegala, manager  # noqa: F401

from steamgiftbot.farm import indiegala as ig

EMPTY = ('<html><body><li><div class="profile-private-page-library-no-results">'
         'This list is actually empty.</div></li></body></html>')


class FakeLibrary(FakeIndieGala):
    """The library part of www.indiegala.com: a backlog that 'Check all'
    goes through a page at a time, and the 'Completed won' list."""

    def __init__(self, won=EMPTY, backlog=(), **kwargs):
        super().__init__(**kwargs)
        self.won = won
        self.backlog = list(backlog)      # 'checked' answers, one per press
        self.calls = []

    def request(self, method, url, headers=None, data=None, **kwargs):
        if '/library/' not in url:
            return super().request(method, url, headers=headers, data=data, **kwargs)
        self.calls.append((method, url.replace(ig.BASE, '')))
        self.csrf.append((headers or {}).get('X-CSRFToken'))
        if url == ig.CHECK_ALL:
            checked = self.backlog.pop(0) if self.backlog else 0
            body = {'checked': checked, 'won': 0}
        elif url.startswith(ig.WON_LIST):
            body = {'status': 'ok', 'html': self.won}
        else:
            body = {}
        response = requests.models.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response


def setUp(manager, site, **conf):  # noqa: F811
    platform, conf = indiegala(manager, site, **conf)
    cards = []
    platform.notify = lambda text='', icon='', **card: cards.append((icon, text, card))
    return platform, conf, cards


def test_won_rows_give_the_key_or_the_gift_link():
    wins = ig.parseWon(fixture('indiegala_won.html'))
    assert [(w.id, w.name) for w in wins] == [('1217777', 'Pirate Guy 2 New Land'),
                                              ('1217789', 'Grav Blazer')]
    assert wins[0].url == ig.BASE + '/giveaways/card/pirate-guy-2-new-land/1217777'
    assert wins[0].serial == 'AAAAA-BBBBB-CCCCC'
    assert wins[1].serial == 'https://www.indiegala.com/gift?gift_id=abc123'
    assert ig.parseWon(EMPTY) == []


def test_a_new_win_is_kept_with_its_key_and_told_without_it(manager):  # noqa: F811
    site = FakeLibrary(backlog=[15, 15, 0])
    platform, conf, cards = setUp(manager, site)
    assert platform.checkWins() == []            # first look: nothing won yet
    assert [c for c in site.calls if c[0] == 'POST'] == [('POST', '/library/giveaways/'
                                                         'check-if-winner-all')] * 3
    site.won = fixture('indiegala_won.html')
    site.backlog = [2]
    fresh = platform.checkWins()
    assert [w.name for w in fresh] == ['Pirate Guy 2 New Land', 'Grav Blazer']
    wins = manager.state.site('indiegala')['wins']
    assert [w['name'] for w in wins] == ['Pirate Guy 2 New Land', 'Grav Blazer']
    assert wins[0]['cdkey'] == 'AAAAA-BBBBB-CCCCC'
    assert wins[1]['cdkey'] == 'https://www.indiegala.com/gift?gift_id=abc123'
    assert [icon for icon, _text, _card in cards] == ['🎉', '🎉']
    assert 'AAAAA' not in repr(cards)
    assert cards[0][2]['headline'] == 'Pirate Guy 2 New Land'
    assert set(site.csrf) == {'tok'}
    # Seen once, told once.
    cards.clear()
    assert platform.checkWins() == []
    assert cards == []
    assert len(manager.state.site('indiegala')['wins']) == 2


def test_keys_already_won_before_the_first_look_are_not_announced(manager):  # noqa: F811
    site = FakeLibrary(won=fixture('indiegala_won.html'))
    platform, conf, cards = setUp(manager, site)
    assert platform.checkWins() == []
    assert cards == []
    assert manager.state.site('indiegala').get('wins', []) == []


def test_wins_are_checked_every_few_hours_not_every_pass(manager):  # noqa: F811
    site = FakeLibrary()
    platform, conf, cards = setUp(manager, site)
    assert platform.winsDue()
    platform.checkWins()
    assert not platform.winsDue()
    manager.state.setFlag('indiegala', 'wins_checked_at', time.time() - ig.WIN_CHECK_EVERY - 1)
    assert platform.winsDue()


def test_an_unknown_won_page_is_kept_for_a_look(manager):  # noqa: F811
    site = FakeLibrary(won='<html><body><table><tr><td>New layout</td></tr></table></body></html>')
    platform, conf, cards = setUp(manager, site)
    platform.checkWins()
    saved = manager.dataDir / 'debug' / 'indiegala-won.html'
    assert saved.exists()
    if os.name != 'nt':      # Windows has no owner-only mode bits
        assert os.stat(saved).st_mode & 0o077 == 0


def test_auto_redeem_is_promised_only_for_a_steam_key(manager):  # noqa: F811
    site = FakeLibrary()
    platform, conf, cards = setUp(manager, site)
    platform.checkWins()
    settings = manager.farmSettings()
    sent = []
    manager.setWinKey = lambda key, moment, name, value: sent.append((name, value))
    manager.farmSettings = lambda: {**settings, 'auto_redeem': True}
    site.won = fixture('indiegala_won.html')
    platform.checkWins()
    notes = [card['note'] for _icon, _text, card in cards]
    assert 'ASF' in notes[0] and 'ASF' not in notes[1]
    assert sent == [('Pirate Guy 2 New Land', 'AAAAA-BBBBB-CCCCC'),
                    ('Grav Blazer', 'https://www.indiegala.com/gift?gift_id=abc123')]
