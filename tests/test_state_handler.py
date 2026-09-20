from types import SimpleNamespace

from source.cur_web_3_bot import StateHandler


def _message(chat_id=1):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id))


def test_state_handler_init_sets_default_state():
    handler = StateHandler()
    message = _message(10)

    assert handler.get_state(message) == StateHandler.ADD_ADDRESS


def test_state_handler_set_next_state_advances_state():
    handler = StateHandler()
    message = _message(11)
    handler.USER_STATE[message.chat.id] = StateHandler.ADD_START

    handler.set_next_state(message)

    assert handler.get_state(message) == StateHandler.ADD_TITLE


def test_state_handler_set_next_state_can_override_state():
    handler = StateHandler()
    message = _message(12)

    handler.set_next_state(message, StateHandler.ADD_ADDRESS)

    assert handler.get_state(message) == StateHandler.ADD_ADDRESS


def test_state_handler_get_state_text_returns_descriptive_label():
    handler = StateHandler()
    message = _message(13)
    handler.USER_STATE[message.chat.id] = StateHandler.ADD_TITLE

    assert handler.get_state_text(message) == "Ввод названия места"
