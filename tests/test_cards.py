"""Telegram cards: HTML that Telegram accepts, the same card as plain text,
buttons, and the fallback when Telegram refuses a button."""
import json

from steamgiftbot import notify
from steamgiftbot.farm import cards
from steamgiftbot.settings import Settings


def test_card_html_escapes_site_text_and_links_the_headline():
    card = cards.Card('🎉', site='SteamGifts', key='steamgifts', headline='<Tom & Jerry>',
                      link='https://www.steamgifts.com/giveaway/x/', lines=['a < b'],
                      block=cards.table([['SG', '93 вх.'], ['IG', '8 вх.']]),
                      note='тихо',
                      buttons=[('Забрать ключ', 'https://x/'), ('bad', 'javascript:1')])
    text = card.html()
    assert text.startswith('🎉 <b>ВЫИГРЫШ</b> · <code>SG</code> SteamGifts')
    assert ('<a href="https://www.steamgifts.com/giveaway/x/">'
            '<b>&lt;Tom &amp; Jerry&gt;</b></a>') in text
    assert '<pre>SG  93 вх.\nIG  8 вх.</pre>' in text and 'a &lt; b' in text
    assert text.endswith('<i>тихо</i>')
    assert card.keyboard() == {'inline_keyboard': [[{'text': 'Забрать ключ', 'url': 'https://x/'}]]}
    plain = card.plain()
    assert '<' + 'b>' not in plain and plain.endswith('Забрать ключ: https://x/')


def test_site_codes_follow_the_project_page():
    assert cards.code('indiegala-2') == 'IG' and cards.code('opiumpulses') == 'OP'


class Telegram:
    """Refuses any message that carries buttons, the way Telegram answers a
    button it will not take."""

    def __init__(self, refuseButtons=False):
        self.calls, self.refuseButtons = [], refuseButtons

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        bad = self.refuseButtons and 'reply_markup' in json
        return Answer(400 if bad else 200, {'ok': not bad, 'description': 'Bad Request: '
                                            f'wrong HTTP URL in {url}'})


class Answer:
    def __init__(self, status, body):
        self.status_code, self.body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self.body


def settings():
    return Settings(telegram_token='123:SECRETTOKENxxxxxxxxxxxxxxxx', telegram_chat='42')


def test_card_goes_out_as_html_with_buttons():
    session = Telegram()
    card = cards.Card('✅', headline='ok', buttons=[('Открыть панель', 'http://100.64.0.5:8092/')])
    assert notify.send(settings(), card.plain(), session=session, card=card) == []
    payload = session.calls[0][1]
    assert payload['parse_mode'] == 'HTML' and payload['reply_markup']['inline_keyboard']


def test_refused_button_falls_back_to_links_in_the_text():
    session = Telegram(refuseButtons=True)
    card = cards.Card('✅', headline='ok', buttons=[('Открыть панель', 'http://192.168.1.10:8092/')])
    assert notify.send(settings(), card.plain(), session=session, card=card) == []
    retry = session.calls[1][1]
    assert 'reply_markup' not in retry
    assert 'Открыть панель: http://192.168.1.10:8092/' in retry['text']


def test_token_never_shows_in_a_problem():
    class Down:
        def post(self, url, json=None, timeout=None):
            raise notify.requests.ConnectionError(f"cannot reach {url}")
    problems = notify.send(settings(), 'x', session=Down())
    assert problems and 'SECRETTOKEN' not in problems[0] and '<token>' in problems[0]
