# -*- coding: utf-8 -*-
"""Telegram location bot for collecting and storing user-defined places.

This module implements a simple Telegram chat bot that allows users to add
named places together with their geographic coordinates. The program manages the
conversation flow through a small finite-state machine, stores temporary and
persistent data in Redis, and exposes commands such as /start, /add, /list, and
/reset to interact with the user.

The bot is designed as a lightweight example of a location-based service: it
captures a title for a place, waits for a geolocation message from the user,
serializes the data into a Redis-backed record, then retrieves and displays saved
places when requested. Each Telegram chat is tracked independently, making it
possible to keep separate location histories for different users.

Key responsibilities of this module:
- define the bot's conversational state transitions,
- serialize and deserialize saved place entries,
- store the user's data in Redis by chat ID,
- register Telegram command and message handlers,
- send replies, location payloads, and help text to the user,
- run the polling loop that keeps the bot active.
"""
from collections import defaultdict
import os
import redis
import telebot
# from common import bot_token


class StateHandler:
    """Manage the conversational workflow for each Telegram chat.

    Purpose:
        This class keeps track of the current step in a multi-step interaction,
        allowing the bot to know whether it is waiting for a place name, a
        location, or for the user to begin a new session.

    Relationship with other classes:
        StateHandler is a collaborator of the bot module's command handlers. It
        is not a subclass of any other class and does not inherit from StorageHandler.
        Instead, it is used via association: the bot callbacks call
        set_next_state(), get_state(), and get_state_text() to update or read the
        current workflow state for a specific chat ID.

        It also has a close structural relationship with StorageHandler because the
        bot moves from one step to another while storing the intermediate title in
        Redis before the location data is collected. This is a logical association,
        not inheritance or composition in the strict OOP sense.

    OOD/OOP relation type:
        Association. The class is a service object that stores state information
        for one or more Telegram chats and is invoked by other code without owning
        its collaborators.
    """
    MAX_STATE = 3
    ADD_START, ADD_TITLE, ADD_ADDRESS = range(MAX_STATE)
    TEXT = {ADD_START: "Начало работы", ADD_TITLE: "Ввод названия места", ADD_ADDRESS: "Ввод местоположения"}

    def __init__(self):
        """Create a new state tracker for Telegram chat sessions.

        Parameters:
            None.

        Returns:
            None. Initializes the internal USER_STATE dictionary used to remember
            the current step for each chat ID.

        Notes:
            This method mutates the instance by creating a defaultdict that stores
            state values per chat identifier. The default state is ADD_ADDRESS.
        """
        self.USER_STATE = defaultdict(lambda: StateHandler.ADD_ADDRESS)

    def set_next_state(self, message, ns=None):
        """Advance or explicitly set the current conversation state for a chat.

        Parameters:
            message: Telegram message object whose chat.id identifies the user.
            ns: Optional integer state value to assign directly. If omitted, the
                next state is computed by advancing one step modulo MAX_STATE.

        Returns:
            None. This function updates the internal USER_STATE dictionary in place.

        Notes:
            This method mutates the passed-in state storage for the current chat by
            reference via self.USER_STATE[message.chat.id].
        """
        self.USER_STATE[message.chat.id] = (self.get_state(message) + 1) % StateHandler.MAX_STATE if ns is None else ns

    def get_state(self, message):
        """Return the current state for the given Telegram chat.

        Parameters:
            message: Telegram message object containing chat.id.

        Returns:
            int: The current conversation state for the chat. The returned value is
            read from the instance state map and is not modified.
        """
        return self.USER_STATE[message.chat.id]

    def get_state_text(self, message):
        """Get a human-readable label for the current state.

        Parameters:
            message: Telegram message object used to determine the current state.

        Returns:
            str: A descriptive label for the state, such as "Начало работы" or
            "Ввод названия места".
        """
        return StateHandler.TEXT[self.USER_STATE[message.chat.id]]


