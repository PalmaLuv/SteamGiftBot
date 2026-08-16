"""A dry run walks the site and reports, but never spends a point."""
from conftest import FakeResponse, FakeSession, fixture


class TestNothingIsSpent:
    def test_no_entry_is_posted(self, makeBot):
        session = FakeSession()
        bot = makeBot(session, dry_run=True)
        bot.updateInfo()
        bot.getGameContent()
        assert session.entered == []

    def test_it_still_reports_what_it_would_have_done(self, makeBot):
        bot = makeBot(dry_run=True)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.stats.entered == 1
        assert bot.stats.pointsSpent == 30

    def test_the_balance_is_spent_on_paper(self, makeBot):
        # Otherwise the walk would never reach the low balance branch and a dry
        # run would not resemble a real one.
        bot = makeBot(dry_run=True)
        bot.updateInfo()
        bot.getGameContent()
        assert bot.points == 1250 - 30

    def test_the_summary_says_it_was_a_dry_run(self, makeBot, capsys):
        bot = makeBot(dry_run=True, once=True)
        bot.start()
        assert "Dry run: nothing was actually entered." in capsys.readouterr().out

    def test_filters_are_applied_the_same_way(self, makeBot):
        session = FakeSession(pages={1: fixture('giveaways.html')})
        bot = makeBot(session, dry_run=True, blacklist=('portal',))
        bot.updateInfo()
        bot.getGameContent()
        assert bot.stats.entered == 0


class TestRateLimit:
    def test_a_429_is_waited_out_rather_than_hammered(self, makeBot, monkeypatch):
        from steamgiftbot import bot as botModule

        waited = []
        monkeypatch.setattr(botModule, 'sleep', lambda seconds: waited.append(seconds))

        response = FakeResponse('', status_code=429)
        response.headers = {'Retry-After': '30'}
        bot = makeBot(FakeSession(entryResponse=response))
        bot.updateInfo()
        bot.getGameContent()

        assert 30 in waited
        assert bot.stats.rateLimited == 1

    def test_a_missing_retry_after_falls_back_to_our_own_wait(self, makeBot, monkeypatch):
        from steamgiftbot import bot as botModule

        waited = []
        monkeypatch.setattr(botModule, 'sleep', lambda seconds: waited.append(seconds))

        response = FakeResponse('', status_code=429)
        response.headers = {}
        bot = makeBot(FakeSession(entryResponse=response))
        bot.updateInfo()
        bot.getGameContent()

        assert botModule.RATE_LIMIT_WAIT in waited

    def test_a_nonsense_retry_after_does_not_crash(self, makeBot, monkeypatch):
        from steamgiftbot import bot as botModule

        monkeypatch.setattr(botModule, 'sleep', lambda seconds: None)
        response = FakeResponse('', status_code=429)
        response.headers = {'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT'}
        bot = makeBot(FakeSession(entryResponse=response))
        bot.updateInfo()
        bot.getGameContent()
        assert bot.stats.rateLimited == 1


class TestPointsWait:
    def test_the_wait_can_be_shortened(self, makeBot):
        bot = makeBot(points_wait=5)
        assert bot.pointsWait == 5

    def test_it_falls_back_to_the_packaged_default(self, makeBot):
        from steamgiftbot import bot as botModule

        bot = makeBot()
        assert bot.pointsWait == botModule.POINTS_WAIT
