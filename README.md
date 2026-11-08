# BET88 — The Football Challenge

A traditional Telegram football entertainment bot built with Python 3.14 and python-telegram-bot. It runs using Telegram long polling as a Render Background Worker. It is not a Mini App and does not require a database.

## Features

- Football multiple-choice quiz
- Guess the Player
- Guess the Club
- Daily football challenge
- Global points leaderboard
- Player profiles and statistics
- Optional admin question entry

All points are non-monetary entertainment points. There are no bets, odds, deposits, withdrawals, casino games, or gambling features.

## Deploy on Render

1. Create a **Background Worker** connected to this repository.
2. Set the build command to `pip install -r requirements.txt`.
3. Set the start command to `python bot.py`.
4. Add one environment variable:
   - `BOT_TOKEN`: token from BotFather
5. Deploy. The worker starts polling Telegram automatically.

Python 3.14 is selected by `.python-version`. No PostgreSQL database or `DATABASE_URL` is required.

## Commands

- `/start` — main menu
- `/play` — football quiz
- `/player` — guess the mystery player
- `/club` — guess the mystery club
- `/daily` — daily challenge
- `/leaderboard` — global rankings
- `/profile` — your stats
- `/facts` — a football fact
- `/help` — command guide
- `/addquestion` — optional admin-only question entry

Admin question format:

```
/addquestion Question? | Option A | Option B | Option C | Option D | correct option (1-4) | Category
```

To enable `/addquestion`, optionally set `ADMIN_IDS` to a comma-separated list of numeric Telegram user IDs. It is not needed to run the bot.

## Storage note

The bot saves scores, daily completions, and custom questions to a local JSON file. No database setup is needed. Render's default filesystem is ephemeral, so local saved data may be lost when the service is redeployed or its instance is replaced. The bot itself continues to work without any database.
