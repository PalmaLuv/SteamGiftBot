import json

import pytest
import requests

from conftest import FakeResponse

from steamgiftbot import steam_api

APPID = 1172620


def answer(monkeypatch, payload=None, status_code=200, raises=None, text=None):
    def fakeGet(url, **kwargs):
        if raises is not None:
            raise raises
        body = text if text is not None else json.dumps(payload)
        return FakeResponse(body, status_code=status_code)

    monkeypatch.setattr(steam_api.requests, 'get', fakeGet)


def storePayload(categories, success=True):
    return {str(APPID): {'success': success, 'data': {'categories': categories}}}


def test_the_store_is_asked_only_once_per_game(monkeypatch):
    calls = []

    def fakeGet(url, **kwargs):
        calls.append(kwargs.get('params'))
        return FakeResponse(json.dumps(storePayload([{'id': 29}])))

    monkeypatch.setattr(steam_api.requests, 'get', fakeGet)

    assert steam_api.get_game_info(APPID) is True
    assert steam_api.get_game_info(APPID) is True
    assert len(calls) == 1


def test_a_negative_answer_is_cached_as_well(monkeypatch):
    calls = []

    def fakeGet(url, **kwargs):
        calls.append(url)
        raise requests.RequestException("store is down")

    monkeypatch.setattr(steam_api.requests, 'get', fakeGet)

    assert steam_api.get_game_info(APPID) is False
    assert steam_api.get_game_info(APPID) is False
    assert len(calls) == 1


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
def test_a_broken_answer_never_raises(monkeypatch, kwargs):
    answer(monkeypatch, **kwargs)
    assert steam_api.get_game_info(APPID) is False
