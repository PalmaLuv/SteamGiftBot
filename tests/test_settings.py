import pytest

from steamgiftbot import settings as steamSettings
from steamgiftbot.cli import buildParser

# The exact file a user asked to be documented in the README.
REQUESTED_CONFIG = """[DEFAULT]
cookie = yourcookievalue
log_info = no
"""

COMPLETE_CONFIG = """[DEFAULT]
cookie = abc
log_info = no
gift_type = All
pinned = no
min_points = 0
"""


class TestConfigFile:
    def test_the_documented_file_is_understood(self, configPath):
        configPath.write_text(REQUESTED_CONFIG, encoding='utf-8')
        config = steamSettings.load(configPath)
        assert config.cookie == 'yourcookievalue'
        assert config.log_info is False

    def test_it_names_what_is_still_missing(self, configPath):
        configPath.write_text(REQUESTED_CONFIG, encoding='utf-8')
        config = steamSettings.load(configPath)
        assert config.missing() == ['gift_type', 'pinned', 'min_points']

    def test_a_complete_file_asks_for_nothing(self, configPath):
        configPath.write_text(COMPLETE_CONFIG, encoding='utf-8')
        assert steamSettings.load(configPath).missing() == []

    def test_zero_minimum_points_is_a_real_value(self, configPath):
        # bool(0) is False, so a naive check would treat this as unset.
        configPath.write_text(COMPLETE_CONFIG, encoding='utf-8')
        assert steamSettings.load(configPath).min_points == 0

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        config = steamSettings.load(tmp_path / 'nothing-here.ini')
        assert config.missing() == ['cookie', 'gift_type', 'pinned', 'min_points']

    @pytest.mark.parametrize('written, expected', [
        ('log_info = no', False), ('log_info = No', False), ('log_info = false', False),
        ('log_info = 0', False), ('log_info = off', False),
        ('log_info = yes', True), ('log_info = TRUE', True), ('log_info = 1', True),
    ])
    def test_yes_and_no_spellings(self, configPath, written, expected):
        configPath.write_text('[DEFAULT]\ncookie = abc\n' + written + '\n', encoding='utf-8')
        assert steamSettings.load(configPath).log_info is expected


class TestWhereConfigLives:
    def test_it_sits_next_to_main_py_when_running_from_source(self):
        assert (steamSettings.baseDir() / 'main.py').exists()

    def test_it_sits_next_to_the_exe_when_frozen(self, tmp_path, monkeypatch):
        # PyInstaller deletes the folder it unpacks the modules into, so a
        # config saved beside them would vanish and the bot would ask the setup
        # questions again on every single run.
        exe = tmp_path / 'SteamGiftBot.exe'
        exe.write_text('', encoding='utf-8')
        monkeypatch.setattr(steamSettings.sys, 'frozen', True, raising=False)
        monkeypatch.setattr(steamSettings.sys, 'executable', str(exe))

        assert steamSettings.baseDir() == tmp_path

    def test_the_frozen_path_is_not_a_temp_folder(self, tmp_path, monkeypatch):
        exe = tmp_path / 'SteamGiftBot.exe'
        exe.write_text('', encoding='utf-8')
        monkeypatch.setattr(steamSettings.sys, 'frozen', True, raising=False)
        monkeypatch.setattr(steamSettings.sys, 'executable', str(exe))

        assert '_MEI' not in str(steamSettings.baseDir())


class TestPrecedence:
    def test_environment_beats_the_file(self, configPath, monkeypatch):
        configPath.write_text(COMPLETE_CONFIG, encoding='utf-8')
        monkeypatch.setenv(steamSettings.ENV_PREFIX + 'GIFT_TYPE', 'wishlist')
        monkeypatch.setenv(steamSettings.ENV_PREFIX + 'MIN_POINTS', '120')

        config = steamSettings.load(configPath)
        assert config.gift_type == 'WishList'      # spelling is normalised
        assert config.min_points == 120

    def test_command_line_beats_the_environment(self, configPath, monkeypatch):
        configPath.write_text(COMPLETE_CONFIG, encoding='utf-8')
        monkeypatch.setenv(steamSettings.ENV_PREFIX + 'GIFT_TYPE', 'WishList')

        args = buildParser().parse_args(['--type', 'DLC', '--no-pinned', '--once'])
        config = steamSettings.load(configPath, args)
        assert config.gift_type == 'DLC'
        assert config.pinned is False
        assert config.once is True

    def test_absent_flags_keep_the_saved_values(self, configPath):
        configPath.write_text(COMPLETE_CONFIG, encoding='utf-8')
        args = buildParser().parse_args([])
        config = steamSettings.load(configPath, args)
        assert config.gift_type == 'All'
        assert config.pinned is False


