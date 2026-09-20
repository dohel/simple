from types import SimpleNamespace

import source.cur_web_3_bot as cur_web_3_bot


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


def _message(chat_id=1, text=None, latitude=None, longitude=None):
    location = None
    if latitude is not None and longitude is not None:
        location = SimpleNamespace(latitude=latitude, longitude=longitude)
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=text, location=location)


def _build_storage_handler(monkeypatch):
    monkeypatch.setattr(cur_web_3_bot.redis, "from_url", lambda *args, **kwargs: FakeRedis())
    return cur_web_3_bot.StorageHandler()


def test_storage_handler_init_creates_redis_client(monkeypatch):
    handler = _build_storage_handler(monkeypatch)

    assert handler.r is not None
    assert isinstance(handler.r, FakeRedis)


def test_storage_handler_encode_db_str_and_decode_db_str(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    message = _message(chat_id=1, text="Central Park", latitude=40.78, longitude=-73.97)

    encoded = handler.encode_db_str(message, "Central Park")
    expected_encoded = f"Central Park{cur_web_3_bot.StorageHandler.sep}40.78{cur_web_3_bot.StorageHandler.sep}-73.97"

    assert encoded == expected_encoded
    assert handler.decode_db_str(encoded) == "Название: 'Central Park', координаты: '40.78, -73.97'"


def test_storage_handler_location_db_str_returns_coordinates_tuple(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    encoded = f"Central Park{cur_web_3_bot.StorageHandler.sep}40.78{cur_web_3_bot.StorageHandler.sep}-73.97"

    result = handler.location_db_str(encoded)

    assert result == ("40.78", "-73.97")


def test_storage_handler_location_db_str_returns_none_for_invalid_entry(monkeypatch):
    handler = _build_storage_handler(monkeypatch)

    assert handler.location_db_str("not-a-valid-entry") is None


def test_storage_handler_push_title_stores_title(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    message = _message(chat_id=7, text="Museum")

    result = handler.push_title(message)

    assert result == "Museum"
    assert handler.r.data[7] == ["Museum"]


def test_storage_handler_push_location_combines_title_and_coordinates(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    message = _message(chat_id=8, latitude=51.5074, longitude=-0.1278)
    handler.r.data[8] = ["London"]

    result = handler.push_location(message)
    expected = f"London{cur_web_3_bot.StorageHandler.sep}51.5074{cur_web_3_bot.StorageHandler.sep}-0.1278"

    assert result == expected
    assert handler.r.data[8] == [expected]


def test_storage_handler_reset_removes_all_entries(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    message = _message(chat_id=9, text="Paris")
    handler.push_title(message)

    handler.reset(message)

    assert handler.r.llen(9) == 0


def test_storage_handler_get_last_returns_recent_entries(monkeypatch):
    handler = _build_storage_handler(monkeypatch)
    message = _message(chat_id=10)
    handler.r.data[10] = ["first", "second", "third"]

    result = handler.get_last(message, 2)

    assert result == ["first", "second"]
