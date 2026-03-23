import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

API_TOKEN = os.getenv("BOT_TOKEN")

# 🔥 каналы (можешь менять названия)
-1003856582918: "🔥 ItsNightmare1337",
   -1003591733345: "🤝 killer_586",
}

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

db = sqlite3.connect("db.sqlite")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS giveaway (
    id INTEGER PRIMARY KEY,
    text TEXT,
    winners INTEGER,
    end_time TEXT
)
""")

db.commit()

giveaway_messages = []


# ======================
# КНОПКИ
# ======================
def join_kb():
    buttons = []

    for channel_id, name in CHANNELS.items():
        link = f"https://t.me/{str(channel_id).replace('-100','')}"
        buttons.append([
            InlineKeyboardButton(text=name, url=link)
        ])

    buttons.append([
        InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ======================
# ПРОВЕРКА ПОДПИСКИ
# ======================
async def is_subscribed(user_id: int):
    try:
        for channel_id in CHANNELS.keys():
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        return True
    except:
        return False


# ======================
# ВРЕМЯ
# ======================
def format_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


# ======================
# /start
# ======================
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Привет 👋")


# ======================
# GIVEAWAY
# ======================
@dp.message(F.text.startswith("/giveaway"))
async def giveaway(message: Message):
    try:
        args = message.text.split("|")

        text = args[1].strip()
        winners = int(args[2])
        minutes = int(args[3])

        end_time = datetime.now() + timedelta(minutes=minutes)

        cur.execute("DELETE FROM giveaway")
        cur.execute("DELETE FROM users")

        cur.execute(
            "INSERT INTO giveaway (text, winners, end_time) VALUES (?, ?, ?)",
            (text, winners, end_time.isoformat())
        )
        db.commit()

        global giveaway_messages
        giveaway_messages = []

        for channel in CHANNELS.keys():
            msg = await bot.send_message(
                chat_id=channel,
                text=f"""
🌙 <b>GIVEAWAY</b>

{text}

⏱ Осталось: ⏳
🏆 Победителей: {winners}
""",
                reply_markup=join_kb()
            )

            giveaway_messages.append((channel, msg.message_id))

        await message.answer("✅ Розыгрыш запущен")

    except Exception as e:
        await message.answer("Ошибка ❌")
        print(e)


# ======================
# JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(call: CallbackQuery):
    if not await is_subscribed(call.from_user.id):
        await call.answer("Подпишись на все каналы ❌", show_alert=True)
        return

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
    db.commit()

    await call.answer("Ты участвуешь 🎉", show_alert=True)


# ======================
# LOOP
# ======================
async def loop():
    while True:
        await asyncio.sleep(5)

        row = cur.execute("SELECT text, winners, end_time FROM giveaway").fetchone()

        if not row:
            continue

        text, winners, end_time = row
        end_time = datetime.fromisoformat(end_time)

        remaining = int((end_time - datetime.now()).total_seconds())

        # 🔥 анти-отписка
        users_db = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]
        valid_users = []

        for user_id in users_db:
            if await is_subscribed(user_id):
                valid_users.append(user_id)
            else:
                cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

        db.commit()

        count = len(valid_users)

        # обновление сообщений
        for channel, msg_id in giveaway_messages:
            try:
                await bot.edit_message_text(
                    chat_id=channel,
                    message_id=msg_id,
                    text=f"""
🌙 <b>GIVEAWAY</b>

{text}

⏱ Осталось: {format_time(max(0, remaining))}
👥 Участников: {count}
🏆 Победителей: {winners}
""",
                    reply_markup=join_kb()
                )
            except:
                pass

        # завершение
        if remaining <= 0:
            if valid_users:
                winners_list = random.sample(valid_users, min(len(valid_users), winners))

                result = "🏆 <b>ПОБЕДИТЕЛИ</b>\n\n" + "\n".join(
                    [f"<a href='tg://user?id={u}'>Пользователь</a>" for u in winners_list]
                )

                for channel in CHANNELS.keys():
                    await bot.send_message(channel, result)

            cur.execute("DELETE FROM giveaway")
            cur.execute("DELETE FROM users")
            db.commit()


# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
