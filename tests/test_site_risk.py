"""SteamGifts says, before it is connected, that its rules do not allow
bots; the other sites have nothing to warn about."""
from pathlib import Path

from test_farm import manager  # noqa: F401

PAGE = Path(__file__).resolve().parent.parent / 'steamgiftbot' / 'farm' / 'static' / 'index.html'


def test_steamgifts_warns_and_the_others_do_not(manager):  # noqa: F811
    risks = {key: platform.snapshot()['risk'] for key, platform in manager.platforms.items()}
    assert 'не разрешают' in risks['steamgifts'] and 'неактивированные' in risks['steamgifts']
    assert not any(risk for key, risk in risks.items() if key != 'steamgifts')


def test_the_wizard_and_the_connection_tab_show_it():
    page = PAGE.read_text(encoding='utf-8')
    assert page.count('${riskNote(p)}') == 2
