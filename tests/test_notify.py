import requests

from conftest import makeSettings

from steamgiftbot import notify
from steamgiftbot.stats import RunStats


class Recorder:
    def __init__(self, error=None, answer=None):
        self.calls = []
        self.error = error
        self.answer = answer

    def post(self, url, json=None, timeout=None):
        if self.error:
            raise self.error
        self.calls.append((url, json))
        return self.answer


class Answer:
    """What Telegram and Discord really send back."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {'ok': True} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class TestRefusals:
    def test_a_wrong_token_is_not_reported_as_success(self):
        # Telegram answers a bad token with a tidy 401, which requests does not
        # raise on. Without this, --notify-test would lie.
        recorder = Recorder(answer=Answer(401, {'ok': False,
                                                'description': 'Unauthorized'}))
        problems = notify.send(makeSettings(telegram_token='bad', telegram_chat='42'),
                               'done', session=recorder)
        assert len(problems) == 1
        assert 'Unauthorized' in problems[0]

    def test_ok_false_with_http_200_is_caught_too(self):
        recorder = Recorder(answer=Answer(200, {'ok': False,
                                                'description': 'chat not found'}))
        problems = notify.send(makeSettings(telegram_token='T', telegram_chat='nope'),
                               'done', session=recorder)
        assert 'chat not found' in problems[0]

    def test_a_dead_discord_webhook_is_caught(self):
        recorder = Recorder(answer=Answer(404, {'message': 'Unknown Webhook'}))
        problems = notify.send(makeSettings(discord_webhook='https://hook'),
                               'done', session=recorder)
        assert 'Unknown Webhook' in problems[0]

    def test_a_good_answer_reports_nothing(self):
        recorder = Recorder(answer=Answer(200, {'ok': True}))
        assert notify.send(makeSettings(telegram_token='T', telegram_chat='42'),
                           'done', session=recorder) == []

    def test_a_non_json_body_still_reports_the_status(self):
        answer = Answer(502, {})
        answer.json = lambda: (_ for _ in ()).throw(ValueError('not json'))
        answer.text = '<html>bad gateway</html>'
        problems = notify.send(makeSettings(discord_webhook='https://hook'),
                               'done', session=Recorder(answer=answer))
        assert '502' in problems[0]


class TestWhoGetsTold:
    def test_nothing_is_configured_by_default(self):
        assert notify.isConfigured(makeSettings()) is False

    def test_a_discord_webhook_counts(self):
        assert notify.isConfigured(makeSettings(discord_webhook='https://hook')) is True

    def test_a_telegram_token_alone_is_not_enough(self):
        # Without a chat id there is nowhere to send the message.
        assert notify.isConfigured(makeSettings(telegram_token='t')) is False
        assert notify.isConfigured(makeSettings(telegram_token='t',
                                                telegram_chat='42')) is True


class TestSending:
    def test_discord_gets_the_text(self):
        recorder = Recorder()
        problems = notify.send(makeSettings(discord_webhook='https://hook'),
                               'done', session=recorder)
        assert problems == []
        assert recorder.calls == [('https://hook', {'content': 'done'})]

    def test_telegram_gets_the_text(self):
        recorder = Recorder()
        notify.send(makeSettings(telegram_token='TOKEN', telegram_chat='42'),
                    'done', session=recorder)
        url, payload = recorder.calls[0]
        assert 'botTOKEN/sendMessage' in url
        assert payload == {'chat_id': '42', 'text': 'done'}

    def test_both_can_be_used_at_once(self):
        recorder = Recorder()
        notify.send(makeSettings(discord_webhook='https://hook',
                                 telegram_token='TOKEN', telegram_chat='42'),
                    'done', session=recorder)
        assert len(recorder.calls) == 2

    def test_a_delivery_failure_is_reported_not_raised(self):
        # A dead webhook must not turn a good run into a failed one.
        recorder = Recorder(error=requests.RequestException('no route to host'))
        problems = notify.send(makeSettings(discord_webhook='https://hook'),
                               'done', session=recorder)
        assert len(problems) == 1
        assert 'Discord' in problems[0]


class TestRunSummary:
    def test_an_empty_run_still_says_something(self):
        assert RunStats().summary() == "Entered 0 giveaways for 0 points."

    def test_it_counts_entries_and_points(self):
        stats = RunStats()
        stats.entry(30)
        stats.entry(45)
        assert stats.summary() == "Entered 2 giveaways for 75 points."

    def test_it_groups_the_reasons_for_skipping(self):
        stats = RunStats()
        stats.entry(30)
        stats.skip('on the blacklist')
        stats.skip('on the blacklist')
        stats.skip('no trading cards')
        stats.rejection()

        summary = stats.summary()
        assert "Entered 1 giveaways for 30 points." in summary
        assert "turned down 1 entries" in summary
        assert "Skipped 2: on the blacklist" in summary
        assert "Skipped 1: no trading cards" in summary
