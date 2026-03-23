import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")

# 🔥 список каналов через запятую
CHANNELS = list(map(int, os.getenv("CHANNELS", "").split(",")))

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

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
# КНОПКА
# ======================
def join_kb():
    buttons = []

    for channel in CHANNELS:
        link = f"https://t.me/{str(channel).replace('-100','')}"
        buttons.append([InlineKeyboardButton(text="📢 Подписаться", url=link)])

    buttons.append([InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ======================
# ПРОВЕРКА ПОДПИСКИ
# ======================
async def is_subscribed(user_id: int):
    try:
        for channel in CHANNELS:
            member = await bot.get_chat_member(channel, user_id)
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
# СТАРТ
# ======================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    await msg.answer("Привет 👋")


# ======================
# СОЗДАНИЕ РОЗЫГРЫША
# ======================
@dp.message_handler(commands=["giveaway"])
async def giveaway(msg: types.Message):
    try:
        args = msg.text.split("|")

        text = args[1]
        winners = int(args[2])
        minutes = int(args[3])

        end_time = datetime.now() + timedelta(minutes=minutes)

        cur.execute("DELETE FROM giveaway")
        cur.execute(
            "INSERT INTO giveaway (text, winners, end_time) VALUES (?, ?, ?)",
            (text, winners, end_time.isoformat())
        )
        db.commit()

        global giveaway_messages
        giveaway_messages = []

        # отправка во все каналы
        for channel in CHANNELS:
            m = await bot.send_message(
                channel,
                f"""
🌙 <b>GIVEAWAY</b>

{text}

⏱ Осталось: ⏳
🏆 Победителей: {winners}
""",
                reply_markup=join_kb()
            )

            giveaway_messages.append((channel, m.message_id))

        await msg.answer("✅ Розыгрыш запущен")

    except Exception as e:
        await msg.answer("Ошибка ❌")
        print(e)


# ======================
# УЧАСТИЕ
# ======================
@dp.callback_query_handler(lambda c: c.data == "join")
async def join(call: types.CallbackQuery):
    if not await is_subscribed(call.from_user.id):
        await call.answer("Подпишись на все каналы ❌", show_alert=True)
        return

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
    db.commit()

    await call.answer("Ты участвуешь 🎉", show_alert=True)


# ======================
# ОБНОВЛЕНИЕ
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

        count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        # обновление сообщений
        for channel, msg_id in giveaway_messages:
            try:
                await bot.edit_message_text(
                    f"""
🌙 <b>GIVEAWAY</b>

{text}

⏱ Осталось: {format_time(max(0, remaining))}
👥 Участников: {count}
🏆 Победителей: {winners}
""",
                    channel,
                    msg_id,
                    reply_markup=join_kb()
                )
            except:
                pass

        # завершение
        if remaining <= 0:
            users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

            if users:
                import random
                winners_list = random.sample(users, min(len(users), winners))

                text_win = "🏆 <b>ПОБЕДИТЕЛИ</b>\n\n" + "\n".join(
                    [f"<a href='tg://user?id={u}'>Пользователь</a>" for u in winners_list]
                )

                for channel in CHANNELS:
                    await bot.send_message(channel, text_win)

            cur.execute("DELETE FROM giveaway")
            cur.execute("DELETE FROM users")
            db.commit()


# ======================
# ЗАПУСК
# ======================
if __name__ == "__main__":
    loop_task = asyncio.get_event_loop().create_task(loop())
    executor.start_polling(dp, skip_updates=True)
