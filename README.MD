# Location Bot

This repository contains a Telegram bot that lets users save named places and later view the locations they have added.

## Purpose

The bot is designed to help a user:

- start a chat session with the bot,
- enter a place name,
- send a geolocation,
- store that location in Redis,
- list previously saved places,
- reset stored locations for privacy or cleanup.

This makes it a simple example of a location-based Telegram bot that stores user-specific data and displays it back on demand.

## How it works

The bot follows a small state machine:

1. User sends `/start` to begin.
2. User types `/add` to add a new place.
3. The bot asks for the place name.
4. The user sends the location via Telegram's geolocation feature.
5. The title and coordinates are saved in Redis.
6. User can retrieve saved entries with `/list`.
7. User can remove all stored entries with `/reset`.

Each user’s saved data is stored separately by chat ID, which allows multiple Telegram users to use the bot independently.

## Main files

- `cur_web_3_bot.py` — bot logic, state handling, Redis storage, and Telegram message handlers.
- `requirements.txt` — Python dependencies used by the project.
- `Procfile` — process definition for deployment platforms such as Heroku.

## Dependencies

This project uses:

- `pyTelegramBotAPI`
- `redis`

## Environment variables

The bot expects a Telegram token in the environment variable:

- `COURSERA_PY_WEB_3_LOCATION_BOT_TOKEN`

Redis is configured through:

- `REDIS_URL` (optional; defaults to `redis://localhost:6379`)

## Local run

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Set the Telegram bot token:

   ```bash
   export COURSERA_PY_WEB_3_LOCATION_BOT_TOKEN="YOUR_TOKEN"
   ```

3. Start Redis if needed.

4. Run the bot:

   ```bash
   python cur_web_3_bot.py
   ```

5. Tests 
   ```bash
   pytest --cov=source --cov-report=term-missing --cov-report=term ./tests/ -q
   ```
   ```bash
    python -m pytest ./tests/ -q
   ```


## Deployment

The project includes a `Procfile` for deploying the bot as a worker process:

```text
worker: python cur_web_3_bot.py
```

This is suitable for hosting platforms that run Python workers, such as Heroku.

## Notes

This repository is a small educational or prototype project demonstrating how to build a Telegram bot with a persistent backend, basic state management, and location storage using Redis.