class StorageHandler:
    """Persist user-entered places in Redis and convert them to/from a stored format.

    Purpose:
        This class is responsible for storing a user's temporary title and final
        location records in Redis. It also formats those records for display in
        Telegram messages and extracts coordinate pairs when needed.

    Relationship with other classes:
        StorageHandler is used by the bot callbacks that handle /add, /list, and
        /reset. In OOP terms, it is a collaborator of the Telegram bot logic and is
        associated with StateHandler through the overall conversation flow: the user
        first enters a title, then the bot asks for a location, and finally the
        stored data is retrieved and displayed.

        The class owns and manages a Redis connection object as an instance
        attribute (self.r). This means the relationship is partially composite in
        the sense that the StorageHandler instance is responsible for creating and
        controlling the lifecycle of its Redis client, though the Redis service is
        external to the application and not a subclass relationship.

    OOD/OOP relation type:
        Composition/association hybrid. The class composes an internal Redis client
        connection object and is also associated with the bot logic through method
        calls such as push_title(), push_location(), and get_last().
    """
    sep = "&#94"

    def __init__(self):
        """Initialize the Redis-backed storage used to save user locations.

        Parameters:
            None.

        Returns:
            None. Creates a Redis client instance attached to self.r.

        Notes:
            This method mutates the StorageHandler instance by assigning a live Redis
            connection object to self.r. The connection uses the REDIS_URL variable
            when present and falls back to a localhost Redis instance.
        """
        self.r = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'), db=0, decode_responses=True)

    @staticmethod
    def encode_db_str(message, title):
        """Convert a Telegram location and its title into a single stored string.

        Parameters:
            message: Telegram message object that contains the user's location
                payload with latitude and longitude attributes.
            title: str: The human-readable place name previously entered by the user.

        Returns:
            str: A serialized value in the form "title{sep}latitude{sep}longitude".

        Notes:
            This function does not mutate its inputs; it returns a new string built
            from the provided values.
        """
        return f'{title}{StorageHandler.sep}{message.location.latitude}{StorageHandler.sep}{message.location.longitude}'

    @staticmethod
    def decode_db_str(entry):
        """Convert a stored database string into a user-friendly description.

        Parameters:
            entry: str: Serialized place data stored in Redis.

        Returns:
            str: A readable message showing the title and coordinates, or only the
            title when the entry has no coordinate data.

        Notes:
            This function does not mutate the input string; it produces a new
            formatted string for display in Telegram.
        """
        return "Название: '{}', координаты: '{}, {}'".format(*entry.split(StorageHandler.sep)) if StorageHandler.sep in entry else "Название: {}".format(entry)

    @staticmethod
    def location_db_str(entry):
        """Extract latitude and longitude from a serialized location entry.

        Parameters:
            entry: str: A stored value containing title and coordinate data.

        Returns:
            tuple | None: A two-item tuple of (latitude, longitude) when the entry
            is valid, otherwise None.

        Notes:
            This function does not modify the given string; it only parses and
            returns a new tuple structure.
        """
        if StorageHandler.sep not in entry:
            return None
        lst = entry.split(StorageHandler.sep)
        if len(lst) != 3:
            return None

        return lst[1], lst[2]

    def push_title(self, message):
        """Store a place title in Redis and return it to the calling code.

        Parameters:
            message: Telegram message object whose text contains the location title.

        Returns:
            str: The title text that was saved.

        Notes:
            This function mutates the Redis list for the current chat by pushing and
            then re-pushing the title. It also consumes and re-queues the value to
            preserve the expected temporary sequence used later when coordinates are
            attached.
        """
        self.r.lpush(message.chat.id, message.text)
        g = self.r.lpop(message.chat.id)
        self.r.lpush(message.chat.id, message.text)
        return message.text

    def push_location(self, message):
        """Save the user's coordinate payload together with the previously stored title.

        Parameters:
            message: Telegram message object that contains a location with latitude
                and longitude attributes.

        Returns:
            str | None: A serialized location string if the location is valid,
            otherwise None.

        Notes:
            This function mutates Redis state for the current chat by removing the
            saved title placeholder, combining it with coordinates, and pushing the
            final serialized record back into the list.
        """
        if message.location is not None:
            title = self.r.lpop(message.chat.id)
            full_location_data = StorageHandler.encode_db_str(message, title)
            self.r.lpush(message.chat.id, full_location_data)
            return full_location_data
        else:
            return None

    def reset(self, message):
        """Delete all stored location entries for the current Telegram chat.

        Parameters:
            message: Telegram message object whose chat.id identifies the user data
                to clear.

        Returns:
            None.

        Notes:
            This function mutates the Redis list in place by repeatedly removing all
            entries for the given chat until the list is empty.
        """
        while self.r.llen(message.chat.id) > 0:
            self.r.lpop(message.chat.id)

    def get_last(self, message, num):
        """Retrieve the most recent saved location entries for a chat.

        Parameters:
            message: Telegram message object used to identify the target chat.
            num: int: Maximum number of entries to return, ordered from newest to
                oldest according to Redis list semantics.

        Returns:
            list[str]: A list of serialized location records for the newest entries.

        Notes:
            This function does not mutate Redis. It reads data from the current chat's
            list and returns a new Python list containing the matching entries.
        """
        last_locations = self.r.lrange(message.chat.id, 0, num - 1)
        result = [entry for entry in last_locations]
        return result


