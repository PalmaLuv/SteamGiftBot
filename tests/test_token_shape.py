"""A Telegram token that is subtly wrong fails silently at the worst moment:
you find out by never being told that you won. So it is checked on the way in,
and the message names the likely cause."""
import pytest

from conftest import makeSettings

from steamgiftbot import settings as steamSettings
from steamgiftbot.cli import missingNotifySetting

GOOD_TOKEN = '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw'


class TestQuotesAndSpacing:
    @pytest.mark.parametrize('written', [
        f'telegram_token = "{GOOD_TOKEN}"',
        f"telegram_token = '{GOOD_TOKEN}'",
        f'telegram_token =    {GOOD_TOKEN}   ',
    ])
    def test_quotes_and_padding_are_stripped(self, configPath, written):
        configPath.write_text('[DEFAULT]\n' + written + '\n', encoding='utf-8')
        assert steamSettings.load(configPath).telegram_token == GOOD_TOKEN

    def test_a_quoted_cookie_is_unwrapped_too(self, configPath):
        configPath.write_text('[DEFAULT]\ncookie = "abc123"\n', encoding='utf-8')
        assert steamSettings.load(configPath).cookie == 'abc123'


class TestCatchingABadToken:
    def test_a_trailing_comment_is_named_as_such(self, configPath):
        # configparser keeps everything after the '=', comment included.
        configPath.write_text(f'[DEFAULT]\ntelegram_token = {GOOD_TOKEN}  # my bot\n',
                              encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='comment'):
            steamSettings.load(configPath)

    def test_a_space_inside_the_token_is_named(self, configPath):
        configPath.write_text(f'[DEFAULT]\ntelegram_token = {GOOD_TOKEN[:10]} {GOOD_TOKEN[10:]}\n',
                              encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='space'):
            steamSettings.load(configPath)

    @pytest.mark.parametrize('bad', [
        'AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw',   # the half after the colon only
        '123456789',                            # the half before it
        'my-telegram-bot',                      # a name, not a token
        '123456789:short',                      # cut off
    ])
    def test_a_token_of_the_wrong_shape_is_refused(self, configPath, bad):
        configPath.write_text(f'[DEFAULT]\ntelegram_token = {bad}\n', encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='telegram_token'):
            steamSettings.load(configPath)

    def test_a_real_token_passes(self, configPath):
        configPath.write_text(f'[DEFAULT]\ntelegram_token = {GOOD_TOKEN}\n', encoding='utf-8')
        assert steamSettings.load(configPath).telegram_token == GOOD_TOKEN

    def test_an_absent_token_is_not_an_error(self, configPath):
        configPath.write_text('[DEFAULT]\ntelegram_token =\n', encoding='utf-8')
        assert steamSettings.load(configPath).telegram_token == ''


class TestCatchingABadChatId:
    @pytest.mark.parametrize('good', ['987654321', '-1001234567890', '@mychannel'])
    def test_the_shapes_telegram_uses_are_accepted(self, configPath, good):
        configPath.write_text(f'[DEFAULT]\ntelegram_chat = {good}\n', encoding='utf-8')
        assert steamSettings.load(configPath).telegram_chat == good

    @pytest.mark.parametrize('bad', ['me', 'chat id here', '123 456'])
    def test_nonsense_is_refused(self, configPath, bad):
        configPath.write_text(f'[DEFAULT]\ntelegram_chat = {bad}\n', encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='telegram_chat'):
            steamSettings.load(configPath)

    def test_the_message_points_at_the_command_that_finds_it(self, configPath):
        configPath.write_text('[DEFAULT]\ntelegram_chat = me\n', encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='--telegram-chat-id'):
            steamSettings.load(configPath)


class TestSayingWhatIsActuallyMissing:
    def test_a_token_without_a_chat_says_so(self):
        message = missingNotifySetting(makeSettings(telegram_token=GOOD_TOKEN))
        assert 'telegram_chat is not' in message
        assert '--telegram-chat-id' in message

    def test_a_chat_without_a_token_says_so(self):
        message = missingNotifySetting(makeSettings(telegram_chat='42'))
        assert 'telegram_token is not' in message
        assert 'BotFather' in message

    def test_a_complete_setup_that_is_switched_off_says_so(self):
        # This used to read 'set telegram_token and telegram_chat', which sends
        # people off replacing a token that was never the problem.
        message = missingNotifySetting(makeSettings(telegram_token=GOOD_TOKEN,
                                                    telegram_chat='42',
                                                    telegram_enabled=False))
        assert 'switched off' in message

    def test_an_empty_setup_still_says_the_general_thing(self):
        assert 'Nothing to notify' in missingNotifySetting(makeSettings())
