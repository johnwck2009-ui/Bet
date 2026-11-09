import json
import logging
import os
import random
from datetime import date
from html import escape
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO"),
)
log = logging.getLogger("bet88")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATA_FILE = Path(os.getenv("DATA_FILE", "bet88_data.json"))
ADMIN_IDS = {
    int(value.strip()) for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

QUESTIONS = [
    ("Which country won the 2022 FIFA World Cup?", ["France", "Argentina", "Brazil", "Germany"], 1, "World Cup"),
    ("Which club plays its home matches at Anfield?", ["Chelsea", "Liverpool", "Arsenal", "Everton"], 1, "Clubs"),
    ("Who is known as 'The King of Football'?", ["Diego Maradona", "Pelé", "Zinedine Zidane", "Johan Cruyff"], 1, "Legends"),
    ("How many players does one team have on the pitch at the start of a standard match?", ["10", "11", "12", "9"], 1, "Rules"),
    ("Which country hosted the 2014 FIFA World Cup?", ["South Africa", "Russia", "Brazil", "Germany"], 2, "World Cup"),
    ("Which club is nicknamed 'The Old Lady'?", ["AC Milan", "Juventus", "Inter", "Roma"], 1, "Clubs"),
    ("What is the maximum number of substitutions normally allowed in many top-level competitions under current rules?", ["3", "4", "5", "6"], 2, "Rules"),
    ("Which nation has won the most men's FIFA World Cups?", ["Germany", "Italy", "Argentina", "Brazil"], 3, "World Cup"),
    ("Which stadium is associated with Real Madrid?", ["Camp Nou", "Santiago Bernabéu", "Wembley", "San Siro"], 1, "Stadiums"),
    ("Which position traditionally wears a different-coloured shirt?", ["Striker", "Goalkeeper", "Centre-back", "Winger"], 1, "Rules"),
    ("Which country won UEFA Euro 2016?", ["France", "Portugal", "Spain", "Italy"], 1, "International"),
    ("Which club is based in Munich?", ["Borussia Dortmund", "Bayern Munich", "RB Leipzig", "Bayer Leverkusen"], 1, "Clubs"),
    ("What is the name of the award given to the top scorer at a FIFA World Cup?", ["Golden Glove", "Golden Boot", "Golden Ball", "Fair Play Award"], 1, "Awards"),
    ("Which country is famous for the nickname 'La Albiceleste'?", ["Uruguay", "Argentina", "Chile", "Mexico"], 1, "International"),
    ("Which English club is known as 'The Gunners'?", ["Tottenham", "Arsenal", "Newcastle", "West Ham"], 1, "Clubs"),
    ("How long is a standard football match, excluding added time and extra time?", ["80 minutes", "90 minutes", "100 minutes", "120 minutes"], 1, "Rules"),
    ("Which nation won the 2010 FIFA World Cup?", ["Netherlands", "Germany", "Spain", "Brazil"], 2, "World Cup"),
    ("Which Italian city is home to both AC Milan and Inter?", ["Rome", "Turin", "Milan", "Naples"], 2, "Clubs"),
    ("What colour card means a player is sent off?", ["Yellow", "Blue", "Red", "Green"], 2, "Rules"),
    ("Which competition is contested by top European club teams?", ["Copa América", "UEFA Champions League", "AFCON", "Asian Cup"], 1, "Competitions"),
]

PLAYERS = [
    ("I am an Argentine forward. I won the 2022 World Cup and spent many years at Barcelona.", "Lionel Messi"),
    ("I am a Portuguese forward famous for my athleticism and multiple Ballon d'Or awards.", "Cristiano Ronaldo"),
    ("I am a Brazilian legend nicknamed O Rei, and I won three World Cups.", "Pelé"),
    ("I am a French midfielder who scored twice in the 1998 World Cup final.", "Zinedine Zidane"),
    ("I am an Egyptian forward known for my time at Liverpool.", "Mohamed Salah"),
    ("I am a Norwegian striker who became known for prolific scoring at Manchester City.", "Erling Haaland"),
]

FOOTBALL_FACTS = [
    "The first FIFA World Cup was held in Uruguay in 1930.",
    "A standard football pitch is rectangular, but its exact dimensions can vary within the Laws of the Game.",
    "The UEFA Champions League was previously known as the European Champion Clubs’ Cup.",
    "The penalty spot is 11 metres (12 yards) from the goal line.",
    "The FIFA World Cup trophy introduced in 1974 replaced the Jules Rimet Trophy.",
    "A standard match has two halves of 45 minutes each, before added time.",
    "The offside law does not apply directly from a goal kick, throw-in or corner kick.",
    "The first Women’s World Cup organised by FIFA took place in 1991 in China.",
]

CLUBS = [
    ("My home is Anfield. My supporters sing 'You'll Never Walk Alone'.", "Liverpool"),
    ("I play at the Santiago Bernabéu and have a record number of European Cups.", "Real Madrid"),
    ("My home is the Emirates Stadium in north London.", "Arsenal"),
    ("I am based in Munich and play at the Allianz Arena.", "Bayern Munich"),
    ("My home ground is Old Trafford and my nickname is the Red Devils.", "Manchester United"),
]

# Simple local storage: no PostgreSQL or external database is required.
state = {"users": {}, "daily_completions": [], "custom_questions": []}


def save_state():
    try:
        temporary_file = DATA_FILE.with_suffix(".tmp")
        temporary_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        temporary_file.replace(DATA_FILE)
    except OSError:
        log.exception("Could not save local bot data")


def load_state():
    global state
    try:
        if DATA_FILE.exists():
            loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state["users"].update(loaded.get("users", {}))
                state["daily_completions"] = loaded.get("daily_completions", [])
                state["custom_questions"] = loaded.get("custom_questions", [])
                for item in state["custom_questions"]:
                    QUESTIONS.append((
                        item["prompt"], item["options"],
                        int(item["answer"]), item["category"],
                    ))
    except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError):
        log.exception("Could not load local bot data; starting with fresh data")


