from types import SimpleNamespace

import source.cur_web_3_bot as bot_module
from source.cur_web_3_bot import run


class FakeRedis:
    def __init__(self):
        self.data = {}

    def lpush(self, key, value):
        bucket = self.data.setdefault(key, [])
        bucket.insert(0, value)

    def lpop(self, key):
        bucket = self.data.setdefault(key, [])
        if not bucket:
            return None
        return bucket.pop(0)

    def llen(self, key):
        return len(self.data.get(key, []))

    def lrange(self, key, start, end):
        bucket = self.data.get(key, [])
        if not bucket:
            return []
        if end is None or end >= len(bucket):
            end = len(bucket) - 1
        if start < 0:
            start = 0
        return bucket[start:end + 1]


class MockTeleBot:
    def __init__(self):
        self.handlers = []
        self.sent_messages = []
        self.sent_locations = []

    def message_handler(self, *args, **kwargs):
        def decorator(func):
            self.handlers.append(func)
            return func
        return decorator

    def send_message(self, chat_id, text):
        self.sent_messages.append({"chat_id": chat_id, "text": text})

    def send_location(self, chat_id, latitude, longitude):
        self.sent_locations.append({
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
        })

    def polling(self):
        return "polling started"


def _make_message(chat_id=1, text="", location=None):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        text=text,
        location=location,
    )


def _install_fake_redis(monkeypatch, fake=None):
    if fake is None:
        fake = FakeRedis()
    monkeypatch.setattr(bot_module.redis, "from_url", lambda *args, **kwargs: fake)
    return fake


def _handler_by_name(bot, name):
    return next(handler for handler in bot.handlers if handler.__name__ == name)


def test_run_registers_handlers_and_starts_polling(monkeypatch):
    _install_fake_redis(monkeypatch)
    bot = MockTeleBot()

    run(bot)

    assert len(bot.handlers) >= 1
    assert bot.polling() == "polling started"


def test_run_help_handler_sends_instructions(monkeypatch):
    _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    help_handler = _handler_by_name(bot, "show_help")
    message = _make_message(chat_id=42)

    help_handler(message)

    assert bot.sent_messages
    assert "/start - начать работу" in bot.sent_messages[-1]["text"]


def test_run_start_handler_sets_initial_state(monkeypatch):
    _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    start_handler = _handler_by_name(bot, "start")
    start_message = _make_message(chat_id=88)

    start_handler(start_message)

    assert any("Location bot, базовый вариант" in msg["text"] for msg in bot.sent_messages)


def test_run_add_and_list_flow_works_with_mock_bot(monkeypatch):
    fake_redis = _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    add_handler = _handler_by_name(bot, "add_0")
    title_handler = _handler_by_name(bot, "add_1")
    location_handler = _handler_by_name(bot, "add_2")
    list_handler = _handler_by_name(bot, "list_last")

    add_message = _make_message(chat_id=7, text="")
    add_handler(add_message)
    title_message = _make_message(chat_id=7, text="Museum")
    title_handler(title_message)

    location_message = _make_message(
        chat_id=7,
        location=SimpleNamespace(latitude=51.5, longitude=-0.1),
    )
    location_handler(location_message)

    list_handler(add_message)

    assert any("Museum" in msg["text"] for msg in bot.sent_messages)
    assert any(loc["chat_id"] == 7 for loc in bot.sent_locations)
    assert fake_redis.data[7]


def test_run_add_2_invalid_location_returns_error(monkeypatch):
    _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    location_handler = _handler_by_name(bot, "add_2")
    invalid_message = _make_message(chat_id=16)

    location_handler(invalid_message)

    assert any("Невалидные координаты" in msg["text"] for msg in bot.sent_messages)


def test_run_unknown_message_handler_returns_error(monkeypatch):
    _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    fallback_handler = _handler_by_name(bot, "handle_message")
    message = _make_message(chat_id=22, text="surprise")

    fallback_handler(message)

    assert any("Неизвестная комманда surprise" in msg["text"] for msg in bot.sent_messages)


def test_run_list_last_handles_empty_list(monkeypatch):
    fake_redis = _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    list_handler = _handler_by_name(bot, "list_last")
    message = _make_message(chat_id=30)
    fake_redis.data[30] = []

    list_handler(message)

    assert any("Добавленных мест нет!" in msg["text"] for msg in bot.sent_messages)


def test_run_list_last_handles_many_items(monkeypatch):
    fake_redis = _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    list_handler = _handler_by_name(bot, "list_last")
    message = _make_message(chat_id=31)
    fake_redis.data[31] = [
        "A&#94;1.0&#94;2.0",
        "B&#94;1.1&#94;2.1",
        "C&#94;1.2&#94;2.2",
        "D&#94;1.3&#94;2.3",
        "E&#94;1.4&#94;2.4",
    ]

    list_handler(message)

    assert any("Последние 5 мест:" in msg["text"] for msg in bot.sent_messages)
    assert len(bot.sent_locations) == 5


def test_run_reset_clears_user_storage(monkeypatch):
    fake_redis = _install_fake_redis(monkeypatch)
    bot = MockTeleBot()
    run(bot)

    reset_handler = _handler_by_name(bot, "reset")
    message = _make_message(chat_id=41)
    fake_redis.data[41] = ["Old place"]

    reset_handler(message)

    assert fake_redis.llen(41) == 0
    assert any("Все Ваши локации удалены!" in msg["text"] for msg in bot.sent_messages)
