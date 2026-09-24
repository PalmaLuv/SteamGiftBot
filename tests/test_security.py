"""The settings hold a live session cookie and bot tokens; keep them that way."""
import os
import sys

import pytest

from conftest import makeSettings

from steamgiftbot import cli, settings

HOOK = 'https://discord.com/api/webhooks/123456789012345678/abcDEF_ghi-JKL'


class TestDiscordWebhook:
    @pytest.mark.parametrize('value', [
        HOOK,
        HOOK + '/',
        'https://ptb.discord.com/api/webhooks/1/x',
        'https://discordapp.com/api/webhooks/1/x',
        f'"{HOOK}"',
    ])
    def test_a_real_webhook_is_accepted(self, value):
        assert settings.toDiscordWebhook(value) == value.strip('"')

    @pytest.mark.parametrize('value', [
        'http://discord.com/api/webhooks/1/x',
        'https://discord.com.evil.example/api/webhooks/1/x',
        'https://evil.example/?https://discord.com/api/webhooks/1/x',
        'https://169.254.169.254/latest/meta-data',
        'https://discord.com/api/webhooks/1/x # mine',
    ])
    def test_anything_else_is_refused(self, value):
        with pytest.raises(ValueError):
            settings.toDiscordWebhook(value)

    def test_empty_means_unset(self):
        assert settings.toDiscordWebhook('') == ''

    def test_a_bad_webhook_in_the_file_names_the_setting(self, configPath):
        configPath.write_text('[DEFAULT]\ndiscord_webhook = https://example.com/hook\n',
                              encoding='utf-8')
        with pytest.raises(settings.SettingsError, match='discord_webhook'):
            settings.load(configPath)


class TestSecretFiles:
    def test_a_value_can_come_from_a_file(self, tmp_path, monkeypatch, configPath):
        secret = tmp_path / 'cookie'
        secret.write_text('from-a-secret\n', encoding='utf-8')
        monkeypatch.setenv('STEAMGIFTBOT_COOKIE_FILE', str(secret))

        assert settings.load(configPath).cookie == 'from-a-secret'

    def test_the_plain_variable_wins_over_the_file(self, tmp_path, monkeypatch, configPath):
        secret = tmp_path / 'cookie'
        secret.write_text('from-a-secret', encoding='utf-8')
        monkeypatch.setenv('STEAMGIFTBOT_COOKIE_FILE', str(secret))
        monkeypatch.setenv('STEAMGIFTBOT_COOKIE', 'plain')

        assert settings.load(configPath).cookie == 'plain'

    def test_a_missing_file_is_a_clear_error(self, tmp_path, monkeypatch, configPath):
        monkeypatch.setenv('STEAMGIFTBOT_COOKIE_FILE', str(tmp_path / 'absent'))
        with pytest.raises(settings.SettingsError, match='STEAMGIFTBOT_COOKIE_FILE'):
            settings.load(configPath)


class TestKeepingTheFilePrivate:
    def test_windows_gets_an_owner_only_acl(self, tmp_path):
        called = []

        class Done:
            returncode = 0

        def runner(command, **kwargs):
            called.append(command)
            return Done()

        path = tmp_path / 'config.ini'
        assert settings.restrictToOwner(path, windows=True, runner=runner) is True
        command = called[0]
        assert command[:3] == ['icacls', str(path), '/inheritance:r']
        assert command[3] == '/grant:r' and command[4].endswith(':F')

    def test_a_failed_acl_is_reported(self, tmp_path):
        class Refused:
            returncode = 5

        assert settings.restrictToOwner(tmp_path / 'c.ini', windows=True,
                                        runner=lambda *a, **k: Refused()) is False

    def test_icacls_missing_is_reported(self, tmp_path):
        def missing(*args, **kwargs):
            raise FileNotFoundError('icacls')

        assert settings.restrictToOwner(tmp_path / 'c.ini', windows=True,
                                        runner=missing) is False

    @pytest.mark.skipif(sys.platform == 'win32', reason='POSIX permissions')
    def test_elsewhere_the_file_is_mode_600(self, tmp_path):
        path = tmp_path / 'config.ini'
        path.write_text('', encoding='utf-8')
        assert settings.restrictToOwner(path) is True
        assert os.stat(path).st_mode & 0o777 == 0o600

    def test_the_user_is_warned_when_it_did_not_work(self, monkeypatch, configPath, capsys):
        monkeypatch.setattr(settings, 'restrictToOwner', lambda path: False)
        cli.saveConfig(makeSettings(log_info=False), configPath)
        assert 'private' in capsys.readouterr().out


def test_sigterm_stops_the_bot_like_ctrl_c():
    with pytest.raises(KeyboardInterrupt):
        cli.handleTermination(15, None)
