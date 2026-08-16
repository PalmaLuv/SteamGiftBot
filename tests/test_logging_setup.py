import logging

from steamgiftbot import logging_setup


def test_no_file_is_written_when_logging_is_off(tmp_path):
    logging_setup.configure(False, tmp_path)
    logging_setup.getLogger().info("nothing should land on disk")
    assert list(tmp_path.iterdir()) == []


def test_the_run_gets_its_own_file(tmp_path):
    path = logging_setup.configure(True, tmp_path)
    logging_setup.getLogger().info("hello")
    logging.shutdown()

    assert path.exists()
    assert "hello" in path.read_text(encoding='utf-8')


def test_configuring_twice_does_not_double_up(tmp_path):
    logging_setup.configure(True, tmp_path)
    path = logging_setup.configure(True, tmp_path)
    logging_setup.getLogger().info("once only")
    logging.shutdown()

    # A second call must replace the handler, not add another one beside it.
    assert len(logging_setup.getLogger().handlers) == 1
    assert path.read_text(encoding='utf-8').count("once only") == 1


def test_logs_land_beside_the_config(tmp_path, monkeypatch):
    # A packed .exe started from somewhere else must not scatter its log, its
    # config and its state across three different directories.
    from steamgiftbot import cli

    configPath = tmp_path / 'config.ini'
    configPath.write_text('[DEFAULT]\ncookie=abc\ngift_type=All\npinned=no\n'
                          'min_points=0\nlog_info=yes\n', encoding='utf-8')

    used = []
    monkeypatch.setattr(cli, 'startLogFile', lambda write, logDir=None: used.append(logDir))
    monkeypatch.setattr('steamgiftbot.bot.SteamGift.start', lambda self: 0)
    monkeypatch.chdir(tmp_path.parent)

    cli.run(['--config', str(configPath), '--no-input'])
    assert used == [tmp_path / 'log']


def test_messages_do_not_leak_to_the_root_logger(tmp_path, capsys):
    logging_setup.configure(False, tmp_path)
    logging_setup.getLogger().info("quiet please")
    assert capsys.readouterr().err == ""
