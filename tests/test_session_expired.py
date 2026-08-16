"""A dead cookie is the one failure the user has to act on, so it gets its own
message rather than being folded into a generic error."""
import pytest

from conftest import FakeResponse, FakeSession

from steamgiftbot import notify
from steamgiftbot.bot import SESSION_ADVICE, SessionExpired, SteamGiftError
from steamgiftbot.cli import buildParser, sendTestNotification
from conftest import makeSettings


@pytest.fixture
def sentMessages(monkeypatch):
    sent = []
    monkeypatch.setattr('steamgiftbot.bot.notify.send',
                        lambda config, text, session=None: sent.append(text) or [])
    return sent


class TestItIsToldApart:
    def test_a_bad_cookie_raises_the_specific_error(self, makeBot):
        bot = makeBot(FakeSession(home='<html><body>Sign in</body></html>'))
        with pytest.raises(SessionExpired):
            bot.updateInfo()

    def test_a_dead_session_on_entry_raises_it_too(self, makeBot):
        session = FakeSession(entryResponse=FakeResponse('<html>login</html>'))
        bot = makeBot(session)
        bot.updateInfo()
        with pytest.raises(SessionExpired):
            bot.getGameContent()

    def test_it_is_still_a_steamgift_error(self):
        # Callers that only care that the run failed keep working.
        assert issubclass(SessionExpired, SteamGiftError)

    def test_an_unreachable_site_is_not_a_dead_session(self, makeBot):
        session = FakeSession()
        session.get = lambda url, **kwargs: FakeResponse('', status_code=500)
        bot = makeBot(session)
        with pytest.raises(SteamGiftError) as raised:
            bot.updateInfo()
        assert not isinstance(raised.value, SessionExpired)


class TestItIsAnnounced:
    def test_telegram_hears_about_a_dead_cookie(self, makeBot, sentMessages):
        bot = makeBot(FakeSession(home='<html></html>'),
                      telegram_token='TOKEN', telegram_chat='42')
        assert bot.start() == 1
        assert len(sentMessages) == 1
        assert "session has expired" in sentMessages[0]

    def test_the_message_says_what_to_do_about_it(self, makeBot, sentMessages):
        bot = makeBot(FakeSession(home='<html></html>'),
                      telegram_token='TOKEN', telegram_chat='42')
        bot.start()
        assert "--setup" in sentMessages[0]
        assert "PHPSESSID" in sentMessages[0]

    def test_it_reads_differently_from_an_ordinary_failure(self, makeBot, sentMessages):
        session = FakeSession(pages={})          # empty first page, not a cookie problem
        bot = makeBot(session, telegram_token='TOKEN', telegram_chat='42')
        bot.start()
        assert "session has expired" not in sentMessages[0]

    def test_the_advice_is_printed_as_well(self, makeBot, sentMessages, capsys):
        bot = makeBot(FakeSession(home='<html></html>'),
                      telegram_token='TOKEN', telegram_chat='42')
        bot.start()
        assert SESSION_ADVICE.splitlines()[0] in capsys.readouterr().out

    def test_nothing_is_sent_when_telegram_is_switched_off(self, makeBot, sentMessages):
        bot = makeBot(FakeSession(home='<html></html>'),
                      telegram_token='TOKEN', telegram_chat='42',
                      telegram_enabled=False)
        bot.start()
        assert sentMessages == []


class TestTheOffSwitch:
    def test_telegram_is_on_once_a_token_and_chat_exist(self):
        assert notify.telegramReady(makeSettings(telegram_token='T',
                                                 telegram_chat='42')) is True

    def test_it_can_be_switched_off_without_deleting_the_token(self):
        config = makeSettings(telegram_token='T', telegram_chat='42',
                              telegram_enabled=False)
        assert notify.telegramReady(config) is False
        assert notify.isConfigured(config) is False

    def test_the_flag_switches_it_off_too(self):
        args = buildParser().parse_args(['--no-telegram'])
        assert args.telegram_enabled is False

    def test_half_a_setup_is_not_enough(self):
        assert notify.telegramReady(makeSettings(telegram_token='T')) is False
        assert notify.telegramReady(makeSettings(telegram_chat='42')) is False


class TestTheTestMessage:
    def test_it_refuses_when_nothing_is_configured(self):
        assert sendTestNotification(makeSettings()) == 2

    def test_it_sends_one_message(self, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.cli.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])
        code = sendTestNotification(makeSettings(telegram_token='T', telegram_chat='42'))
        assert code == 0
        assert len(sent) == 1

    def test_a_delivery_failure_is_reported(self, monkeypatch):
        monkeypatch.setattr('steamgiftbot.cli.notify.send',
                            lambda config, text, session=None: ['Telegram: unauthorized'])
        assert sendTestNotification(makeSettings(telegram_token='T',
                                                 telegram_chat='42')) == 1
