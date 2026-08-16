import pytest

from conftest import FakeResponse, FakeSession, fixture, makeSettings

from steamgiftbot.bot import SteamGift, SteamGiftError


class TestReadingThePage:
    def test_reads_token_and_balance(self, makeBot):
        bot = makeBot()
        bot.updateInfo()
        assert bot.xsrfToken == '0123456789abcdef'
        # The page prints '1,250'; a thousands separator must not break parsing.
        assert bot.points == 1250

    def test_invalid_cookie_is_reported(self, makeBot):
        bot = makeBot(FakeSession(home='<html><body>Sign in</body></html>'))
        with pytest.raises(SteamGiftError, match="Cookie is not valid"):
            bot.updateInfo()

    def test_http_error_is_reported(self, makeBot):
        session = FakeSession()
        session.get = lambda url, **kwargs: FakeResponse('', status_code=503)
        bot = makeBot(session)
        with pytest.raises(SteamGiftError, match="Could not reach"):
            bot.updateInfo()


class TestChoosingGiveaways:
    def test_enters_only_what_it_should(self, makeBot):
        session = FakeSession()
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        # Portal 2 only: Half-Life is already entered, RimWorld is pinned and
        # pinned is off, Very Expensive costs more than the balance.
        assert session.entered == ['aaa11']

    def test_pinned_flag_lets_pinned_through(self, makeBot):
        session = FakeSession()
        bot = makeBot(session, pinned=True)
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == ['aaa11', 'ccc33']

    def test_balance_comes_from_the_server(self, makeBot):
        bot = makeBot()
        bot.updateInfo()
        bot.getGameContent()
        # The ajax answer says 1000, which beats the local 1250 - 30.
        assert bot.points == 1000

    def test_balance_falls_back_to_local_math(self, makeBot):
        session = FakeSession(entryResponse=FakeResponse('{"type":"success"}'))
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.points == 1250 - 30

    def test_rejected_entry_does_not_spend_points(self, makeBot):
        session = FakeSession(
            entryResponse=FakeResponse('{"type":"error","msg":"Already entered"}'))
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.points == 1250

    def test_empty_first_page_is_fatal(self, makeBot):
        bot = makeBot(FakeSession(pages={}))
        bot.updateInfo()
        with pytest.raises(SteamGiftError, match="Page is empty"):
            bot.getGameContent()

    def test_running_out_of_pages_just_returns(self, makeBot):
        session = FakeSession()
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        # Page 1 had giveaways, page 2 was empty: that ends the walk quietly.
        assert any('page=2' in url for url in session.requested)


class TestBrokenAnswers:
    def test_html_instead_of_json_is_reported(self, makeBot):
        session = FakeSession(entryResponse=FakeResponse('<html>login</html>'))
        bot = makeBot(session)
        bot.updateInfo()
        with pytest.raises(SteamGiftError, match="expired"):
            bot.getGameContent()

    def test_network_failure_does_not_crash_the_run(self, makeBot):
        import requests

        session = FakeSession()

        def explode(url, data=None, **kwargs):
            raise requests.RequestException("connection reset")

        session.post = explode
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.points == 1250

    def test_start_returns_failure_code(self, makeBot):
        bot = makeBot(FakeSession(home='<html></html>'))
        assert bot.start() == 1


class TestSingleRun:
    def test_once_never_sleeps(self, makeBot):
        session = FakeSession(
            entryResponse=FakeResponse('{"type":"success","points":"5"}'))
        bot = makeBot(session, min_points=100, once=True)
        slept = []
        bot.waitForPoints = lambda: slept.append(1)

        assert bot.start() == 0
        assert slept == []
        assert bot.running is False

    def test_without_once_it_waits_instead(self, makeBot):
        session = FakeSession(
            entryResponse=FakeResponse('{"type":"success","points":"5"}'))
        bot = makeBot(session, min_points=100, once=False)
        slept = []

        def waitThenStop():
            slept.append(1)
            bot.stop()

        bot.waitForPoints = waitThenStop
        bot.start()
        assert slept == [1]

    def test_low_balance_does_not_recurse(self, makeBot):
        # The old code called start() from inside the page loop, so every wait
        # grew the stack. Waiting must be a plain return.
        session = FakeSession()
        bot = makeBot(session, min_points=5000)
        bot.updateInfo()
        bot.waitForPoints = lambda: None
        bot.getGameContent()
        assert session.entered == []

    def test_stop_breaks_the_countdown(self, makeBot):
        bot = makeBot()
        bot.running = False
        bot.waitForPoints()          # returns at once instead of counting down


class TestSession:
    def test_retries_user_agent_and_cookie_are_set(self):
        bot = SteamGift(makeSettings())
        adapter = bot.session.get_adapter('https://www.steamgifts.com')
        assert adapter.max_retries.total == 5
        # 429 is in the list so urllib3 honours Retry-After.
        assert 429 in adapter.max_retries.status_forcelist
        assert 'Mozilla' in bot.session.headers['User-Agent']
        assert bot.session.cookies.get('PHPSESSID') == 'cookievalue'

    def test_post_is_not_retried(self):
        # Replaying an entry could spend points twice.
        bot = SteamGift(makeSettings())
        adapter = bot.session.get_adapter('https://www.steamgifts.com')
        assert 'POST' not in adapter.max_retries.allowed_methods


