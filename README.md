# BET88 — The Football Challenge

A traditional Telegram bot built with Python 3.14, python-telegram-bot, and PostgreSQL. It runs with Telegram long polling as a Render Background Worker. It is not a Mini App.

## Features

- Football multiple-choice quiz
- Guess the Player
- Guess the Club
- Daily football challenge (one completion per user per day)
- Global points leaderboard
- Player profiles and statistics
- Admin-only question command

All points are non-monetary entertainment points. There are no bets, odds, deposits, withdrawals, casino games, or gambling features.

## Deploy on Render

1. Create a PostgreSQL database on Render.
2. Create a **Background Worker** and connect this repository.
3. Set the build command to `pip install -r requirements.txt`.
4. Set the start command to `python bot.py`.
5. Set the following environment variables:
   - `BOT_TOKEN`: token from BotFather
   - `DATABASE_URL`: Render PostgreSQL **Internal Database URL** (use the external URL only if connecting from outside Render)
   - `ADMIN_IDS`: comma-separated Telegram numeric user IDs allowed to use `/addquestion`
   - `PYTHON_VERSION`: `3.14` (also pinned in `.python-version`)
6. Deploy. The worker starts polling Telegram automatically.

The repository includes `render.yaml` as a deployment blueprint. If you use it, provide the secret environment variables in the Render dashboard when prompted. A Background Worker is appropriate because this bot uses polling and does not need a public web server.

## Commands

- `/start` — main menu
- `/play` — football quiz
- `/player` — guess the mystery player
- `/club` — guess the mystery club
- `/daily` — daily challenge
- `/leaderboard` — global rankings
- `/profile` — your stats
- `/help` — command guide
- `/addquestion` — admin-only question entry

Admin question format:

```
/addquestion Question? | Option A | Option B | Option C | Option D | correct option (1-4) | Category
```

## Notes

- Never commit your Telegram bot token or database credentials.
- The database tables are created automatically on first startup.
- The starter question and guessing datasets live in `bot.py`. Expand and review the question bank before public launch.
