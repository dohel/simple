import source.cur_web_3_bot as bot_module


def test_get_token_returns_value_when_env_var_is_set(monkeypatch):
    monkeypatch.setenv(bot_module.TOKEN_ENV_VAR, "test-token-123")

    token = bot_module.get_token()

    assert token == "test-token-123"


def test_get_token_returns_none_when_env_var_is_missing(monkeypatch):
    monkeypatch.delenv(bot_module.TOKEN_ENV_VAR, raising=False)

    token = bot_module.get_token()

    assert token is None


def test_runner_creates_bot_and_starts_run(monkeypatch):
    monkeypatch.setenv(bot_module.TOKEN_ENV_VAR, "runner-token")

    created = {}

    class FakeBot:
        def __init__(self, token):
            created["token"] = token

    def fake_run(bot):
        created["bot"] = bot

    monkeypatch.setattr(bot_module.telebot, "TeleBot", FakeBot)
    monkeypatch.setattr(bot_module, "run", fake_run)

    bot_module.runner()

    assert created["token"] == "runner-token"
    assert isinstance(created["bot"], FakeBot)


def test_runner_raises_when_token_missing(monkeypatch):
    monkeypatch.delenv(bot_module.TOKEN_ENV_VAR, raising=False)

    try:
        bot_module.runner()
        assert False, "Expected SystemExit when token is missing"
    except SystemExit as exc:
        assert exc.code == 1
