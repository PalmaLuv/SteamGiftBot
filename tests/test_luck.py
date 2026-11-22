"""Luck against expectation: the wins the entries should have brought, from
the people seen at entry and the copies, against the wins that came, plus
the site's currency per win. In the summary, the panel and the daily report."""
import re
import time

import pytest

from test_farm import call, manager, panel  # noqa: F401
from test_panel_page import function

from steamgiftbot.farm.manager import entryChance, luckOf
from steamgiftbot.giveaway import Giveaway


def entry(moment, cost, **extra):
    return {'time': moment, 'name': 'G', 'cost': cost, 'url': '', **extra}


# ---- the math -----------------------------------------------------------------------

def test_one_entry_shares_its_copies_with_the_people_in():
    assert entryChance(entry(1, 5, entries=9)) == (pytest.approx(0.1), False)
    assert entryChance(entry(1, 5, entries=9, copies=3)) == (pytest.approx(0.3), False)
    # More copies than people: a sure win, not more than one.
    assert entryChance(entry(1, 5, entries=1, copies=5)) == (1.0, False)
    assert entryChance(entry(1, 5, entries=0)) == (1.0, False)
    # IndieGala's forecast for the end wins over the people seen at entry.
    assert entryChance(entry(1, 5, entries=9, expected=19)) == (pytest.approx(0.05), True)


def test_an_entry_without_a_count_is_unknown():
    assert entryChance(entry(1, 5)) is None
    assert entryChance(entry(1, 5, entries=None)) is None
    assert entryChance(entry(1, 5, entries='да')) is None
    assert entryChance(entry(1, 5, entries=True)) is None


def test_luck_over_the_kept_history():
    entries = [entry(100, 10, entries=9), entry(200, 20, entries=3, copies=2),
               entry(300, 30), entry(400, 0, entries=99, expected=199)]
    wins = [{'time': 50, 'name': 'Before'}, {'time': 250, 'name': 'A'},
            {'time': 500, 'name': 'B'}, {'time': 600, 'name': 'Imported', 'cli': True}]
    luck = luckOf(entries, wins)
    assert luck['entries'] == 4 and luck['known'] == 3 and luck['unknown'] == 1
    assert luck['forecast'] == 1
    assert luck['expected'] == pytest.approx(0.1 + 0.5 + 0.005, abs=0.01)
    # A win from before the oldest kept entry and the command line bot's
    # imported one are not the kept entries' doing.
    assert luck['wins'] == 2
    assert luck['spent'] == 60 and luck['perWin'] == 30 and luck['avgCost'] == 15
    assert luck['since'] == 100


def test_luck_with_no_wins_or_no_entries():
    luck = luckOf([entry(1, 7, entries=1)], [])
    assert luck['wins'] == 0 and luck['perWin'] is None and luck['expected'] == 0.5
    assert luckOf([], [{'time': 1, 'name': 'x'}]) is None


# ---- what the sites keep at entry ---------------------------------------------------

def test_steamgifts_keeps_people_and_copies(manager):  # noqa: F811
    platform = manager.platforms['steamgifts']
    for code, copies in (('aaa', 3), ('bbb', 1)):
        platform.pendingCost[code] = 10
        platform.lastGiveaways[code] = Giveaway(code, code, 10, entries=59, copies=copies)
        platform.enteredByName(code)
    first, second = manager.state.site('steamgifts')['entries']
    assert first['entries'] == 59 and first['copies'] == 3
    # One copy is the usual and goes unwritten; it is still one.
    assert second['entries'] == 59 and 'copies' not in second
    assert manager.summary(7)['sites'][0]['luck']['expected'] == pytest.approx(0.05 + 1 / 60,
                                                                               abs=0.01)


def test_old_entries_still_count_as_unknown(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    platform.recordEntry('Old', 4)
    platform.recordEntry('New', 6, entries=3, expected=7)
    platform.recordWin('New')
    sites = {site['key']: site for site in manager.summary(7)['sites']}
    luck = sites['indiegala']['luck']
    assert (luck['entries'], luck['known'], luck['unknown'], luck['forecast']) == (2, 1, 1, 1)
    assert luck['expected'] == pytest.approx(0.12, abs=0.01)
    assert luck['wins'] == 1 and luck['perWin'] == 10 and luck['avgCost'] == 5
    # Free sites draw nothing; a giveaway site with no entries has no luck yet.
    assert sites['gog']['luck'] is None and sites['opiumpulses']['luck'] is None


# ---- the panel and the report -------------------------------------------------------

def test_summary_api_carries_luck(panel, manager):  # noqa: F811
    manager.platforms['indiegala'].recordEntry('A', 2, entries=1)
    _, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    status, summary, _ = call(panel + '/api/summary?days=7', cookie=cookie)
    sites = {site['key']: site for site in summary['sites']}
    assert status == 200
    assert sites['indiegala']['luck']['expected'] == 0.5
    assert sites['indiegala']['luck']['avgCost'] == 2
    assert sites['steamfree']['luck'] is None


def test_daily_report_has_a_luck_line_per_site(manager):  # noqa: F811
    manager.platforms['indiegala'].recordEntry('A', 4, entries=1)
    manager.platforms['indiegala'].recordEntry('B', 6)
    manager.platforms['indiegala'].recordWin('A')
    manager.platforms['opiumpulses'].recordEntry('C', 5)
    report = manager.report(now=time.time())
    assert ('🍀 IG за историю: выигрышей 1, ожидалось ≈0.5 (известно для 1 из 2 входов) · '
            '10 iS за выигрыш · вход в среднем 5 iS') in report
    assert '🍀 OP за историю: выигрышей 0, ожидание неизвестно · вход в среднем 5 OP' in report
    assert '🍀 SG' not in report and '🍀 GOG' not in report


def test_overview_shows_luck_next_to_the_tiles():
    summary = function('renderSummary')
    assert '.join(\'\') + luckTile(S);' in summary
    tile = function('luckTile')
    assert 'S.filter(s => s.luck)' in tile
    assert 'известно для ${k.known} из ${k.entries} входов' in tile
    assert re.search(r'Участники прибывают и после входа фермы.*ожидание завышено', tile)
    assert 'прогноз участников к концу раздачи' in tile
