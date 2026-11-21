"""The idle watchdog: a giveaway site that keeps making passes and enters
nothing for a day is told once in Telegram; an entry starts the count again."""
import time

from test_farm import manager  # noqa: F401

from steamgiftbot.farm import base


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def passes(platform, clock, count, every=3600, enter=False):
    for _ in range(count):
        platform.passStartedAt = clock.now
        clock.now += 30
        if enter:
            platform.recordEntry('Game', 1)
        clock.now += 1
        platform.finishPass("Проход окончен")
        clock.now += every


def watched(manager, monkeypatch, key='indiegala'):  # noqa: F811
    clock = Clock()
    monkeypatch.setattr(time, 'time', clock)
    platform = manager.platforms[key]
    manager.panelLink = lambda route='': 'http://panel/#' + route
    cards = []
    platform.notify = lambda text='', icon='', **card: cards.append((icon, text, card))
    return platform, clock, cards


def test_a_day_without_entries_is_told_once(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch)
    platform.balance = 0
    platform.waitReason = 'Закончился iS (0), ждёт пополнения'
    passes(platform, clock, 24)
    assert cards == []                      # 23 h 30 min so far
    passes(platform, clock, 1)
    assert len(cards) == 1
    icon, text, card = cards[0]
    assert icon == '⚠️' and card['title'] == 'СТОИТ БЕЗ ВХОДОВ'
    assert 'Закончился iS' in text and 'Баланс: 0 iS' in text
    assert card['headline'].startswith('Ни одного входа за 24 ч')
    assert card['buttons'][0][1].endswith('#/site/indiegala/preview')
    passes(platform, clock, 30)
    assert len(cards) == 1


def test_an_entry_starts_the_count_again(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch)
    passes(platform, clock, 20)
    passes(platform, clock, 1, enter=True)
    passes(platform, clock, 20)
    assert cards == []
    passes(platform, clock, 10)
    assert len(cards) == 1
    # Entering again re-arms it for the next stretch.
    passes(platform, clock, 1, enter=True)
    passes(platform, clock, 26)
    assert len(cards) == 2


def test_a_few_long_waits_are_not_a_stall(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch)
    passes(platform, clock, base.IDLE_PASSES - 1, every=10 * 3600)
    assert cards == []


def test_free_sources_are_not_watched(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch, 'gog')
    passes(platform, clock, 40)
    assert cards == []


def test_the_opiumpulses_filter_warning_is_enough(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch, 'opiumpulses')
    platform.filteredNow = True
    passes(platform, clock, 40)
    assert cards == []
    platform.filteredNow = False
    passes(platform, clock, 1)
    assert len(cards) == 1


def test_the_count_survives_a_restart(manager, monkeypatch):  # noqa: F811
    platform, clock, cards = watched(manager, monkeypatch)
    passes(platform, clock, 20)
    assert manager.state.value('indiegala', 'idle')['passes'] == 20
    passes(platform, clock, 6)
    assert len(cards) == 1