CHALLENGE_PAGE = ('<!DOCTYPE html><html><head><title>Just a moment...</title>'
                  '<script src="https://challenges.cloudflare.com/turnstile"></script>'
                  '</head><body></body></html>')


class TestCloudflare:
    def test_a_challenge_page_is_named_for_what_it_is(self, makeBot):
        # Without this the missing xsrf_token reads as "your cookie is bad",
        # which sends people off changing a cookie that was fine.
        session = FakeSession()
        session.get = lambda url, **kwargs: FakeResponse(CHALLENGE_PAGE, status_code=403)
        bot = makeBot(session)

        with pytest.raises(SteamGiftError, match="Cloudflare"):
            bot.updateInfo()

    def test_a_challenge_on_entry_is_named_too(self, makeBot):
        session = FakeSession(
            entryResponse=FakeResponse(CHALLENGE_PAGE, status_code=403))
        bot = makeBot(session)
        bot.updateInfo()

        with pytest.raises(SteamGiftError, match="Cloudflare"):
            bot.getGameContent()

    def test_an_ordinary_403_is_not_blamed_on_cloudflare(self, makeBot):
        session = FakeSession()
        session.get = lambda url, **kwargs: FakeResponse('nope', status_code=403)
        bot = makeBot(session)

        with pytest.raises(SteamGiftError, match="Could not reach"):
            bot.updateInfo()


class TestFiltersInAction:
    def test_a_cost_limit_is_honoured(self, makeBot):
        session = FakeSession()
        bot = makeBot(session, max_cost=10)
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == []

    def test_a_blacklisted_game_is_left_alone(self, makeBot):
        session = FakeSession()
        bot = makeBot(session, blacklist=('portal',))
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == []

    def test_cards_only_asks_the_store_once_per_game(self, makeBot, monkeypatch):
        from steamgiftbot import steam_api

        asked = []

        def fakeLookUp(appid):
            asked.append(appid)
            return True

        monkeypatch.setattr(steam_api, '_lookUp', fakeLookUp)

        session = FakeSession(pages={1: fixture('giveaways.html'),
                                     2: fixture('giveaways.html')})
        bot = makeBot(session, cards_only=True)
        bot.updateInfo()
        bot.getGameContent()

        # Portal 2 appears on both pages; the answer is memoised.
        assert asked == [620]

    def test_an_affordable_bundle_is_skipped_when_cards_are_required(self, makeBot,
                                                                     monkeypatch):
        from steamgiftbot import filters, steam_api

        monkeypatch.setattr(steam_api, '_lookUp', lambda appid: True)
        session = FakeSession(pages={1: fixture('giveaways_bundle.html')})
        bot = makeBot(session, cards_only=True)
        bot.updateInfo()
        bot.getGameContent()

        assert session.entered == []
        assert bot.stats.skipped[filters.UNKNOWN_APP] == 1

    def test_the_same_bundle_is_entered_without_the_cards_setting(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways_bundle.html')})
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == ['eee55']


class TestRunReport:
    def test_the_summary_counts_what_happened(self, makeBot):
        from steamgiftbot import filters

        bot = makeBot()
        bot.updateInfo()
        bot.getGameContent()

        assert bot.stats.entered == 1
        assert bot.stats.pointsSpent == 30
        assert bot.stats.skipped[filters.ALREADY_ENTERED] == 1
        assert bot.stats.skipped[filters.PINNED] == 1
        assert bot.stats.skipped[filters.NOT_ENOUGH] == 1

    def test_a_rejected_entry_is_counted(self, makeBot):
        session = FakeSession(
            entryResponse=FakeResponse('{"type":"error","msg":"Already entered"}'))
        bot = makeBot(session)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.stats.rejected == 1
        assert bot.stats.entered == 0

    def test_the_summary_is_sent_when_a_webhook_is_set(self, makeBot, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])

        bot = makeBot(once=True, discord_webhook='https://hook')
        bot.start()
        assert len(sent) == 1
        assert "Entered 1 giveaways for 30 points." in sent[0]

    def test_a_failure_is_reported_too(self, makeBot, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])

        bot = makeBot(FakeSession(pages={}), discord_webhook='https://hook')
        assert bot.start() == 1
        assert "The run stopped" in sent[0]

    def test_a_dead_cookie_gets_its_own_wording(self, makeBot, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])

        bot = makeBot(FakeSession(home='<html></html>'), discord_webhook='https://hook')
        assert bot.start() == 1
        assert "session has expired" in sent[0]

    def test_nothing_is_sent_without_a_destination(self, makeBot, monkeypatch):
        sent = []
        monkeypatch.setattr('steamgiftbot.bot.notify.send',
                            lambda config, text, session=None: sent.append(text) or [])

        bot = makeBot(once=True)
        bot.start()
        assert sent == []


def test_info_json_is_found_from_any_directory(tmp_path, monkeypatch):
    import json

    monkeypatch.chdir(tmp_path)
    from steamgiftbot import bot as botModule

    # Reloading the module here would hand every later test a different
    # SteamGiftError class, so check the resolved path instead.
    assert botModule.INFO_PATH.is_absolute()
    with botModule.INFO_PATH.open(encoding='utf-8') as infoFile:
        assert json.load(infoFile)['URL'].startswith('https://')