def ensure_user(user):
    key = str(user.id)
    name = user.full_name or user.username or "Football fan"
    if key not in state["users"]:
        state["users"][key] = {
            "username": user.username,
            "full_name": name,
            "points": 0,
            "correct_answers": 0,
            "games_played": 0,
        }
    else:
        state["users"][key]["username"] = user.username
        state["users"][key]["full_name"] = name
    save_state()


def add_points(user_id, points):
    user = state["users"].setdefault(str(user_id), {
        "username": None, "full_name": "Football fan",
        "points": 0, "correct_answers": 0, "games_played": 0,
    })
    user["points"] += points
    user["correct_answers"] += 1
    save_state()


def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 ចូលប្រើសេវាកម្ម", url="https://t.me/WIN365KH1BOT?start=telegram")],
        [InlineKeyboardButton("⚽ Play Quiz", callback_data="quiz"),
         InlineKeyboardButton("🕵️ Guess Player", callback_data="player")],
        [InlineKeyboardButton("🏟 Guess Club", callback_data="club"),
         InlineKeyboardButton("📅 Daily Challenge", callback_data="daily")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
         InlineKeyboardButton("👤 My Profile", callback_data="profile")],
        [InlineKeyboardButton("💡 Football Facts", callback_data="facts")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.effective_message.reply_text(
        "សូមស្វាគមន៍មកវេបសាយធំបំផុត ងាយស្រួលលេង📲 និងគួរឱ្យទុកចិត្តបំផុតនៅកម្ពុជា🔥សេវាកម្ម២៤ម៉ោង",
        reply_markup=home_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "<b>BET88 COMMANDS</b>\n"
        "/start — Open the main menu\n/play — Start a football quiz\n"
        "/player — Guess the mystery player\n/club — Guess the mystery club\n"
        "/daily — Take today's challenge\n/leaderboard — View top players\n"
        "/profile — View your stats\n/facts — Get a football fact\n/help — Show this guide\n\n"
        "BET88 is a football entertainment game. Points are for fun only.",
        parse_mode=ParseMode.HTML, reply_markup=home_keyboard(),
    )


async def show_profile(message, user_id):
    row = state["users"].get(str(user_id))
    if not row:
        await message.reply_text("Your profile is not ready yet. Send /start first.")
        return
    await message.reply_text(
        f"👤 <b>{escape(row['full_name'])}</b>\n"
        f"⭐ Points: <b>{row['points']}</b>\n"
        f"✅ Correct answers: <b>{row['correct_answers']}</b>\n"
        f"🎮 Quiz questions answered: <b>{row['games_played']}</b>",
        parse_mode=ParseMode.HTML,
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await show_profile(update.effective_message, update.effective_user.id)


async def leaderboard_message(message):
    rows = sorted(
        state["users"].values(),
        key=lambda item: (item["points"], item["correct_answers"]),
        reverse=True,
    )[:10]
    if not rows:
        await message.reply_text("The leaderboard is waiting for its first challenger!")
        return
    lines = ["🏆 <b>BET88 GLOBAL LEADERBOARD</b>", ""]
    medals = ["🥇", "🥈", "🥉"]
    for index, row in enumerate(rows, 1):
        medal = medals[index - 1] if index <= 3 else f"{index}."
        lines.append(f"{medal} {escape(row['full_name'])} — <b>{row['points']}</b> pts")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await leaderboard_message(update.effective_message)


async def facts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "💡 <b>FOOTBALL FACT</b>\n\n" + random.choice(FOOTBALL_FACTS),
        parse_mode=ParseMode.HTML,
    )


async def send_quiz(message, context, daily=False):
    if daily:
        index = date.today().toordinal() % len(QUESTIONS)
        question = QUESTIONS[index]
        context_key = "daily"
    else:
        question = random.choice(QUESTIONS)
        context_key = "quiz"
    prompt, options, answer, category = question
    context.user_data[context_key] = {
        "answer": answer,
        "question": prompt,
        "daily": daily,
        "challenge_date": date.today().isoformat() if daily else None,
    }
    buttons = [
        [InlineKeyboardButton(f"{chr(65+i)}. {option}", callback_data=f"answer:{context_key}:{i}")]
        for i, option in enumerate(options)
    ]
    buttons.append([InlineKeyboardButton("🏠 Main menu", callback_data="home")])
    title = "📅 <b>DAILY CHALLENGE</b>\n" if daily else "⚽ <b>FOOTBALL QUIZ</b>\n"
    await message.reply_text(
        title + f"<b>{escape(prompt)}</b>\n\nCategory: {escape(category)}",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons),
    )


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await send_quiz(update.effective_message, context)


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    today = date.today().isoformat()
    if f"{update.effective_user.id}:{today}" in state["daily_completions"]:
        await update.effective_message.reply_text(
            "You have already completed today's challenge. Come back tomorrow! ⚽"
        )
        return
    await send_quiz(update.effective_message, context, daily=True)


