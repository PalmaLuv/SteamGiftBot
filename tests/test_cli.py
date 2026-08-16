"""The unattended paths: cron and Docker must never hit an interactive prompt."""
from steamgiftbot import cli
from steamgiftbot import ui


class TestUnattendedRuns:
    def test_incomplete_setup_exits_with_a_code(self, configPath, monkeypatch):
        configPath.write_text('[DEFAULT]\ncookie = abc\n', encoding='utf-8')
        # Any question here would hang a cron job for ever.
        monkeypatch.setattr(ui, 'ask', _refuseToAsk)

        code = cli.run(['--config', str(configPath), '--no-input'])
        assert code == cli.EXIT_BADSETUP

    def test_it_says_which_settings_are_absent(self, configPath, capsys, monkeypatch):
        configPath.write_text('[DEFAULT]\ncookie = abc\n', encoding='utf-8')
        monkeypatch.setattr(ui, 'ask', _refuseToAsk)

        cli.run(['--config', str(configPath), '--no-input'])
        printed = capsys.readouterr().out
        assert 'gift_type' in printed and 'pinned' in printed and 'min_points' in printed

    def test_a_bad_value_exits_with_a_code(self, configPath):
        configPath.write_text('[DEFAULT]\ncookie = abc\ngift_type = Nope\n', encoding='utf-8')
        assert cli.run(['--config', str(configPath), '--no-input']) == cli.EXIT_BADSETUP

    def test_setup_menu_refuses_without_a_terminal(self, configPath):
        configPath.write_text('[DEFAULT]\n', encoding='utf-8')
        assert cli.run(['--config', str(configPath), '--setup',
                        '--no-input']) == cli.EXIT_BADSETUP


class TestFlags:
    def test_once_defaults_to_off(self):
        assert cli.buildParser().parse_args([]).once is None

    def test_pinned_has_three_states(self):
        parse = cli.buildParser().parse_args
        assert parse([]).pinned is None            # not mentioned: keep the config
        assert parse(['--pinned']).pinned is True
        assert parse(['--no-pinned']).pinned is False

    def test_log_has_three_states(self):
        parse = cli.buildParser().parse_args
        assert parse([]).log_info is None
        assert parse(['--log']).log_info is True
        assert parse(['--no-log']).log_info is False


def test_keyboard_interrupt_is_not_a_traceback(monkeypatch):
    def interrupt(argv=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, 'run', interrupt)
    assert cli.main([]) == cli.EXIT_OK


def _refuseToAsk(*args, **kwargs):
    raise AssertionError("the bot asked a question while running unattended")
