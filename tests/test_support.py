"""Asking to support the project: rarely, only under a win, and never once
the user has turned it off."""
from test_farm import manager  # noqa: F401

from steamgiftbot import notify
from steamgiftbot.farm import cards, support
from steamgiftbot.farm.telegram import TelegramControl


def test_due_once_a_week_and_only_when_on():
    now = 10 * support.ASK_EVERY
    assert support.due(True, None, now)
    assert support.due(True, now - support.ASK_EVERY, now)
    assert not support.due(True, now - support.ASK_EVERY + 60, now)
    assert not support.due(False, None, now)


def capture(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, 'isConfigured', lambda config: True)
    monkeypatch.setattr(notify, 'send', lambda config, text, card=None: sent.append(card) or [])
    return sent


def win():
    return cards.Card('🎉', site='IndieGala', key='indiegala', headline='Hollow Pact')


def test_a_win_carries_the_line_once_a_week(manager, monkeypatch):  # noqa: F811
    sent = capture(monkeypatch)
    manager.notify(card=win())
    manager.notify(card=win())
    manager.notify(card=cards.Card('🔑', headline='cookie expired'))
    first, second, other = sent
    assert first.note and any(url == support.PAGE['ru'] for _text, url in first.buttons)
    assert not second.note and not second.buttons
    assert not other.note
    assert manager.farm['supportAsked'] > 0


def test_no_line_when_turned_off(manager, monkeypatch):  # noqa: F811
    sent = capture(monkeypatch)
    manager.updateUi({'support': False})
    manager.notify(card=win())
    assert not sent[0].note and 'supportAsked' not in manager.farm


def test_a_failed_message_does_not_count_as_asked(manager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(notify, 'isConfigured', lambda config: True)
    monkeypatch.setattr(notify, 'send', lambda config, text, card=None: ['down'])
    manager.notify(card=win())
    assert 'supportAsked' not in manager.farm


def test_donate_command_and_settings_info(manager):  # noqa: F811
    control = TelegramControl(manager)
    text = control.handle('/donate')
    assert support.TON in text and 'GitHub Sponsors' in text
    assert '/donate' in control.handle('/help')
    info = manager.settingsInfo()['support']
    assert info['ton'] == support.TON and info['page'] == support.PAGE['ru']
    manager.updateUi({'lang': 'en'})
    assert manager.settingsInfo()['support']['page'] == support.PAGE['en']
