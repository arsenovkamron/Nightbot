import asyncio
import random
import time
import logging
import os
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------- CONFIG ----------------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

giveaway_msg_id = None
pending = {}


# ---------------- DB ----------------
async def init_db():
    async with aiosqlite.connect("db.sqlite3") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            user_id INTEGER PRIMARY KEY
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS giveaway (
            id INTEGER PRIMARY KEY,
            end_time INTEGER,
            winners INTEGER,
            text TEXT,
            photo TEXT
        )
        """)
        await db.commit()


# ---------------- UI ----------------
def join_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")]
    ])


def format_time(sec):
    sec = max(0, sec)
    h, m = divmod(sec, 3600)
    m, s = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------------- START ----------------
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("""
🌙 <b>Nightbot</b>

🤖 Добро пожаловать!

Я управляю розыгрышами на канале @ItsNightmare1337.
Меня создал @arsen_kamron.

⚡ Участвуй в постах и выигрывай призы!
""")


# ---------------- PANEL ----------------
@dp.message(F.text == "/panel")
async def panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("""
🌑 <b>Night Control Panel</b>

Команды:
/start_giveaway <сек> <победители>
/status
""")


# ---------------- STATUS ----------------
@dp.message(F.text == "/status")
async def status(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("""
📊 <b>Nightbot Status</b>

🟢 Online
⚙️ System: aiogram v3
💾 DB: SQLite
🌙 Brand: Nightbot
""")


# ---------------- START GIVEAWAY ----------------
@dp.message(F.text.startswith("/start_giveaway"))
async def start_giveaway(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split()
    if len(args) != 3:
        return await message.answer("Формат: /start_giveaway 60 3")

    pending["duration"] = int(args[1])
    pending["winners"] = int(args[2])

    await message.answer("📸 Отправь фото")


# ---------------- PHOTO ----------------
@dp.message(F.photo)
async def photo(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if "duration" not in pending:
        return

    pending["photo"] = message.photo[-1].file_id
    await message.answer("📝 Отправь текст")


# ---------------- TEXT ----------------
@dp.message(F.text)
async def text(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if "photo" not in pending:
        return

    pending["text"] = message.text
    await create_giveaway()


# ---------------- CREATE GIVEAWAY ----------------
async def create_giveaway():
    global giveaway_msg_id

    data = pending
    end_time = int(time.time()) + data["duration"]

    async with aiosqlite.connect("db.sqlite3") as db:
        await db.execute("DELETE FROM giveaway")
        await db.execute(
            "INSERT INTO giveaway VALUES (1, ?, ?, ?, ?)",
            (end_time, data["winners"], data["text"], data["photo"])
        )
        await db.commit()

    msg = await bot.send_photo(
        CHANNEL_ID,
        data["photo"],
        caption=f"""
🌙 <b>NIGHT GIVEAWAY</b>

📝 {data['text']}
⏱ Осталось: ⏳
🏆 Победителей: {data['winners']}
""",
        reply_markup=join_kb()
    )

    giveaway_msg_id = msg.message_id
    pending.clear()


# ---------------- JOIN ----------------
async def is_subscribed(user_id: int):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False


@dp.callback_query(F.data == "join")
async def join(call: CallbackQuery):
    if not await is_subscribed(call.from_user.id):
        return await call.answer("❌ Подпишись на канал!", show_alert=True)

    async with aiosqlite.connect("db.sqlite3") as db:
        await db.execute(
            "INSERT OR IGNORE INTO participants VALUES (?)",
            (call.from_user.id,)
        )
        await db.commit()

    await call.answer("✅ Ты в розыгрыше!")


# ---------------- LOOP ----------------
async def loop():
    global giveaway_msg_id

    while True:
        try:
            now = int(time.time())

            async with aiosqlite.connect("db.sqlite3") as db:
                cur = await db.execute("SELECT end_time, winners, text FROM giveaway WHERE id=1")
                row = await cur.fetchone()

                if row and giveaway_msg_id:
                    end, winners, text = row
                    remaining = end - now

                    cur = await db.execute("SELECT COUNT(*) FROM participants")
                    count = (await cur.fetchone())[0]

                    if remaining > 0:
                        try:
                            await bot.edit_message_caption(
                                CHANNEL_ID,
                                giveaway_msg_id,
                                caption=f"""
🌙 <b>NIGHT GIVEAWAY</b>

📝 {text}
⏱ Осталось: {format_time(remaining)}
👥 Участников: {count}
🏆 Победителей: {winners}
"""
                            )
                        except:
                            pass

                    else:
                        cur = await db.execute("SELECT user_id FROM participants")
                        users = [u[0] for u in await cur.fetchall()]

                        if users:
                            win = random.sample(users, min(len(users), winners))
                            await bot.send_message(
                                CHANNEL_ID,
                                "🏆 <b>WINNERS</b>\n\n" + "\n".join(map(str, win))
                            )
                        else:
                            await bot.send_message(CHANNEL_ID, "❌ Нет участников")

                        await db.execute("DELETE FROM giveaway")
                        await db.execute("DELETE FROM participants")
                        await db.commit()

                        giveaway_msg_id = None

            await asyncio.sleep(5)

        except Exception as e:
            logging.error(e)
            await asyncio.sleep(5)


# ---------------- MAIN ----------------
async def main():
    await init_db()
    asyncio.create_task(loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
