"""IndieGala's 'smart' order counts the people still to come, and a game
gets only so many tickets: one key is enough."""
import time

from test_farm import FakeIndieGala, indiegala, manager  # noqa: F401

from steamgiftbot.farm import indiegala as ig


def ticket(ident, entries, minutesLeft, price=1, name=None):
    return ig.Ticket(id=ident, token='t', name=name or f'Game {ident}', price=price,
                     entries=entries, extraOdds=False, url='https://x/', minutesLeft=minutesLeft)


def test_the_forecast_waits_for_a_pace_then_uses_it(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    now = 1_800_000_000.0
    first = [ticket('a', 10, 600), ticket('b', 10, 600)]
    platform.forecast(first, now)
    assert [t.expected for t in first] == [None, None]      # nothing watched yet
    later = [ticket('a', 40, 570), ticket('b', 10, 570), ticket('c', 5, 100)]
    platform.forecast(later, now + 30 * 60)
    a, b, c = later
    assert a.expected == 40 + 1.0 * 570                     # 30 people in 30 min
    assert b.expected == 10                                 # nobody came
    assert c.expected == 5 + 0.5 * 100                      # new: the median pace


def test_smart_prefers_the_giveaway_that_stays_small(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    now = 1_800_000_000.0
    platform.forecast([ticket('busy', 5, 3000), ticket('quiet', 20, 40)], now)
    busy, quiet = ticket('busy', 15, 2970), ticket('quiet', 21, 10)
    platform.forecast([busy, quiet], now + 30 * 60)
    # By the entrants now 'busy' looks better; by the end it is far worse.
    assert busy.entries < quiet.entries
    assert sorted([busy, quiet], key=lambda t: -t.value) == [quiet, busy]


def test_old_sightings_are_forgotten(manager):  # noqa: F811
    platform = manager.platforms['indiegala']
    now = 1_800_000_000.0
    platform.forecast([ticket('a', 10, 600)], now)
    platform.forecast([ticket('b', 10, 600)], now + ig.PACE_KEPT + 1)
    assert set(platform.sightings) == {'b'}


def test_a_game_gets_only_so_many_tickets(manager):  # noqa: F811
    platform, conf = indiegala(manager, FakeIndieGala(), max_per_game=2)
    now = time.time()
    state = manager.state
    for moment in (now - 3600, now - 2 * 86400, now - 8 * 86400):
        state.addEntry('indiegala', {'time': moment, 'name': 'Puzzle Chambers™', 'cost': 1})
    platform.countTickets()
    puzzle = ticket('p', 3, 60, name='Puzzle Chambers')
    assert platform.skipReason(conf, puzzle, set()) == 'хватит билетов на эту игру'
    other = ticket('o', 3, 60, name='Other Game')
    assert platform.skipReason(conf, other, set()) is None
    platform.boughtFor(other)
    assert platform.skipReason(conf, other, set()) is None
    platform.boughtFor(other)
    assert platform.skipReason(conf, other, set()) == 'хватит билетов на эту игру'
    # Priority games are wanted as much as can be had.
    conf['priority'] = ['puzzle']
    assert platform.skipReason(conf, puzzle, set()) is None
    # Empty means no limit.
    conf['priority'], conf['max_per_game'] = [], None
    assert platform.skipReason(conf, puzzle, set()) is None


def test_a_pass_counts_its_own_tickets(manager):  # noqa: F811
    site = FakeIndieGala(silver=100)
    platform, conf = indiegala(manager, site, max_per_game=1)
    platform.cycle(conf)
    assert len(site.joined) == 3                            # three different games
    assert platform.ticketsFor(ticket('n', 1, 1, name='Grav Blazer Squared')) == 1
