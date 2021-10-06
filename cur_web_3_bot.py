# -*- coding: utf-8 -*-
from collections import defaultdict
import os
import redis
import telebot
# from common import bot_token


class StateHandler:
    MAX_STATE = 3
    ADD_START, ADD_TITLE, ADD_ADDRESS = range(MAX_STATE)
    TEXT = {ADD_START: "Начало работы", ADD_TITLE: "Ввод названия места", ADD_ADDRESS: "Ввод местоположения"}

    def __init__(self):
        self.USER_STATE = defaultdict(lambda: StateHandler.ADD_ADDRESS)

    def set_next_state(self, message, ns=None):
        self.USER_STATE[message.chat.id] = (self.get_state(message) + 1) % StateHandler.MAX_STATE if ns is None else ns

    def get_state(self, message):
        return self.USER_STATE[message.chat.id]

    def get_state_text(self, message):
        return StateHandler.TEXT[self.USER_STATE[message.chat.id]]


class StorageHandler:
    sep = "&#94"

    def __init__(self):
        self.r = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'), db=0, decode_responses=True)

    @staticmethod
    def encode_db_str(message, title):
        """converts location and title to a string to store in db"""
        return f'{title}{StorageHandler.sep}{message.location.latitude}{StorageHandler.sep}{message.location.longitude}'

    @staticmethod
    def decode_db_str(entry):
        """converts string from db to a readable string"""
        return "Название: '{}', координаты: '{}, {}'".format(*entry.split(StorageHandler.sep)) if StorageHandler.sep in entry else "Название: {}".format(entry)

    @staticmethod
    def location_db_str(entry):
        """converts string from db to a location dictionary"""
        if StorageHandler.sep not in entry:
            return None
        lst = entry.split(StorageHandler.sep)
        if len(lst) != 3:
            return None

        return lst[1], lst[2]

    def push_title(self, message):
        self.r.lpush(message.chat.id, message.text)
        g = self.r.lpop(message.chat.id)
        self.r.lpush(message.chat.id, message.text)
        return message.text

    def push_location(self, message):
        if message.location is not None:
            title = self.r.lpop(message.chat.id)
            full_location_data = StorageHandler.encode_db_str(message, title)
            self.r.lpush(message.chat.id, full_location_data)
            return full_location_data
        else:
            return None

    def reset(self, message):
        while self.r.llen(message.chat.id) > 0:
            self.r.lpop(message.chat.id)

    def get_last(self, message, num):
        last_locations = self.r.lrange(message.chat.id, 0, num - 1)
        result = [entry for entry in last_locations]
        return result


if __name__ == "__main__":
    token_env_var = 'COURSERA_PY_WEB_3_LOCATION_BOT_TOKEN'
    bot_token = os.getenv(token_env_var)
    if not bot_token:
        print(f"ENV VAR {token_env_var} is not set")
        exit(-1)

    bot = telebot.TeleBot(bot_token)
    state = StateHandler()

    storage = StorageHandler()

    start_str = "Location bot, базовый вариант. Добавление мест в 2 этапа - название, потом геолокация.\n""/help  - напечатать подсказки\n"

    @bot.message_handler(commands=['start'])
    def start(message):
        # print("ID: ", message.chat.id)
        state.set_next_state(message, StateHandler.ADD_START)
        bot.send_message(chat_id=message.chat.id, text=start_str)

    @bot.message_handler(commands=['help'])
    def show_help(message):
        bot.send_message(chat_id=message.chat.id, text=start_str +
                         "/start - начать работу\n"
                         "/add – добавление нового места\n"
                         "Для ввода местоположения на смартфоне нужно\nнажать вложение к сообщению,\n"
                         "далее Геопозиция и выбор конкретного места на карте\n"
                         "/list – отображение добавленных мест\n"
                         "/reset позволяет пользователю удалить все его добавленные локации(помним про GDPR)\n\n" +
                         f"Cостояние бота в общении с Вами: {state.get_state_text(message)}\n"
                         )

    # / add – добавление нового места;
    @bot.message_handler(commands=['add'])
    def add_0(message):
        bot.send_message(chat_id=message.chat.id, text="Введите название места:")
        state.set_next_state(message)
        # print("next state:", state.get_state(message))
        return

    @bot.message_handler(func=lambda message: state.get_state(message) == StateHandler.ADD_TITLE,
                         content_types=['text'])
    def add_1(message):
        # print("Title:", message.text)
        title = storage.push_title(message)
        bot.send_message(chat_id=message.chat.id, text=f"Введите координаты места {title}")
        state.set_next_state(message)
        # print("next state:", state.get_state(message))
        return

    @bot.message_handler(func=lambda message: state.get_state(message) == StateHandler.ADD_ADDRESS,
                         content_types=['location'])
    def add_2(message):
        # print("coordinates:", message.location)
        loc = storage.push_location(message)
        if loc is not None:
            bot.send_message(chat_id=message.chat.id, text=f"{StorageHandler.decode_db_str(loc)} добавлено!")
            state.set_next_state(message)
            bot.send_message(chat_id=message.chat.id, text=start_str)
        else:
            bot.send_message(chat_id=message.chat.id, text="Невалидные координаты. Введите координаты места:")
        # print("next state:", state.get_state(message))
        return

    # /list – отображение добавленных мест;
    @bot.message_handler(commands=['list'])
    def list_last(message):
        max_loc = 10 # TODO 10
        lst = storage.get_last(message, max_loc)
        if len(lst) == 0:
            msg = f"Добавленных мест нет!"
        elif len(lst) == 1:
            msg = f"Последнее место:"
        elif len(lst) in (2, 3, 4):
            msg = f"Последние {len(lst)} места:"
        else:
            msg = f"Последние {len(lst)} мест:"


        bot.send_message(chat_id=message.chat.id, text=msg)
        for l in lst:
            bot.send_message(chat_id=message.chat.id, text=StorageHandler.decode_db_str(l))
            loc = StorageHandler.location_db_str(l)
            if loc is not None:
                # print(loc)
                bot.send_location(chat_id=message.chat.id, latitude=loc[0], longitude=loc[1])


    # /reset позволяет пользователю удалить все его добавленные локации(помним про GDPR)
    @bot.message_handler(commands=['reset'])
    def reset(message):
        storage.reset(message)
        bot.send_message(chat_id=message.chat.id, text="Все Ваши локации удалены!")
        state.set_next_state(message, StateHandler.ADD_START)
        bot.send_message(chat_id=message.chat.id, text=start_str)

    @bot.message_handler()
    def handle_message(message):
        # print(message.text, "state :", state.get_state(message))
        bot.send_message(chat_id=message.chat.id, text=f'Неизвестная комманда {message.text}')


    bot.polling()
