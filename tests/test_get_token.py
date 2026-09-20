import source.cur_web_3_bot as bot_module


def test_get_token_returns_value_when_env_var_is_set(monkeypatch):
    monkeypatch.setenv(bot_module.TOKEN_ENV_VAR, "test-token-123")

    token = bot_module.get_token()

    assert token == "test-token-123"


def test_get_token_returns_none_when_env_var_is_missing(monkeypatch):
    monkeypatch.delenv(bot_module.TOKEN_ENV_VAR, raising=False)

    token = bot_module.get_token()

    assert token is None
