import asyncio
import logging
import os
import random
from datetime import date
from html import escape

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
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
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_IDS = {
    int(value.strip()) for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}
pool: AsyncConnectionPool | None = None

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

def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚽ Play Quiz", callback_data="quiz"),
         InlineKeyboardButton("🕵️ Guess Player", callback_data="player")],
        [InlineKeyboardButton("🏟 Guess Club", callback_data="club"),
         InlineKeyboardButton("📅 Daily Challenge", callback_data="daily")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
         InlineKeyboardButton("👤 My Profile", callback_data="profile")],
        [InlineKeyboardButton("💡 Football Facts", callback_data="facts")],
        [InlineKeyboardButton("💡 Football Facts", callback_data="facts")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])

async def db_execute(query, params=(), fetch=False):
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params)
            if fetch:
                return await cur.fetchall()
            return cur.rowcount

async def ensure_user(user):
    name = user.full_name or user.username or "Football fan"
    await db_execute(
        """INSERT INTO users (user_id, username, full_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE SET
             username = EXCLUDED.username, full_name = EXCLUDED.full_name""",
        (user.id, user.username, name),
    )

async def add_points(user_id, points):
    await db_execute(
        "UPDATE users SET points = points + %s, correct_answers = correct_answers + 1 WHERE user_id = %s",
        (points, user_id),
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await update.message.reply_text(
        "⚽ <b>WELCOME TO BET88</b>\n"
        "<i>THE FOOTBALL CHALLENGE</i>\n\n"
        "Your football knowledge is about to be tested. Play trivia, identify legendary players, "
        "guess clubs and take on the daily challenge. Earn points and climb the global leaderboard.\n\n"
        "Ready to prove how well you know the beautiful game?",
        parse_mode=ParseMode.HTML, reply_markup=home_keyboard(),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>BET88 COMMANDS</b>\n"
        "/start — Open the main menu\n/play — Start a football quiz\n"
        "/player — Guess the mystery player\n/club — Guess the mystery club\n"
        "/daily — Take today's challenge\n/leaderboard — View top players\n"
        "/profile — View your stats\n/facts — Get a football fact\n/help — Show this guide\n\n"
        "BET88 is a football entertainment game. Points are for fun only.",
        parse_mode=ParseMode.HTML, reply_markup=home_keyboard(),
    )

async def show_profile(message, user_id):
    rows = await db_execute(
        "SELECT full_name, points, correct_answers, games_played FROM users WHERE user_id=%s",
        (user_id,), fetch=True,
    )
    row = rows[0] if rows else None
    if not row:
        await message.reply_text("Your profile is not ready yet. Send /start first.")
        return
    await message.reply_text(
        f"👤 <b>{escape(row['full_name'])}</b>\n"
        f"⭐ Points: <b>{row['points']}</b>\n"
        f"✅ Correct answers: <b>{row['correct_answers']}</b>\n"
        f"🎮 Quizzes played: <b>{row['games_played']}</b>",
        parse_mode=ParseMode.HTML,
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await show_profile(update.effective_message, update.effective_user.id)

async def leaderboard_message(message):
    rows = await db_execute(
        "SELECT full_name, points FROM users ORDER BY points DESC, correct_answers DESC LIMIT 10",
        fetch=True,
    )
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
    await update.effective_message.reply_text("💡 <b>FOOTBALL FACT</b>\\n\\n" + random.choice(FOOTBALL_FACTS), parse_mode=ParseMode.HTML)

async def send_quiz(message, user_id, context, daily=False):
    if daily:
        index = date.today().toordinal() % len(QUESTIONS)
        question = QUESTIONS[index]
        context_key = "daily"
    else:
        question = random.choice(QUESTIONS)
        context_key = "quiz"
    prompt, options, answer, category = question
    # The question index and answer are stored in the user's Telegram session.
    context.user_data[context_key] = {"answer": answer, "question": prompt, "daily": daily, "challenge_date": date.today().isoformat() if daily else None}
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
    await ensure_user(update.effective_user)
    await send_quiz(update.effective_message, update.effective_user.id, context)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    today = date.today().isoformat()
    done = await db_execute(
        "SELECT 1 FROM daily_completions WHERE user_id=%s AND challenge_date=%s",
        (update.effective_user.id, today), fetch=True,
    )
    if done:
        await update.effective_message.reply_text("You have already completed today's challenge. Come back tomorrow! ⚽")
        return
    await send_quiz(update.effective_message, update.effective_user.id, context, daily=True)

async def guess_game(message, user_id, context, kind):
    options = PLAYERS if kind == "player" else CLUBS
    clue, answer = random.choice(options)
    context.user_data[f"guess:{kind}"] = {"answer": answer.casefold(), "display": answer}
    await message.reply_text(
        ("🕵️ <b>GUESS THE PLAYER</b>\n" if kind == "player" else "🏟 <b>GUESS THE CLUB</b>\n")
        + escape(clue) + "\n\nSend your answer as a message. You have one attempt.",
        parse_mode=ParseMode.HTML,
    )

async def player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await guess_game(update.effective_message, update.effective_user.id, context, "player")

async def club(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update.effective_user)
    await guess_game(update.effective_message, update.effective_user.id, context, "club")

async def text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for kind in ("player", "club"):
        key = f"guess:{kind}"
        game = context.user_data.get(key)
        if game:
            context.user_data.pop(key, None)
            if update.message.text.strip().casefold() == game["answer"]:
                await add_points(user_id, 15)
                await update.message.reply_text(f"🎉 Correct! It was {game['display']}. You earned 15 points.")
            else:
                await update.message.reply_text(f"Not quite! The answer was {game['display']}. Try another round.")
            return

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    await ensure_user(user)
    if data == "home":
        await query.message.reply_text("⚽ <b>BET88 — THE FOOTBALL CHALLENGE</b>", parse_mode=ParseMode.HTML, reply_markup=home_keyboard())
    elif data == "help":
        await query.message.reply_text(
            "/play — Football quiz\n/player — Guess the player\n/club — Guess the club\n"
            "/daily — Daily challenge\n/leaderboard — Rankings\n/profile — Your stats",
            reply_markup=home_keyboard(),
        )
    elif data == "quiz":
        await send_quiz(query.message, user.id, context)
    elif data == "daily":
        today = date.today().isoformat()
        done = await db_execute("SELECT 1 FROM daily_completions WHERE user_id=%s AND challenge_date=%s", (user.id, today), fetch=True)
        if done:
            await query.message.reply_text("You have already completed today's challenge. Come back tomorrow!")
        else:
            await send_quiz(query.message, user.id, context, daily=True)
    elif data in ("player", "club"):
        await guess_game(query.message, user.id, context, data)
    elif data == "profile":
        await show_profile(query.message, user.id)
    elif data == "leaderboard":
        await leaderboard_message(query.message)
    elif data == "facts":
        await query.message.reply_text("💡 <b>FOOTBALL FACT</b>\\n\\n" + random.choice(FOOTBALL_FACTS), parse_mode=ParseMode.HTML)
    elif data.startswith("answer:"):
        _, key, selected_text = data.split(":", 2)
        selected = int(selected_text)
        game = context.user_data.get(key)
        if not game:
            await query.message.reply_text("That question has expired. Start a new game with /play.")
            return
        context.user_data.pop(key, None)
        if selected == game["answer"]:
            points = 25 if game["daily"] else 10
            await add_points(user.id, points)
            if game["daily"]:
                await db_execute(
                    "INSERT INTO daily_completions (user_id, challenge_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user.id, game["challenge_date"]),
                )
            await query.message.reply_text(f"✅ Correct! +{points} points. Keep it up! ⚽")
        else:
            await query.message.reply_text("❌ Not quite! Better luck on the next question.")
        await db_execute("UPDATE users SET games_played=games_played+1 WHERE user_id=%s", (user.id,))
        await query.message.reply_text("What would you like to do next?", reply_markup=home_keyboard())

async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("This command is for bot administrators only.")
        return
    # Usage: /addquestion Question | option A | option B | option C | option D | correct option (1-4) | category
    raw = " ".join(context.args)
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) != 7:
        await update.message.reply_text(
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
        await update.message.reply_text("Correct option must be a number from 1 to 4.")
        return
    category = rest[5]
    await db_execute("INSERT INTO custom_questions (prompt, options, answer, category) VALUES (%s, %s, %s, %s)", (question, options, answer, category))
    QUESTIONS.append((question, options, answer, category))
    await update.message.reply_text("✅ Question saved. It will remain available after bot restarts.")

async def post_init(application: Application):
    global pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Add a Render PostgreSQL connection string.")
    pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False)
    await pool.open()
    await db_execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            correct_answers INTEGER NOT NULL DEFAULT 0,
            games_played INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db_execute("""
        CREATE TABLE IF NOT EXISTS daily_completions (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            challenge_date DATE NOT NULL,
            PRIMARY KEY (user_id, challenge_date)
        )
    """)
    await db_execute("""
        CREATE TABLE IF NOT EXISTS custom_questions (
            id BIGSERIAL PRIMARY KEY,
            prompt TEXT NOT NULL,
            options TEXT[] NOT NULL,
            answer INTEGER NOT NULL CHECK (answer BETWEEN 0 AND 3),
            category TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    saved_questions = await db_execute(
        "SELECT prompt, options, answer, category FROM custom_questions ORDER BY id", fetch=True
    )
    QUESTIONS.extend((row["prompt"], row["options"], row["answer"], row["category"]) for row in saved_questions)
    log.info("BET88 bot is ready. Database connection established.")

async def post_shutdown(application: Application):
    if pool:
        await pool.close()

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add your Telegram bot token to Render environment variables.")
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler(["help"], help_command))
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
    log.info("Starting BET88 using Telegram polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
