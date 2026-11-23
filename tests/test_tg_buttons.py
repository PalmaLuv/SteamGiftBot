"""Buttons under a win card in Telegram: 'Активировать в ASF' and 'Ключ
получен', answered by the farm's own command polling and only in its chat."""
import json

import pytest

from test_farm import FakeOpium, manager  # noqa: F401
from test_farm_extras import answer
from test_indiegala_wins import FakeLibrary, setUp

from steamgiftbot import notify
from steamgiftbot.farm import asf as asfModule
from steamgiftbot.farm import cards
from steamgiftbot.farm.manager import FarmState
from steamgiftbot.farm.telegram import TelegramControl
from steamgiftbot.settings import Settings
from steamgiftbot.wins import Win

TOKEN = '123456789:' + 'A' * 35
CHAT = '555'


class FakeTelegram:
    """Takes every Bot API call and keeps it; getUpdates hands out `updates`."""

    def __init__(self, updates=()):
        self.calls, self.updates = [], list(updates)

    def post(self, url, json=None, timeout=None):
        method = url.rsplit('/', 1)[1]
        self.calls.append((method, json))
        if method == 'getUpdates' and json.get('timeout'):
            updates, self.updates = self.updates, []
            return answer({'ok': True, 'result': updates})
        return answer({'ok': True, 'result': [] if method == 'getUpdates' else True})

    def made(self, method):
        return [params for name, params in self.calls if name == method]


@pytest.fixture
def polling(manager, tmp_path, monkeypatch):  # noqa: F811
    # No ASF.json of this machine decides what the tests see.
    monkeypatch.setattr(asfModule, 'LOCAL_CONFIG', tmp_path / 'no-asf' / 'ASF.json')
    manager.updateFarmSettings({'telegram_token': TOKEN, 'telegram_chat': CHAT,
                                'telegram_commands': True})
    return manager


def addWin(manager, key='steamgifts', name='Hollow Knight', cdkey=None):  # noqa: F811
    moment = manager.platforms[key].recordWin(name, 'https://www.steamgifts.com/giveaway/AbC12/x/')
    if cdkey:
        manager.state.updateWin(key, moment, name, cdkey=cdkey)
    return moment


def press(data, chat=CHAT, markup=None):
    message = {'message_id': 77, 'chat': {'id': int(chat)}}
    if markup is not None:
        message['reply_markup'] = markup
    return {'update_id': 9, 'callback_query': {'id': 'q1', 'data': data, 'message': message}}


# ---- the card ------------------------------------------------------------------

def test_card_puts_the_farms_buttons_on_top_and_keeps_them_without_links():
    card = cards.Card('🎉', headline='Game', buttons=[('Выигрыши', 'http://192.168.1.10/')],
                      actions=[('Ключ получен', 'win:abc:got'), ('too long', 'x' * 65)])
    assert card.keyboard() == {'inline_keyboard': [
        [{'text': 'Ключ получен', 'callback_data': 'win:abc:got'}],
        [{'text': 'Выигрыши', 'url': 'http://192.168.1.10/'}]]}
    assert 'win:abc' not in card.plain()
    bare = card.withoutButtons()
    assert bare.buttons == [] and bare.actions == card.actions
    assert 'Выигрыши: http://192.168.1.10/' in bare.plain()


def test_refused_link_keeps_the_farms_buttons():
    class Refusing:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, timeout=None):
            self.calls.append(json)
            bad = any('url' in button for row in (json.get('reply_markup') or {})
                      .get('inline_keyboard', []) for button in row)
            return answer({'ok': not bad, 'description': 'Bad Request: wrong HTTP URL'},
                          400 if bad else 200)
    session = Refusing()
    card = cards.Card('🎉', headline='Game', buttons=[('Выигрыши', 'http://192.168.1.10/')],
                      actions=[('Ключ получен', 'win:abc:got')])
    config = Settings(telegram_token=TOKEN, telegram_chat=CHAT)
    assert notify.send(config, card.plain(), session=session, card=card) == []
    assert session.calls[1]['reply_markup'] == {'inline_keyboard': [
        [{'text': 'Ключ получен', 'callback_data': 'win:abc:got'}]]}


def test_translated_card_keeps_its_buttons(polling):
    polling.updateUi({'lang': 'en'})
    card = polling.translateCard(cards.Card('🎉', actions=[('Ключ получен', 'win:abc:got')]))
    assert card.actions == [('Key received', 'win:abc:got')]


# ---- which buttons a win gets ------------------------------------------------------

def test_no_buttons_without_command_polling(manager):  # noqa: F811
    moment = addWin(manager)
    assert manager.winActions('steamgifts', moment, 'Hollow Knight') == []
    manager.updateFarmSettings({'telegram_token': TOKEN, 'telegram_chat': CHAT})
    assert manager.winActions('steamgifts', moment, 'Hollow Knight') == []


