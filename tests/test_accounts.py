"""Several accounts of one site: each is its own card with its own key,
settings, history and log; a second Steam account is a second ASF bot."""
import logging

import pytest

from bs4 import BeautifulSoup
from test_farm import call, manager, panel  # noqa: F401
from test_farm_extras import FakeASF

from steamgiftbot import settings as sgSettings
from steamgiftbot.bot import SteamGift
from steamgiftbot.farm.base import actingFor
from steamgiftbot.farm.indiegala import IndieGalaPlatform
from steamgiftbot.farm.manager import FarmManager
from steamgiftbot.logging_setup import LOGGER_NAME


@pytest.fixture
def accounts(monkeypatch):
    """IndieGala's check answers with the account named in the cookie."""
    def check(self, values):
        cookie = values.get('cookie') or ''
        if not cookie.startswith('user='):
            raise ValueError("сайт не узнал cookie")
        return {'account': cookie[5:], 'balance': 3}
    monkeypatch.setattr(IndieGalaPlatform, 'check', check)


def test_second_account_gets_its_own_card(manager, accounts):  # noqa: F811
    main = manager.platforms['indiegala']
    manager.rememberAccount(main, manager.checkAccount(main, {'cookie': 'user=ann'}))
    assert main.title == 'IndieGala'

    second, found = manager.addAccount('indiegala', {'cookie': 'user=bob'})
    assert second.key == 'indiegala-2' and found['account'] == 'bob'
    assert not second.primary and second.kind == 'indiegala'
    assert second.settings()['cookie'] == 'user=bob' and second.configured()
    assert main.title == 'IndieGala · ann' and second.title == 'IndieGala · bob'
    # The same site's accounts stay next to each other.
    keys = list(manager.platforms)
    assert keys.index('indiegala-2') == keys.index('indiegala') + 1
    snap = second.snapshot()
    assert snap['kind'] == 'indiegala' and snap['baseTitle'] == 'IndieGala' and not snap['primary']

    assert manager.renameAccount('indiegala-2', '  Брат  ') == 'IndieGala · Брат'


def test_the_same_account_twice_is_refused(manager, accounts):  # noqa: F811
    manager.addAccount('indiegala', {'cookie': 'user=bob'})
    with pytest.raises(ValueError, match='уже подключена'):
        manager.addAccount('indiegala', {'cookie': 'user=BOB'})
    with pytest.raises(ValueError):
        manager.addAccount('indiegala', {'cookie': 'broken'})
    assert [key for key in manager.platforms if key.startswith('indiegala')] == [
        'indiegala', 'indiegala-2']
    assert len(manager.farm['accounts']) == 1
    with pytest.raises(ValueError, match='одна карточка'):
        manager.addAccount('steamfree', {})
    with pytest.raises(ValueError):
        manager.addAccount('nosuch', {})


def test_accounts_survive_a_restart_and_removal(manager, accounts, tmp_path):  # noqa: F811
    manager.addAccount('indiegala', {'cookie': 'user=bob'})
    again = FarmManager(dataDir=tmp_path, configPath=tmp_path / 'config.ini')
    second = again.platforms['indiegala-2']
    assert second.settings()['cookie'] == 'user=bob' and second.title == 'IndieGala · bob'

    with pytest.raises(ValueError):
        again.removeAccount('indiegala')
    again.removeAccount('indiegala-2')
    assert 'indiegala-2' not in again.platforms and again.farm['accounts'] == []
    assert again.platforms['indiegala'].title == 'IndieGala'
    # A removed number is not handed out again: its history stays its own.
    third, _ = again.addAccount('indiegala', {'cookie': 'user=cid'})
    assert third.key == 'indiegala-3'