async def guess_game(message, context, kind):
    options = PLAYERS if kind == "player" else CLUBS
    clue, answer = random.choice(options)
    context.user_data[f"guess:{kind}"] = {
        "answer": answer.casefold(), "display": answer,
    }
    await message.reply_text(
        ("🕵️ <b>GUESS THE PLAYER</b>\n" if kind == "player" else "🏟 <b>GUESS THE CLUB</b>\n")
        + escape(clue) + "\n\nSend your answer as a message. You have one attempt.",
        parse_mode=ParseMode.HTML,
    )


async def player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await guess_game(update.effective_message, context, "player")


async def club(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await guess_game(update.effective_message, context, "club")


async def text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for kind in ("player", "club"):
        key = f"guess:{kind}"
        game = context.user_data.get(key)
        if game:
            context.user_data.pop(key, None)
            if update.effective_message.text.strip().casefold() == game["answer"]:
                add_points(user_id, 15)
                await update.effective_message.reply_text(
                    f"🎉 Correct! It was {game['display']}. You earned 15 points."
                )
            else:
                await update.effective_message.reply_text(
                    f"Not quite! The answer was {game['display']}. Try another round."
                )
            return


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    ensure_user(user)

    if data == "home":
        await query.message.reply_text(
            "⚽ <b>BET88 — THE FOOTBALL CHALLENGE</b>",
            parse_mode=ParseMode.HTML, reply_markup=home_keyboard(),
        )
    elif data == "help":
        await help_command(update, context)
    elif data == "quiz":
        await send_quiz(query.message, context)
    elif data == "daily":
        today = date.today().isoformat()
        if f"{user.id}:{today}" in state["daily_completions"]:
            await query.message.reply_text(
                "You have already completed today's challenge. Come back tomorrow!"
            )
        else:
            await send_quiz(query.message, context, daily=True)
    elif data in ("player", "club"):
        await guess_game(query.message, context, data)
    elif data == "profile":
        await show_profile(query.message, user.id)
    elif data == "leaderboard":
        await leaderboard_message(query.message)
    elif data == "facts":
        await query.message.reply_text(
            "💡 <b>FOOTBALL FACT</b>\n\n" + random.choice(FOOTBALL_FACTS),
            parse_mode=ParseMode.HTML,
        )
    elif data.startswith("answer:"):
        _, key, selected_text = data.split(":", 2)
        selected = int(selected_text)
        game = context.user_data.get(key)
        if not game:
            await query.message.reply_text(
                "That question has expired. Start a new game with /play."
            )
            return
        context.user_data.pop(key, None)
        if selected == game["answer"]:
            points = 25 if game["daily"] else 10
            add_points(user.id, points)
            if game["daily"]:
                completion = f"{user.id}:{game['challenge_date']}"
                if completion not in state["daily_completions"]:
                    state["daily_completions"].append(completion)
            await query.message.reply_text(
                f"✅ Correct! +{points} points. Keep it up! ⚽"
            )
        else:
            await query.message.reply_text(
                "❌ Not quite! Better luck on the next question."
            )
        row = state["users"][str(user.id)]
        row["games_played"] += 1
        save_state()
        await query.message.reply_text(
            "What would you like to do next?", reply_markup=home_keyboard()
        )


async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_IDS:
        await update.effective_message.reply_text(
            "Admin question management is disabled. The bot can run without an admin ID."
        )
        return
    if update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text(
            "This command is for bot administrators only."
        )
        return
    raw = " ".join(context.args)
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) != 7:
        await update.effective_message.reply_text(
            "Usage:\n/addquestion Question? | Option A | Option B | Option C | Option D | correct option (1-4) | Category"
        )
        return
    question, *rest = parts
    options = rest[:4]
    try:
        answer = int(rest[4]) - 1
        if answer not in range(4):
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Correct option must be a number from 1 to 4."
        )
        return
    category = rest[5]
    item = {
        "prompt": question, "options": options,
        "answer": answer, "category": category,
    }
    state["custom_questions"].append(item)
    QUESTIONS.append((question, options, answer, category))
    save_state()
    await update.effective_message.reply_text(
        "✅ Question added to the bot's local question bank."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add your Telegram bot token to Render environment variables."
        )

    load_state()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["play", "quiz"], play))
    application.add_handler(CommandHandler("player", player))
    application.add_handler(CommandHandler("club", club))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("facts", facts))
    application.add_handler(CommandHandler("addquestion", add_question))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer))

    log.info("Starting BET88 using Telegram polling (local JSON storage)...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
