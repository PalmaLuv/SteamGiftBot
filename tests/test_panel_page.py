"""The panel page's own behaviour: what it says after a failed start, what
it asks before stopping everything, how it shows a lost connection on a
phone, which links it lets through and what the 'удача' tile counts.

The page is one file with no build step and the tests have no browser, so
most checks read the page's script; the summary flag is checked on the farm."""
import re

from pathlib import Path

from test_farm import manager  # noqa: F401

PAGE = Path(__file__).resolve().parent.parent / 'steamgiftbot' / 'farm' / 'static' / 'index.html'
HTML = PAGE.read_text(encoding='utf-8')
SCRIPT = re.search(r'<script>(.*)</script>', HTML, re.S).group(1)
MARKUP = HTML[:HTML.index('<script>')]


def function(name):
    """The source of a top level function of the page's script."""
    found = re.search(rf'^(?:async )?function {name}\(.*?^}}$', SCRIPT, re.M | re.S)
    assert found, name
    return found.group(0)


# ---- translation ------------------------------------------------------------------

def test_an_attribute_is_translated_once():
    """Ukrainian '30 дн' is '30 дн.', which holds '30 дн' again: the chart's
    aria-label grew a dot on every observer pass and the page froze."""
    node = function('translateNode')
    assert 'const done = TRANSLATED.get(node) || {};' in node
    assert 'v !== done[a]' in node and 'done[a] = t;' in node
    assert 'node.value !== done.value' in node and 'done.value = t;' in node
    assert 'TRANSLATED.set(node, done);' in node


# ---- 1. the connect wizard -------------------------------------------------------

def test_wizard_reports_a_failed_start():
    wizard = function('pageConnect')
    start = wizard.index('/start`')
    # The start's error is kept, not thrown away ...
    assert '.catch(() => null)' not in wizard[start:start + 80]
    assert 'err => err' in wizard[start:start + 80]
    # ... and the toast says so instead of 'запущена'.
    assert 'подключена, но не запустилась: ${startError.message}`, true)' in wizard
    success = wizard.index('подключена и запущена')
    assert 'if (startError)' in wizard[start:success]


# ---- 2. phones and a lost connection ---------------------------------------------

def test_phone_top_bar_has_status_and_sign_out():
    bar = re.search(r'<header class="topbar">(.*?)</header>', MARKUP, re.S)
    assert bar, 'no top bar'
    assert 'data-conn' in bar.group(1) and 'data-act="logout"' in bar.group(1)
    # Hidden on wide screens, where the sidebar shows both; shown on phones.
    assert re.search(r'^\.topbar\{display:none\}', HTML, re.M)
    phone = re.search(r'@media \(max-width:900px\)\{\n  \.shell.*?\n\}', HTML, re.S).group(0)
    assert '.side{display:none}' in phone and '.topbar{display:flex' in phone


def test_lost_connection_shows_a_banner_on_every_size():
    assert re.search(r'<div id="offline" class="offline hidden" role="alert">.*?'
                     r'Нет связи с фермой', MARKUP)
    # The banner is not tied to a screen size: only its padding changes.
    assert re.search(r'^\.offline\{display:flex', HTML, re.M)
    tick = function('tick')
    assert "showConnection(false)" in tick
    show = function('showConnection')
    assert "$('#offline').classList.toggle('hidden', ok)" in show
    assert "$$('[data-conn]')" in show            # the sidebar's clock and the top bar's
    assert 'showConnection(true)' in function('poll')


# ---- 3. stop everything ----------------------------------------------------------

def test_stop_all_asks_first():
    block = SCRIPT[SCRIPT.index("act === 'stop-all'"):]
    block = block[:block.index("api('/api/stop-all'")]
    assert "if (!await confirmDialog('Остановить все площадки?'" in block
    assert ', true)) return;' in block              # a red button, and no on 'Отмена'
    assert 'window.confirm' not in block and 'confirm(' not in block.replace('confirmDialog(', '')


# ---- 4. links from site data -----------------------------------------------------

def test_outside_links_only_come_from_extLink():
    # The only <a target="_blank"> the script builds is extLink's, which
    # passes the address through safeUrl first.
    assert SCRIPT.count('target="_blank"') == 1
    ext = function('extLink')
    assert 'target="_blank"' in ext and 'const href = safeUrl(url);' in ext
    # Every other href built from a value is an in-page '#/…' route or a
    # safeUrl() result.
    for expr in re.findall(r'href="\$\{((?:[^{}]|\{[^{}]*\})*)\}"', SCRIPT):
        assert expr in ('esc(href)', 'href', 'esc(safeUrl(u))') or \
            expr.startswith('p.configured ? `#/'), expr


def test_safeUrl_lets_only_http_through():
    safe = function('safeUrl')
    assert r"if (!/^https?:\/\//i.test(text)) return '';" in safe
    assert "u.protocol === 'http:' || u.protocol === 'https:'" in safe


def test_every_data_link_goes_through_safeUrl():
    for name, expr in (('renderWinsBanner', 'w.url'), ('entriesTable', 'r.url'),
                       ('runPreviewInto', 'i.url'), ('renderWinsTable', 'w.url'),
                       ('detailList', 'v'), ('pageConnect', 'g.link'),
                       ('renderSiteHead', 'p.url'), ('catalogCard', 'p.url')):
        body = function(name)
        assert f'extLink({expr},' in body, (name, expr)
        assert f'href="${{esc({expr})}}"' not in body, (name, expr)


# ---- 5. luck over giveaways only -------------------------------------------------

def test_summary_marks_free_sites(manager):  # noqa: F811
    sites = {site['key']: site for site in manager.summary(7)['sites']}
    assert {key for key, site in sites.items() if site['free']} == {'gog', 'itch', 'steamfree'}
    assert not any(sites[key]['free'] for key in ('steamgifts', 'indiegala', 'opiumpulses'))


def test_luck_leaves_free_claims_out():
    summary = function('renderSummary')
    assert 'const G = S.filter(s => !s.free)' in summary
    assert 'luckText(drawnWins, drawn)' in summary
    assert 'выигрышей на ${drawn} входов в раздачи' in summary