class TestBadValues:
    @pytest.mark.parametrize('written, field', [
        ('gift_type = Nope', 'gift_type'),
        ('min_points = -5', 'min_points'),
        ('min_points = many', 'min_points'),
        ('pinned = maybe', 'pinned'),
        ('log_info = sometimes', 'log_info'),
    ])
    def test_a_bad_value_names_itself(self, configPath, written, field):
        configPath.write_text('[DEFAULT]\ncookie = abc\n' + written + '\n', encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match=field):
            steamSettings.load(configPath)

    def test_the_message_lists_the_valid_types(self, configPath):
        configPath.write_text('[DEFAULT]\ngift_type = Nope\n', encoding='utf-8')
        with pytest.raises(steamSettings.SettingsError, match='WishList'):
            steamSettings.load(configPath)


class TestSaving:
    def test_settings_survive_a_round_trip(self, configPath):
        saved = steamSettings.Settings(cookie='c1', log_info=True, gift_type='New',
                                       pinned=True, min_points=42)
        steamSettings.save(saved, configPath)

        loaded = steamSettings.load(configPath)
        assert (loaded.cookie, loaded.log_info, loaded.gift_type,
                loaded.pinned, loaded.min_points) == ('c1', True, 'New', True, 42)

    def test_once_is_never_written(self, configPath):
        steamSettings.save(steamSettings.Settings(cookie='c1', log_info=False,
                                                  gift_type='All', pinned=False,
                                                  min_points=0, once=True), configPath)
        # 'once' belongs to a single run, not to the saved setup.
        assert 'once' not in configPath.read_text(encoding='utf-8')
        assert steamSettings.load(configPath).once is False

    @pytest.mark.parametrize('name', steamSettings.RUNTIME_ONLY)
    def test_per_run_settings_are_never_written(self, configPath, name):
        saved = steamSettings.Settings(cookie='c1', log_info=False, gift_type='All',
                                       pinned=False, min_points=0, once=True, dry_run=True)
        steamSettings.save(saved, configPath)
        assert name not in configPath.read_text(encoding='utf-8')

    def test_the_filters_do_survive_a_round_trip(self, configPath):
        saved = steamSettings.Settings(cookie='c1', log_info=False, gift_type='All',
                                       pinned=False, min_points=0, max_cost=60,
                                       cards_only=True, blacklist=('simulator', 'hentai'))
        steamSettings.save(saved, configPath)

        loaded = steamSettings.load(configPath)
        assert loaded.max_cost == 60
        assert loaded.cards_only is True
        assert loaded.blacklist == ('simulator', 'hentai')

    def test_no_cost_limit_is_not_written_as_zero(self, configPath):
        # An absent max_cost means 'no limit'; zero would mean 'nothing at all'.
        steamSettings.save(steamSettings.Settings(cookie='c1', log_info=False,
                                                  gift_type='All', pinned=False,
                                                  min_points=0), configPath)
        assert steamSettings.load(configPath).max_cost is None

    def test_a_hand_written_once_is_kept(self, configPath):
        configPath.write_text('[DEFAULT]\nonce = yes\ncookie = old\n', encoding='utf-8')
        steamSettings.save(steamSettings.Settings(cookie='new', log_info=False,
                                                  gift_type='All', pinned=False,
                                                  min_points=0), configPath)
        reloaded = steamSettings.load(configPath)
        assert reloaded.once is True
        assert reloaded.cookie == 'new'
