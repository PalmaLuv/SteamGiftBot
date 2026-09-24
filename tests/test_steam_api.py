import json

import pytest
import requests

from conftest import FakeResponse

from steamgiftbot import steam_api

APPID = 1172620


class FakeStore:
    """Stands in for the shared session; counts what it was asked."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs.get('params'))
        return self.respond()


def serve(monkeypatch, respond):
    store = FakeStore(respond)
    monkeypatch.setattr(steam_api, '_http', store)
    return store


def answer(monkeypatch, payload=None, status_code=200, raises=None, text=None):
    def respond():
        if raises is not None:
            raise raises
        body = text if text is not None else json.dumps(payload)
        return FakeResponse(body, status_code=status_code)

    return serve(monkeypatch, respond)


def storePayload(categories, success=True):
    return {str(APPID): {'success': success, 'data': {'categories': categories}}}


def test_the_store_is_asked_only_once_per_game(monkeypatch):
    store = answer(monkeypatch, storePayload([{'id': 29}]))

    assert steam_api.get_game_info(APPID) is True
    assert steam_api.get_game_info(APPID) is True
    assert len(store.calls) == 1


def test_a_real_no_is_cached(monkeypatch):
    store = answer(monkeypatch, storePayload([{'id': 2}]))

    assert steam_api.get_game_info(APPID) is False
    assert steam_api.get_game_info(APPID) is False
    assert len(store.calls) == 1


def test_a_network_failure_is_not_cached(monkeypatch):
    # A blip must not mark a game with cards as 'no cards' for the whole run.
    outcomes = [requests.RequestException("store is down"),
                FakeResponse(json.dumps(storePayload([{'id': 29}])))]

    def respond():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    store = serve(monkeypatch, respond)

    assert steam_api.get_game_info(APPID) is None
    assert steam_api.get_game_info(APPID) is True
    assert len(store.calls) == 2


def test_reports_a_game_with_trading_cards(monkeypatch):
    answer(monkeypatch, storePayload([{'id': 29, 'description': 'Steam Trading Cards'}]))
    assert steam_api.get_game_info(APPID) is True


def test_reports_a_game_without_trading_cards(monkeypatch):
    answer(monkeypatch, storePayload([{'id': 2, 'description': 'Single-player'}]))
    assert steam_api.get_game_info(APPID) is False


def test_handles_a_game_with_no_categories_at_all(monkeypatch):
    answer(monkeypatch, {str(APPID): {'success': True, 'data': {}}})
    assert steam_api.get_game_info(APPID) is False


def test_handles_an_unknown_appid(monkeypatch):
    # Steam answers success=false for delisted or region locked apps.
    answer(monkeypatch, {str(APPID): {'success': False}})
    assert steam_api.get_game_info(APPID) is False


@pytest.mark.parametrize('kwargs', [
    {'status_code': 503, 'payload': {}},
    {'text': '<html>maintenance</html>'},
    {'raises': requests.RequestException('connection reset')},
])
def test_a_broken_answer_is_unknown_and_logged(monkeypatch, capsys, kwargs):
    answer(monkeypatch, **kwargs)
    assert steam_api.get_game_info(APPID) is None
    assert str(APPID) in capsys.readouterr().out


def test_the_session_is_shared_and_retries(monkeypatch):
    monkeypatch.setattr(steam_api, '_http', None)
    first = steam_api.session()
    assert steam_api.session() is first
    assert first.get_adapter(steam_api.STORE_API).max_retries.total == 3