def test_received_only_without_a_steam_key_or_asf(polling):
    moment = addWin(polling)
    actions = polling.winActions('steamgifts', moment, 'Hollow Knight')
    assert [text for text, _data in actions] == ['Ключ получен']
    moment = addWin(polling, name='Celeste', cdkey='AAAAA-BBBBB-CCCCC')
    # A Steam key, but no sign of ASF.
    assert [text for text, _ in polling.winActions('steamgifts', moment, 'Celeste')] == \
        ['Ключ получен']


def test_asf_button_for_a_steam_key_when_asf_is_set_up(polling):
    polling.updateFarmSettings({'asf_password': 'ipc'})
    moment = addWin(polling, name='Celeste', cdkey='AAAAA-BBBBB-CCCCC')
    actions = polling.winActions('steamgifts', moment, 'Celeste')
    assert [text for text, _ in actions] == ['Активировать в ASF', 'Ключ получен']
    # Short, and naming the win only by a token: no name, no key.
    for _text, data in actions:
        assert len(data.encode()) <= 64 and 'AAAAA' not in data and 'Celeste' not in data
    # The same token every time, and kept in the state file.
    token = actions[0][1].split(':')[1]
    assert polling.winActions('steamgifts', moment, 'Celeste')[0][1] == f'win:{token}:asf'
    again = FarmState(polling.state.path)
    assert again.winByToken(token)[1]['name'] == 'Celeste'
    # A gift link is not for ASF; nor a key the farm sends on its own.
    link = addWin(polling, name='Gift', cdkey='https://www.indiegala.com/gift?gift_id=abc')
    assert len(polling.winActions('steamgifts', link, 'Gift')) == 1
    polling.updateFarmSettings({'auto_redeem': True})
    assert len(polling.winActions('steamgifts', moment, 'Celeste')) == 1


def test_asf_counts_as_set_up_from_its_own_config_file(polling, tmp_path, monkeypatch):
    assert not polling.asfConfigured()
    found = tmp_path / 'ASF.json'
    found.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(asfModule, 'LOCAL_CONFIG', found)
    assert polling.asfConfigured()


# ---- the win cards ---------------------------------------------------------------

def test_steamgifts_win_card_carries_the_buttons_and_is_recorded_once(polling):
    from steamgiftbot.farm.steamgifts import FarmSteamGift
    sent = []
    polling.notify = lambda text=None, card=None: sent.append(card) or []
    platform = polling.platforms['steamgifts']
    bot = object.__new__(FarmSteamGift)
    bot.platform = platform
    bot.provider = type('Provider', (), {'wonPage': None})()
    win = Win('8caCY', 'Patrician Iii')
    bot.announceWins = lambda: bot.tellWin(win) or [win]
    platform.announce(bot)
    assert [w['name'] for w in polling.state.site('steamgifts')['wins']] == ['Patrician Iii']
    assert [text for text, _ in sent[0].actions] == ['Ключ получен']
    assert sent[0].keyboard()['inline_keyboard'][0][0]['callback_data'].startswith('win:')


def test_indiegala_win_card_offers_asf_for_its_steam_key(polling):
    polling.updateFarmSettings({'asf_password': 'ipc'})
    site = FakeLibrary()
    platform, conf, sent = setUp(polling, site)
    platform.checkWins()
    from conftest import fixture
    site.won = fixture('indiegala_won.html')
    platform.checkWins()
    actions = [[text for text, _ in card['actions']] for _icon, _text, card in sent]
    # The first has a Steam key, the second only a gift link.
    assert actions == [['Активировать в ASF', 'Ключ получен'], ['Ключ получен']]


def test_opiumpulses_win_card_offers_received(polling):
    from steamgiftbot.farm.opiumpulses import WON_KEYS
    platform = polling.platforms['opiumpulses']
    sent = []
    platform.notify = lambda text='', icon='', **card: sent.append(card)
    for names in (('Old Game',), ('Old Game', 'Cool Game')):
        rows = ''.join(f'<tr><td>{name}</td><td><a href="/user/key/{n}">show</a></td></tr>'
                       for n, name in enumerate(names))
        platform.session = FakeOpium({WON_KEYS: (200, f'<table><tbody>{rows}</tbody></table>')})
        platform.checkWins()
    assert [text for text, _ in sent[0]['actions']] == ['Ключ получен']


# ---- pressing them ---------------------------------------------------------------

def tokenOf(manager, moment, name='Hollow Knight', key='steamgifts'):  # noqa: F811
    return manager.state.winToken(key, moment, name)


