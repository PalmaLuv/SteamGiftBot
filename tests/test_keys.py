"""Won keys: what is kept of a pasted key, each Steam key of a bundle sent to
ASF on its own, and the keys Steam asked to wait with tried again later."""
import json
import threading

import pytest
import requests

from test_farm import manager  # noqa: F401

from steamgiftbot.farm import asf as asfModule
from steamgiftbot.farm import manager as managerModule

LINK = 'https://www.indiegala.com/gift?gift_id=AbC123xYz&gift_code=QwErTy'


def answer(body, status=200):
    response = requests.models.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


class KeyASF:
    """ASF with one bot that answers each key by `plan`: key -> detail code,
    0 for activated, None for no answer at all (the bot went away)."""

    def __init__(self, plan=None, default=0):
        self.plan, self.default, self.sent, self.down = dict(plan or {}), default, [], False

    def request(self, method, url, json=None, headers=None, timeout=None):
        if self.down:
            raise requests.Timeout('timed out')
        if url.endswith('/Api/Bot/ASF'):
            return answer({'Success': True, 'Result': {
                'Main Bot': {'IsConnectedAndLoggedOn': True}}})
        assert url.endswith('/Redeem')
        keys = json['KeysToRedeem']
        self.sent.append(keys)
        result = {}
        for key in keys:
            detail = self.plan.get(key, self.default)
            if detail is None:
                continue
            result[key] = {'purchase_result_details': detail, 'purchase_receipt_info': {
                'purchase_status': 1 if detail == 0 else 2,
                'line_items': [{'line_item_description': f'Game {key[:5]}'}]}}
        return answer({'Success': True, 'Result': {'Main Bot': result}})


@pytest.fixture
def farm(manager):  # noqa: F811
    manager.asf.session = KeyASF()
    manager.told = []
    manager.cards = []

    # Each card in the old one-line form, so the checks read the same.
    def notify(text=None, card=None):
        manager.cards.append(card)
        manager.told.append(text or f"{card.icon} {card.site}: ключ «{card.headline}» — "
                                    f"{card.lines[0]}")
    manager.notify = notify
    manager.platforms['indiegala'].recordWin('Bundle')
    win = manager.openWins()[0]
    manager.win = (win['time'], 'Bundle')
    return manager


def stored(farm):
    return farm.state.findWin('indiegala', *farm.win)


# ---- what is kept of a pasted key ----------------------------------------------

def test_steam_keys_are_capitalised_links_and_other_codes_are_not():
    assert asfModule.normalizeKey(' aaaaa-bbbbb-ccccc ') == 'AAAAA-BBBBB-CCCCC'
    # A gift link opens only as pasted, and a mixed-case code is not Steam's.
    assert asfModule.normalizeKey(LINK) == LINK
    assert asfModule.normalizeKey('Gog: AbCd-EfGh-IjKl') == 'Gog: AbCd-EfGh-IjKl'
    assert asfModule.normalizeKey('x9fq2-bbbbb-ccccc\n\nddddd-eeeee-fffff-ggggg-hhhhh') == \
        'X9FQ2-BBBBB-CCCCC DDDDD-EEEEE-FFFFF-GGGGG-HHHHH'
    assert asfModule.normalizeKey(f'key aaaaa-bbbbb-ccccc or {LINK}') == \
        f'key AAAAA-BBBBB-CCCCC or {LINK}'


def test_a_bundle_is_split_into_its_steam_keys():
    text = 'Game A: aaaaa-11111-ccccc, Game B: DDDDD-EEEEE-FFFFF; again AAAAA-11111-CCCCC'
    assert asfModule.steamKeys(text) == ['AAAAA-11111-CCCCC', 'DDDDD-EEEEE-FFFFF']
    assert asfModule.steamKeys('12345-67890-12345') == ['12345-67890-12345']
    # A key shape inside a link is part of the link, not a key.
    assert asfModule.steamKeys('https://x/redeem/AAAAA-BBBBB-CCCCC') == []
    assert asfModule.steamKeys(LINK) == []
    # Some other code still goes to ASF as one, as pasted.
    assert asfModule.steamKeys('AbCd1234EfGh') == ['AbCd1234EfGh']
    assert asfModule.steamKeys(f'AbCd1234EfGh {LINK}') == ['AbCd1234EfGh']
    assert asfModule.steamKeys('') == []


def test_set_win_key_keeps_a_link_and_does_not_send_it(farm):
    farm.updateFarmSettings({'auto_redeem': True})
    assert farm.setWinKey('indiegala', *farm.win, LINK) == LINK
    assert stored(farm)['cdkey'] == LINK
    assert farm.asf.session.sent == []
    with pytest.raises(ValueError, match='ссылка на подарок'):
        farm.redeemWin('indiegala', *farm.win)


def test_unknown_win_is_still_an_error(farm):
    with pytest.raises(ValueError, match='выигрыш не найден'):
        farm.setWinKey('indiegala', 1, 'Nope', 'AAAAA-BBBBB-CCCCC')


# ---- each key on its own ---------------------------------------------------------

def test_every_key_of_a_bundle_goes_to_asf_alone(farm):
    farm.setWinKey('indiegala', *farm.win, 'aaaaa-bbbbb-ccccc ddddd-eeeee-fffff')
    kind, words = farm.redeemWin('indiegala', *farm.win)
    assert farm.asf.session.sent == [['AAAAA-BBBBB-CCCCC'], ['DDDDD-EEEEE-FFFFF']]
    assert kind == 'ok'
    assert words == '1/2: активирован: Game AAAAA; 2/2: активирован: Game DDDDD'
    win = stored(farm)
    assert win['status'] == 'activated' and win['redeemed'] == ['AAAAA-BBBBB-CCCCC',
                                                                'DDDDD-EEEEE-FFFFF']
    # The message keeps its usual look, and never shows a key.
    assert farm.told == [f"✅ IndieGala: ключ «Bundle» — {words}"]
    assert farm.cards[-1].heading() == 'КЛЮЧ АКТИВИРОВАН'


