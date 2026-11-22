"""SteamGifts bans for unactivated wins most. The farm takes a win's key from
the won page the bot already reads, keeps it on the win (ASF takes it when
auto_redeem is on) and reminds in the daily report until it is activated."""
import time

from bs4 import BeautifulSoup
from conftest import FakeSession, fixture

from test_farm import manager  # noqa: F401

from steamgiftbot.farm import steamgifts
from steamgiftbot.farm.steamgifts import wonKeys


def page(name='won_keys.html'):
    return BeautifulSoup(fixture(name), 'html.parser')


def setUp(manager, *wins):  # noqa: F811
    platform = manager.platforms['steamgifts']
    cards = []
    platform.notify = lambda text='', icon='', **card: cards.append((icon, card))
    for code, name in wins:
        platform.recordWin(name, f"https://www.steamgifts.com/giveaway/{code}/")
    return platform, cards


def winOf(manager, code):  # noqa: F811
    return next(win for win in manager.state.site('steamgifts')['wins'] if code in win['url'])


# ---- reading the page ----------------------------------------------------------

def test_keys_are_read_from_the_copy_button_the_key_box_and_the_row():
    assert wonKeys(page()) == {
        'key101': 'AAAAA-BBBBB-CCCCC',
        'key103': 'https://www.humblebundle.com/gift?key=FAKEGIFT',
        'key105': 'D4DDD-E5EEE-F6FFF',
        'key106': 'GGGGG-HHHHH-IIIII JJJJJ-KKKKK-LLLLL',
        'key109': 'https://www.gog.com/redeem/FAKEGOGCODE',
    }


def test_no_key_in_sight_reads_as_no_key():
    found = wonKeys(page())
    # 'View Key' not pressed yet; a game or user name shaped like a key, a key
    # in a comment, the store link and the sidebar are not keys.
    assert 'key102' not in found and 'key104' not in found and 'nav999' not in found


def test_words_and_shop_pages_are_not_taken_for_keys():
    found = wonKeys(page())
    # A lowercase tag and a shouted title in the row's text are no Steam key;
    # a shop's game page or the creator's site in the key box is no gift. A
    # wrong key would stick: the real one never replaces it.
    assert 'key107' not in found and 'key108' not in found
    assert 'gog.com/game' not in found['key109']


def test_a_link_from_the_copy_button_is_the_key():
    row = BeautifulSoup('<div class="table__row-inner-wrap">'
                        '<a class="table__column__heading" href="/giveaway/key110/x">X</a>'
                        '<i data-clipboard-text="https://store.example.com/k/AbC9"></i>'
                        '</div>', 'html.parser')
    assert steamgifts.rowKey(row) == 'https://store.example.com/k/AbC9'


def test_pages_without_keys_or_known_rows_give_nothing():
    assert wonKeys(page('won.html')) == {}
    assert wonKeys(page('won_unknown_layout.html')) == {}


# ---- onto the wins -------------------------------------------------------------

def test_a_key_goes_onto_the_win_and_is_told(manager):  # noqa: F811
    platform, cards = setUp(manager, ('key101', 'Hollow Knight'), ('key102', 'Celeste'))
    assert platform.keysFromWonPage(page()) == 1
    assert winOf(manager, 'key101')['cdkey'] == 'AAAAA-BBBBB-CCCCC'
    assert not winOf(manager, 'key102').get('cdkey')
    assert [icon for icon, _card in cards] == ['🔑']
    assert cards[0][1]['title'] == 'КЛЮЧ ПОЛУЧЕН' and 'AAAAA' not in str(cards[0])
    # Read again on the next pass: nothing new.
    assert platform.keysFromWonPage(page()) == 0
    assert len(cards) == 1


def test_a_key_already_on_the_win_is_kept(manager):  # noqa: F811
    platform, cards = setUp(manager, ('key101', 'Hollow Knight'))
    win = winOf(manager, 'key101')
    manager.setWinKey('steamgifts', win['time'], win['name'], 'XXXXX-YYYYY-ZZZZZ')
    assert platform.keysFromWonPage(page()) == 0
    assert winOf(manager, 'key101')['cdkey'] == 'XXXXX-YYYYY-ZZZZZ'
    assert cards == []