def test_steamgifts_accounts_keep_apart(manager, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv('STEAMGIFTBOT_COOKIE', 'fromenv')
    monkeypatch.setattr(SteamGift, 'updateInfo',
                        lambda bot: (setattr(bot, 'points', 50),
                                     setattr(bot, 'username', bot.cookie['PHPSESSID'][:3])))
    second, found = manager.addAccount('steamgifts', {'cookie': 'bobsession'})
    assert found == {'account': 'bob', 'balance': 50}
    path = tmp_path / 'accounts' / 'steamgifts-2' / 'config.ini'
    assert second.configPath == path and path.exists()
    # The environment speaks for the main account only.
    assert sgSettings.load(path).cookie == 'fromenv'
    assert second.loadConfig().cookie == 'bobsession'
    assert sgSettings.load(manager.configPath).cookie == 'fromenv'

    main = manager.platforms['steamgifts']
    second.attachLogger()
    package = logging.getLogger(LOGGER_NAME)
    with actingFor(second):
        package.info('only for bob')
    package.info('from the command line')
    assert any('only for bob' in line['text'] for line in second.logLines(0))
    assert not any('only for bob' in line['text'] for line in main.logLines(0))
    assert any('from the command line' in line['text'] for line in main.logLines(0))
    assert not any('command line' in line['text'] for line in second.logLines(0))

    manager.removeAccount('steamgifts-2')
    assert not path.parent.exists()


def test_steamgifts_reads_the_name_from_the_header():
    bot = SteamGift.__new__(SteamGift)
    html = ('<input name="xsrf_token" value="t"><span class="nav__points">1,204</span>'
            '<a class="nav__avatar-outer-wrap" href="/user/Palma"></a>')
    bot.GetSoupFromPage = lambda url: BeautifulSoup(html, 'html.parser')
    bot.baseURL = 'https://www.steamgifts.com'
    bot.updateInfo()
    assert (bot.points, bot.username) == (1204, 'Palma')


def test_steam_accounts_are_asf_bots(manager):  # noqa: F811
    manager.asf.session = fake = FakeASF()
    manager.asf.addLicenses([10], [], bots=['Main Bot', 'Second'])
    assert fake.calls[-1][1].endswith('/Api/Bot/Main%20Bot%2CSecond/AddLicense')
    manager.asf.addLicenses([10], [])
    assert fake.calls[-1][1].endswith('/Api/Bot/ASF/AddLicense')

    manager.state.addWin('indiegala', {'time': 100, 'name': 'Game', 'url': '', 'cdkey': 'K-1'})
    manager.setKeyBot('indiegala', 'Second')
    assert manager.platforms['indiegala'].snapshot()['keyBot'] == 'Second'
    manager.redeemWin('indiegala', 100, 'Game')
    assert '/Api/Bot/Second/Redeem' in fake.calls[-1][1]


def test_panel_adds_and_removes_accounts(panel, manager, accounts):  # noqa: F811
    status, _, headers = call(panel + '/api/login', {'password': 'secret123'})
    cookie = headers['Set-Cookie'].split(';')[0]
    status, body, _ = call(panel + '/api/accounts/add',
                           {'kind': 'indiegala', 'values': {'cookie': 'user=bob'}}, cookie)
    assert status == 200 and body['key'] == 'indiegala-2' and body['account'] == 'bob'
    status, body, _ = call(panel + '/api/accounts/add',
                           {'kind': 'indiegala', 'values': {'cookie': 'user=bob'}}, cookie)
    assert status == 400 and 'уже подключена' in body['error']
    status, body, _ = call(panel + '/api/platforms/indiegala-2/label', {'label': 'Брат'}, cookie)
    assert body['title'] == 'IndieGala · Брат'
    status, body, _ = call(panel + '/api/platforms/indiegala-2/key-bot', {'bot': 'Second'}, cookie)
    assert manager.keyBotFor('indiegala-2') == 'Second'
    status, body, _ = call(panel + '/api/platforms/indiegala/remove', {}, cookie)
    assert status == 400
    status, body, _ = call(panel + '/api/platforms/indiegala-2/remove', {}, cookie)
    assert status == 200 and 'indiegala-2' not in manager.platforms