def test_one_bad_key_leaves_the_win_open(farm):
    farm.asf.session.plan = {'DDDDD-EEEEE-FFFFF': 14}
    farm.setWinKey('indiegala', *farm.win, 'AAAAA-BBBBB-CCCCC DDDDD-EEEEE-FFFFF')
    kind, words = farm.redeemWin('indiegala', *farm.win)
    assert kind == 'fail' and words.endswith('2/2: неверный ключ')
    win = stored(farm)
    assert win['status'] == '' and win['redeemed'] == ['AAAAA-BBBBB-CCCCC']
    assert win.get('redeemRetry') is None
    # A click again sends only the key that did not go through.
    farm.asf.session.plan = {}
    assert farm.redeemWin('indiegala', *farm.win)[0] == 'ok'
    assert farm.asf.session.sent[-1] == ['DDDDD-EEEEE-FFFFF']
    assert stored(farm)['status'] == 'activated'


# ---- trying again later -------------------------------------------------------------

def test_rate_limited_keys_are_tried_again_by_the_clock(farm):
    session = farm.asf.session
    session.plan = {'DDDDD-EEEEE-FFFFF': 53, 'GGGGG-HHHHH-IIIII': 53}
    farm.setWinKey('indiegala', *farm.win,
                   'AAAAA-BBBBB-CCCCC DDDDD-EEEEE-FFFFF GGGGG-HHHHH-IIIII')
    kind, words = farm.redeemWin('indiegala', *farm.win)
    assert kind == 'retry' and 'повторю в' in words
    # After Steam asked to wait the last key is not even sent.
    assert session.sent == [['AAAAA-BBBBB-CCCCC'], ['DDDDD-EEEEE-FFFFF']]
    pending = stored(farm)['redeemRetry']
    assert pending['keys'] == ['DDDDD-EEEEE-FFFFF', 'GGGGG-HHHHH-IIIII']
    assert pending['tries'] == 0
    assert farm.told[-1].startswith('⏳ IndieGala: ключ «Bundle» — ')
    # Not before its time.
    assert farm.redeemTick(now=pending['nextTry'] - 1) == 0
    session.plan = {}
    assert farm.redeemTick(now=pending['nextTry'] + 1) == 1
    assert session.sent[2:] == [['DDDDD-EEEEE-FFFFF'], ['GGGGG-HHHHH-IIIII']]
    win = stored(farm)
    assert win['status'] == 'activated' and win.get('redeemRetry') is None
    assert farm.told[-1].startswith('✅ IndieGala: ключ «Bundle» — ')
    assert farm.redeemTick(now=pending['nextTry'] + 10 ** 6) == 0


def test_asf_away_is_a_retry_not_an_error(farm):
    farm.asf.session.down = True
    farm.setWinKey('indiegala', *farm.win, 'AAAAA-BBBBB-CCCCC')
    kind, words = farm.redeemWin('indiegala', *farm.win)
    assert kind == 'retry' and words.startswith('ASF недоступен')
    assert stored(farm)['redeemRetry']['keys'] == ['AAAAA-BBBBB-CCCCC']
    farm.asf.session.down = False
    farm.asf.session.plan = {'AAAAA-BBBBB-CCCCC': None}     # the bot went away
    farm.redeemTick(now=stored(farm)['redeemRetry']['nextTry'])
    assert stored(farm)['redeem'].startswith('бот ASF не в сети')


def test_retries_end_after_the_last_try(farm):
    session = farm.asf.session
    session.default = 53
    farm.setWinKey('indiegala', *farm.win, 'AAAAA-BBBBB-CCCCC')
    farm.redeemWin('indiegala', *farm.win)
    told = len(farm.told)
    for attempt in range(1, managerModule.REDEEM_TRIES + 1):
        pending = stored(farm)['redeemRetry']
        assert pending['tries'] == attempt - 1
        assert farm.redeemTick(now=pending['nextTry']) == 1
    assert len(session.sent) == 1 + managerModule.REDEEM_TRIES
    win = stored(farm)
    assert win.get('redeemRetry') is None and win['status'] == ''
    assert 'повторы не помогли' in win['redeem']
    # The quiet tries said nothing; the last one is told as a failure.
    assert farm.told[told:] == ['⚠️ IndieGala: ключ «Bundle» — '
                                'Steam просит подождать: слишком много активаций']
    assert farm.redeemTick(now=10 ** 12) == 0


def test_a_new_key_drops_the_old_retry(farm):
    farm.asf.session.default = 53
    farm.setWinKey('indiegala', *farm.win, 'AAAAA-BBBBB-CCCCC')
    farm.redeemWin('indiegala', *farm.win)
    assert stored(farm)['redeemRetry']
    farm.setWinKey('indiegala', *farm.win, 'DDDDD-EEEEE-FFFFF')
    assert stored(farm).get('redeemRetry') is None
    assert farm.redeemTick(now=10 ** 12) == 0


def test_the_clock_runs_the_retries(farm, monkeypatch):
    ran = threading.Event()

    class OneTick:
        calls = 0

        def wait(self, seconds):
            self.calls += 1
            return self.calls > 1

        def set(self):
            pass

    farm.clockStop = OneTick()
    monkeypatch.setattr(farm, 'reportTick', lambda: False)
    monkeypatch.setattr(farm, 'redeemTick', lambda: ran.set())
    farm.startClock()
    farm.clock.join(5)
    assert ran.is_set()