def run(bot):
    """Configure and start the Telegram bot's command handlers and polling loop.

    Parameters:
        bot: telebot.TeleBot: A configured Telegram bot instance created by the
            caller, typically from a bot token in the environment.

    Returns:
        None. This function initializes the bot's state and storage, registers all
        handlers, and starts polling for incoming messages.

    Notes:
        This function sets up the bot's runtime state and mutates the given bot
        instance by registering handlers. It does not return a value; it starts the
        interaction loop for the bot.
    """
    state = StateHandler()
    storage = StorageHandler()

    start_str = "Location bot, базовый вариант. Добавление мест в 2 этапа - название, потом геолокация.\n""/help  - напечатать подсказки\n"

    @bot.message_handler(commands=['start'])
    def start(message):
        """Start the bot interaction and reset the user's state to the initial step.

        Parameters:
            message: Telegram message object received when the user sends /start.

        Returns:
            None. This function sends a welcome/help message to the chat and updates
            the internal conversation state.

        Notes:
            This function mutates the shared state tracker by calling set_next_state,
            which changes the stored state for this chat in place.
        """
        state.set_next_state(message, StateHandler.ADD_START)
        bot.send_message(chat_id=message.chat.id, text=start_str)

    @bot.message_handler(commands=['help'])
    def show_help(message):
        """Send the bot usage instructions and current state to the user.

        Parameters:
            message: Telegram message object that triggered the /help command.

        Returns:
            None. The function sends a formatted help text to the chat.

        Notes:
            This function does not mutate input data. It reads state via
            state.get_state_text(message) and sends a response.
        """
        bot.send_message(chat_id=message.chat.id, text=start_str +
                         "/start - начать работу\n"
                         "/add – добавление нового места\n"
                         "Для ввода местоположения на смартфоне нужно\nнажать вложение к сообщению,\n"
                         "далее Геопозиция и выбор конкретного места на карте\n"
                         "/list – отображение добавленных мест\n"
                         "/reset позволяет пользователю удалить все его добавленные локации(помним про GDPR)\n\n" +
                         f"Cостояние бота в общении с Вами: {state.get_state_text(message)}\n"
                         )

    @bot.message_handler(commands=['add'])
    def add_0(message):
        """Begin the process of adding a new place by requesting its name.

        Parameters:
            message: Telegram message object received after the user sends /add.

        Returns:
            None. The bot asks the user to enter the place title and advances the
            state machine to the title-entry phase.

        Notes:
            This function mutates the current chat state by calling set_next_state,
            which updates the state dictionary in place.
        """
        bot.send_message(chat_id=message.chat.id, text="Введите название места:")
        state.set_next_state(message)
        return

    @bot.message_handler(func=lambda message: state.get_state(message) == StateHandler.ADD_TITLE,
                         content_types=['text'])
    def add_1(message):
        """Accept a place title, save it temporarily, and ask for the location.

        Parameters:
            message: Telegram message object containing the entered place title.

        Returns:
            None. The function saves the title in Redis and sends a follow-up prompt
            asking for the geolocation.

        Notes:
            This function mutates both Redis storage and the chat's state: the title
            is stored via storage.push_title(message), and the state is advanced in
            place by set_next_state.
        """
        title = storage.push_title(message)
        bot.send_message(chat_id=message.chat.id, text=f"Введите координаты места {title}")
        state.set_next_state(message)
        return

    @bot.message_handler(func=lambda message: state.get_state(message) == StateHandler.ADD_ADDRESS,
                         content_types=['location'])
    def add_2(message):
        """Store a geolocation tied to the previously saved place title.

        Parameters:
            message: Telegram message object containing a location payload with
                latitude and longitude.

        Returns:
            None. The function sends a success message when the location is saved,
            otherwise asks the user to retry with a valid location.

        Notes:
            This function mutates Redis state when a valid location is present by
            calling storage.push_location(message), and it also updates the chat's
            state in place.
        """
        loc = storage.push_location(message)
        if loc is not None:
            bot.send_message(chat_id=message.chat.id, text=f"{StorageHandler.decode_db_str(loc)} добавлено!")
            state.set_next_state(message)
            bot.send_message(chat_id=message.chat.id, text=start_str)
        else:
            bot.send_message(chat_id=message.chat.id, text="Невалидные координаты. Введите координаты места:")
        return

    @bot.message_handler(commands=['list'])
    def list_last(message):
        """Display up to the most recent saved locations for the current user.

        Parameters:
            message: Telegram message object that identifies the chat whose saved
                places should be shown.

        Returns:
            None. The function sends a summary message and then each saved place as a
            human-readable text plus map coordinates when available.

        Notes:
            This function does not mutate persisted data. It reads from Redis via
            storage.get_last(message, max_loc) and sends responses to the user.
        """
        max_loc = 10
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
        for loc_entry in lst:
            bot.send_message(chat_id=message.chat.id, text=StorageHandler.decode_db_str(loc_entry))
            loc = StorageHandler.location_db_str(loc_entry)
            if loc is not None:
                bot.send_location(chat_id=message.chat.id, latitude=loc[0], longitude=loc[1])

    @bot.message_handler(commands=['reset'])
    def reset(message):
        """Delete every saved place for the current user and reset the conversation state.

        Parameters:
            message: Telegram message object whose chat.id identifies the user data
                to clear.

        Returns:
            None. The function confirms the cleanup and resets the bot back to the
            initial state.

        Notes:
            This function mutates the attached Redis storage in place by clearing all
            entries for the current chat. It also updates the state dictionary for the
            chat via state.set_next_state.
        """
        storage.reset(message)
        bot.send_message(chat_id=message.chat.id, text="Все Ваши локации удалены!")
        state.set_next_state(message, StateHandler.ADD_START)
        bot.send_message(chat_id=message.chat.id, text=start_str)

    @bot.message_handler()
    def handle_message(message):
        """Handle any message that does not match a known command or workflow step.

        Parameters:
            message: Telegram message object representing an unrecognized user input.

        Returns:
            None. The function responds with a message indicating that the command is
            unknown.

        Notes:
            This helper does not mutate the message object or the bot state; it only
            sends a reply to the user.
        """
        bot.send_message(chat_id=message.chat.id, text=f'Неизвестная комманда {message.text}')

    bot.polling()


TOKEN_ENV_VAR = 'COURSERA_PY_WEB_3_LOCATION_BOT_TOKEN'


def get_token():
    """Retrieve the Telegram bot token from the environment.

    Returns:
        str | None: The bot token string used to authenticate with the Telegram
        API when configured, otherwise None.
    """
    bot_token = os.getenv(TOKEN_ENV_VAR)
    if not bot_token:
        return None
    return bot_token


def runner():
    """Create the bot using the configured token and start the polling loop.

    Returns:
        None. This function validates the Telegram token, constructs the bot
        instance, and invokes run(bot) so the application starts in the same way
        it did under the old __main__ guard.

    Raises:
        SystemExit: If the required environment variable is not set.
    """
    token = get_token()
    if not token:
        print(f"ENV VAR {TOKEN_ENV_VAR} is not set")
        raise SystemExit(1)

    bot = telebot.TeleBot(token)
    run(bot)


if __name__ == "__main__":  # pragma: no cover - entrypoint may be excluded from test coverage
    runner()