def test_an_activated_win_and_an_unknown_one_are_left_alone(manager):  # noqa: F811
    platform, cards = setUp(manager, ('key105', 'Oxenfree'))
    win = winOf(manager, 'key105')
    manager.state.setWinStatus('steamgifts', win['time'], win['name'], 'activated')
    assert platform.keysFromWonPage(page()) == 0
    assert not winOf(manager, 'key105').get('cdkey')
    # key101 is on the page but the farm never recorded it: no win made up.
    assert len(manager.state.site('steamgifts')['wins']) == 1
    assert platform.keysFromWonPage(None) == 0


def test_auto_redeem_sends_the_key_to_asf_and_asf_tells(manager):  # noqa: F811
    platform, cards = setUp(manager, ('key101', 'Hollow Knight'), ('key103', 'Stardew Valley'))
    manager.updateFarmSettings({'auto_redeem': True})
    sent = []
    manager.redeemWin = lambda key, moment, name, auto=False: sent.append(name)
    platform.keysFromWonPage(page())
    assert sent == ['Hollow Knight']
    # The gift link cannot go to ASF, so that one is told.
    assert [card['headline'] for _icon, card in cards] == ['Stardew Valley']


def test_a_broken_page_does_not_stop_the_farm(manager, monkeypatch):  # noqa: F811
    platform, cards = setUp(manager, ('key101', 'Hollow Knight'))
    monkeypatch.setattr(steamgifts, 'wonKeys', lambda soup: 1 / 0)
    assert platform.keysFromWonPage(page()) == 0


class WonBot:
    """The bot after a look at the won page: one fresh win, the page kept."""

    def __init__(self):
        self.wonPage = page()

    def announceWins(self):
        from steamgiftbot.wins import Win
        return [Win('key105', 'Oxenfree')]


def test_announce_records_the_win_then_takes_its_key(manager):  # noqa: F811
    platform, cards = setUp(manager)
    platform.announce(WonBot())
    assert winOf(manager, 'key105')['cdkey'] == 'D4DDD-E5EEE-F6FFF'


def test_the_bot_keeps_the_won_page_it_read(makeBot, tmp_path, monkeypatch):
    monkeypatch.setattr('steamgiftbot.bot.notify.send', lambda config, text, session=None: [])
    session = FakeSession(won=fixture('won_keys.html'))
    bot = makeBot(session, statePath=tmp_path / 'state.json')
    bot.session = session
    bot.announceWins()
    assert 'key101' in wonKeys(bot.wonPage)
    # Not read this time: no old page to take keys from.
    bot.checkWins = False
    bot.announceWins()
    assert bot.wonPage is None


# ---- the daily report ----------------------------------------------------------

def test_the_report_reminds_about_keys_not_activated(manager):  # noqa: F811
    old = time.time() - 3 * 86400
    manager.state.addWin('steamgifts', {'time': old, 'name': 'Celeste', 'url': '',
                                        'status': 'received', 'cdkey': 'AAAAA-BBBBB-CCCCC'})
    manager.state.addWin('steamgifts', {'time': old + 1, 'name': 'Done', 'url': '',
                                        'status': 'activated', 'cdkey': 'DDDDD-EEEEE-FFFFF'})
    manager.state.addWin('indiegala', {'time': old + 2, 'name': 'No Key', 'url': ''})
    card = manager.reportCard()
    text = card.plain()
    assert '🔑 Ключ есть, но не активирован: 1 (Celeste)' in text
    assert 'неактивированные' in card.note
    assert ('Выигрыши', manager.panelLink('/wins')) in card.buttons


def test_the_report_says_nothing_when_every_key_is_activated(manager):  # noqa: F811
    manager.state.addWin('steamgifts', {'time': time.time(), 'name': 'Done', 'url': '',
                                        'status': 'activated', 'cdkey': 'DDDDD-EEEEE-FFFFF'})
    assert 'не активирован' not in manager.reportCard().plain()
