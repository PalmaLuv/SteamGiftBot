"""Finding your own Telegram chat id.

Telegram will not tell you what it is; it only reports chats that have already
written to the bot. So this is the one setup step that cannot be guessed, and
the bot has to do the asking.
"""
import pytest
import requests

from conftest import makeSettings

from steamgiftbot import notify
from steamgiftbot.cli import EXIT_BADSETUP, EXIT_FAILED, EXIT_OK, showTelegramChats


class Answer:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.text = str(body)

    def json(self):
        return self.body


class Fetcher:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.answer


def updates(*chats):
    return {'ok': True, 'result': [{'update_id': i, 'message': {'chat': chat}}
                                   for i, chat in enumerate(chats)]}


PRIVATE = {'id': 987654321, 'type': 'private', 'first_name': 'Palma'}
GROUP   = {'id': -1001234567890, 'type': 'supergroup', 'title': 'Giveaway alerts'}


class TestFindingChats:
    def test_it_asks_the_right_endpoint(self):
        fetcher = Fetcher(Answer(updates(PRIVATE)))
        notify.findChats('TOKEN', session=fetcher)
        assert fetcher.urls == ['https://api.telegram.org/botTOKEN/getUpdates']

    def test_a_private_chat_is_found(self):
        chats = notify.findChats('T', session=Fetcher(Answer(updates(PRIVATE))))
        assert [chat['id'] for chat in chats] == [987654321]

    def test_a_group_is_found_too(self):
        chats = notify.findChats('T', session=Fetcher(Answer(updates(GROUP))))
        assert [chat['id'] for chat in chats] == [-1001234567890]

    def test_the_same_chat_writing_twice_is_listed_once(self):
        answer = Answer(updates(PRIVATE, PRIVATE, GROUP))
        chats = notify.findChats('T', session=Fetcher(answer))
        assert len(chats) == 2

    def test_nothing_written_yet_is_an_empty_list_not_an_error(self):
        chats = notify.findChats('T', session=Fetcher(Answer({'ok': True, 'result': []})))
        assert chats == []

    @pytest.mark.parametrize('kind', ['channel_post', 'my_chat_member', 'edited_message'])
    def test_other_kinds_of_update_still_carry_a_chat(self, kind):
        body = {'ok': True, 'result': [{'update_id': 1, kind: {'chat': GROUP}}]}
        chats = notify.findChats('T', session=Fetcher(Answer(body)))
        assert [chat['id'] for chat in chats] == [-1001234567890]

    def test_a_wrong_token_is_reported(self):
        answer = Answer({'ok': False, 'description': 'Unauthorized'}, status_code=401)
        with pytest.raises(notify.NotifyError, match='Unauthorized'):
            notify.findChats('bad', session=Fetcher(answer))

    def test_an_unreachable_telegram_is_reported(self):
        fetcher = Fetcher(error=requests.RequestException('no route to host'))
        with pytest.raises(notify.NotifyError, match='Could not reach'):
            notify.findChats('T', session=fetcher)


class TestDescribing:
    def test_a_person_is_shown_by_name(self):
        line = notify.describeChat(PRIVATE)
        assert '987654321' in line and 'private' in line and 'Palma' in line

    def test_a_group_is_shown_by_title(self):
        assert 'Giveaway alerts' in notify.describeChat(GROUP)

    def test_a_nameless_chat_does_not_leave_a_ragged_line(self):
        assert notify.describeChat({'id': 5, 'type': 'private'}) == '5  private'


class TestTheCommand:
    def test_it_refuses_without_a_token(self, capsys):
        assert showTelegramChats(makeSettings()) == EXIT_BADSETUP
        assert 'BotFather' in capsys.readouterr().out

    def test_it_prints_the_id_and_the_line_to_paste(self, monkeypatch, capsys):
        monkeypatch.setattr(notify, 'findChats', lambda token, session=None: [PRIVATE])
        assert showTelegramChats(makeSettings(telegram_token='T')) == EXIT_OK

        printed = capsys.readouterr().out
        assert '987654321' in printed
        assert 'telegram_chat = 987654321' in printed

    def test_several_chats_are_all_listed(self, monkeypatch, capsys):
        monkeypatch.setattr(notify, 'findChats', lambda token, session=None: [PRIVATE, GROUP])
        showTelegramChats(makeSettings(telegram_token='T'))

        printed = capsys.readouterr().out
        assert '987654321' in printed and '-1001234567890' in printed
        # With more than one it must not pick for you.
        assert 'telegram_chat = 987654321' not in printed

    def test_an_untouched_bot_says_what_to_do(self, monkeypatch, capsys):
        monkeypatch.setattr(notify, 'findChats', lambda token, session=None: [])
        assert showTelegramChats(makeSettings(telegram_token='T')) == EXIT_FAILED
        assert 'send it any message' in capsys.readouterr().out

    def test_a_telegram_failure_is_reported(self, monkeypatch, capsys):
        def explode(token, session=None):
            raise notify.NotifyError('Telegram refused the message (HTTP 401): Unauthorized')

        monkeypatch.setattr(notify, 'findChats', explode)
        assert showTelegramChats(makeSettings(telegram_token='bad')) == EXIT_FAILED
        assert 'Unauthorized' in capsys.readouterr().out

    def test_it_works_even_with_telegram_switched_off(self, monkeypatch):
        # You may well be setting it up before turning it on.
        monkeypatch.setattr(notify, 'findChats', lambda token, session=None: [PRIVATE])
        config = makeSettings(telegram_token='T', telegram_enabled=False)
        assert showTelegramChats(config) == EXIT_OK