def test_received_marks_the_win_and_takes_its_button_away(polling):
    moment = addWin(polling)
    token = tokenOf(polling, moment)
    told = []
    platform = polling.platforms['steamgifts']
    platform.onWinStatus = lambda win, status: told.append((win['name'], status))
    session = FakeTelegram()
    control = TelegramControl(polling, session=session)
    markup = {'inline_keyboard': [
        [{'text': 'Активировать в ASF', 'callback_data': f'win:{token}:asf'},
         {'text': 'Ключ получен', 'callback_data': f'win:{token}:got'}],
        [{'text': 'Выигрыши', 'url': 'http://100.64.0.5:8092/#/wins'}]]}
    assert control.process(TOKEN, CHAT, press(f'win:{token}:got', markup=markup)) == 'received'
    assert polling.state.findWin('steamgifts', moment, 'Hollow Knight')['status'] == 'received'
    assert told == [('Hollow Knight', 'received')]
    assert session.made('answerCallbackQuery') == [{'callback_query_id': 'q1',
                                                    'text': 'Отмечено: ключ получен.'}]
    edited = session.made('editMessageReplyMarkup')[0]
    assert edited['message_id'] == 77 and edited['reply_markup'] == {'inline_keyboard': [
        [{'text': 'Активировать в ASF', 'callback_data': f'win:{token}:asf'}],
        [{'text': 'Выигрыши', 'url': 'http://100.64.0.5:8092/#/wins'}]]}
    # A second press changes nothing and is still answered.
    assert control.process(TOKEN, CHAT, press(f'win:{token}:got')) == 'already'
    assert len(session.made('answerCallbackQuery')) == 2 and len(told) == 1


def test_only_the_farms_chat_may_press(polling):
    moment = addWin(polling)
    token = tokenOf(polling, moment)
    session = FakeTelegram()
    control = TelegramControl(polling, session=session)
    assert control.process(TOKEN, CHAT, press(f'win:{token}:got', chat='777')) is None
    assert polling.state.findWin('steamgifts', moment, 'Hollow Knight')['status'] == ''
    # Answered all the same, with nothing in it.
    assert session.made('answerCallbackQuery') == [{'callback_query_id': 'q1'}]
    assert session.made('sendMessage') == []


@pytest.mark.parametrize('data', ['win:gone1234:got', 'win:x', 'other', '', 'win:abc:delete'])
def test_old_or_unknown_buttons_are_answered_harmlessly(polling, data):
    moment = addWin(polling)
    tokenOf(polling, moment)
    session = FakeTelegram()
    control = TelegramControl(polling, session=session)
    assert control.process(TOKEN, CHAT, press(data)) == 'stale'
    assert 'устарела' in session.made('answerCallbackQuery')[0]['text']
    assert polling.state.findWin('steamgifts', moment, 'Hollow Knight')['status'] == ''


def test_buttons_still_work_after_a_restart(polling):
    moment = addWin(polling)
    token = tokenOf(polling, moment)
    polling.state = FarmState(polling.state.path)
    control = TelegramControl(polling, session=FakeTelegram())
    assert control.process(TOKEN, CHAT, press(f'win:{token}:got')) == 'received'


def test_activate_sends_the_key_to_asf(polling, monkeypatch):
    moment = addWin(polling, cdkey='AAAAA-BBBBB-CCCCC')
    token = tokenOf(polling, moment)
    sent = []

    def redeem(key, when, name, auto=False):
        sent.append((key, name))
        polling.state.updateWin(key, when, name, status='activated')
        return 'ok', 'активирован'
    monkeypatch.setattr(polling, 'redeemWin', redeem)
    session = FakeTelegram()
    control = TelegramControl(polling, session=session)
    markup = {'inline_keyboard': [
        [{'text': 'Активировать в ASF', 'callback_data': f'win:{token}:asf'},
         {'text': 'Ключ получен', 'callback_data': f'win:{token}:got'}]]}
    assert control.process(TOKEN, CHAT, press(f'win:{token}:asf', markup=markup)) == 'ok'
    assert sent == [('steamgifts', 'Hollow Knight')]
    # Answered before ASF is asked, which may take a while.
    assert [name for name, _ in session.calls][0] == 'answerCallbackQuery'
    assert session.made('editMessageReplyMarkup')[0]['reply_markup'] == {'inline_keyboard': []}
    # Once activated, either button only says so.
    assert control.process(TOKEN, CHAT, press(f'win:{token}:got')) == 'already'
    assert len(sent) == 1


def test_activate_failure_comes_back_as_a_card(polling):
    moment = addWin(polling)              # no key at all
    token = tokenOf(polling, moment)
    session = FakeTelegram()
    control = TelegramControl(polling, session=session)
    assert control.process(TOKEN, CHAT, press(f'win:{token}:asf')) == 'error'
    text = session.made('sendMessage')[0]['text']
    assert 'КЛЮЧ НЕ ОТПРАВЛЕН' in text and 'нет ключа' in text
    assert session.made('editMessageReplyMarkup') == []


def test_polling_asks_for_button_presses_too(polling):
    moment = addWin(polling)
    token = tokenOf(polling, moment)
    session = FakeTelegram(updates=[press(f'win:{token}:got')])
    control = TelegramControl(polling, session=session)
    assert control.pollOnce()
    asked = [params for params in session.made('getUpdates') if params.get('timeout')][0]
    assert 'callback_query' in asked['allowed_updates']
    assert polling.state.findWin('steamgifts', moment, 'Hollow Knight')['status'] == 'received'
    assert json.dumps(session.calls, ensure_ascii=False).count('Hollow Knight') == 0
