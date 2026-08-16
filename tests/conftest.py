"""Shared test helpers: fixture HTML and a stand-in for requests.Session."""
import json
import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class FakeResponse:
    def __init__(self, text, status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = {} if headers is None else headers

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Serves the fixture pages and remembers which giveaways were entered."""

    def __init__(self, home=None, pages=None, entryResponse=None, won=None):
        self.home    = fixture('home.html') if home is None else home
        self.pages   = {1: fixture('giveaways.html')} if pages is None else pages
        # An empty won page by default, so ordinary tests announce nothing.
        self.won     = '<html><body><div class="table"></div></body></html>' if won is None else won
        self.entryResponse = entryResponse
        self.entered   = []
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        if url.endswith('/giveaways/won'):
            return FakeResponse(self.won)
        if '/giveaways/' not in url:
            return FakeResponse(self.home)
        page = int(url.split('page=')[1].split('&')[0])
        return FakeResponse(self.pages.get(page, fixture('giveaways_empty.html')))

    def post(self, url, data=None, **kwargs):
        self.entered.append(data['code'])
        if self.entryResponse is not None:
            return self.entryResponse
        return FakeResponse(json.dumps({'type': 'success', 'points': '1000'}))


def makeSettings(**overrides):
    from steamgiftbot.settings import Settings

    options = {'cookie': 'cookievalue', 'gift_type': 'All', 'pinned': False,
               'min_points': 0, 'once': False}
    options.update(overrides)
    return Settings(**options)


@pytest.fixture
def makeBot(monkeypatch):
    from steamgiftbot import bot as botModule

    # Real runs pace themselves between entries; tests should not.
    monkeypatch.setattr(botModule, 'sleep', lambda *args, **kwargs: None)
    monkeypatch.setattr(botModule, 'POINTS_WAIT', 1)

    def factory(session=None, statePath=None, **overrides):
        instance = botModule.SteamGift(makeSettings(**overrides), statePath=statePath)
        instance.session = FakeSession() if session is None else session
        return instance

    return factory


@pytest.fixture(autouse=True)
def emptySteamCache():
    # The store answers are memoised for the life of the process; one test must
    # not decide what the next one sees.
    from steamgiftbot import steam_api
    steam_api.clearCache()
    yield
    steam_api.clearCache()


@pytest.fixture
def configPath(tmp_path):
    return tmp_path / 'config.ini'


@pytest.fixture(autouse=True)
def cleanEnvironment(monkeypatch):
    from steamgiftbot.settings import ENV_PREFIX
    import os

    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
