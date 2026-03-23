import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

TOKEN = os.getenv("BOT_TOKEN")

# 📸 LOGO (file_id вставишь сюда)
LOGO = ""

# 📢 КАНАЛЫ
CHANNELS = {
    -1001234567890: "🔥 Основной канал",
    -1009876543210: "🤝 Партнёр",
    -1001111111111: "📢 Новости"
}

bot = Bot(
    token=TOKEN,
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
db.commit()


# ======================
# LINK BUILDER
# ======================
def get_link(channel_id: int):
    return f"https://t.me/c/{str(channel_id)[4:]}"


# ======================
# KEYBOARD (ULTRA UI)
# ======================
def kb():
    buttons = []

    for cid, name in CHANNELS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {name}",
                url=get_link(cid)
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")
    ])

    buttons.append([
        InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")
    ])

    buttons.append([
        InlineKeyboardButton(
            text="📤 Поделиться",
            switch_inline_query="Я участвую в Nightbot Giveaway!"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ======================
# CHECK SUB
# ======================
async def is_subscribed(user_id: int):
    try:
        for cid in CHANNELS.keys():
            m = await bot.get_chat_member(cid, user_id)
            if m.status not in ("member", "administrator", "creator"):
                return False
        return True
    except:
        return False


# ======================
# JOIN (ANTI CHEAT)
# ======================
@dp.callback_query(F.data == "join")
async def join(call: CallbackQuery):
    if not await is_subscribed(call.from_user.id):
        await call.answer("❌ Сначала подпишись на каналы!", show_alert=True)
        return

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
    db.commit()

    await call.answer("🎉 Ты участвуешь!", show_alert=True)


# ======================
# CHECK BUTTON (ULTRA 3)
# ======================
@dp.callback_query(F.data == "check_sub")
async def check(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
        db.commit()

        await call.answer("✅ Подписка подтверждена!", show_alert=True)
    else:
        await call.answer("❌ Подпишись на все каналы!", show_alert=True)


# ======================
# GIVEAWAY STATE
# ======================
giveaway = {
    "msg": None,
    "end": None,
    "text": "",
    "winners": 0,
    "active": False
}


# ======================
# FORMAT TIME
# ======================
def format_time(s: int):
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    return f"{h:02}:{m:02}:{s:02}"


# ======================
# LIVE ENGINE
# ======================
async def live():
    while True:
        await asyncio.sleep(1)

        if not giveaway["active"]:
            continue

        remaining = int((giveaway["end"] - datetime.now()).total_seconds())
        if remaining < 0:
            remaining = 0

        users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        caption = f"""
🌙 <b>NIGHTBOT GIVEAWAY</b>
━━━━━━━━━━━━━━
🎁 <b>{giveaway['text']}</b>

⏱ Осталось: {format_time(remaining)}
👥 Участников: {users}
🏆 Победителей: {giveaway['winners']}

━━━━━━━━━━━━━━
🤖 Nightbot System
"""

        try:
            await bot.edit_message_caption(
                chat_id=giveaway["msg"].chat.id,
                message_id=giveaway["msg"].message_id,
                caption=caption,
                reply_markup=kb()
            )
        except:
            pass

        # FINISH
        if remaining <= 0:
            giveaway["active"] = False

            users_list = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

            if users_list:
                winners = random.sample(users_list, min(len(users_list), giveaway["winners"]))

                text = "🏆 <b>NIGHTBOT WINNERS</b>\n\n" + "\n".join(
                    [f"👤 <a href='tg://user?id={u}'>Winner</a>" for u in winners]
                )

                await bot.send_message(giveaway["msg"].chat.id, text)

            cur.execute("DELETE FROM users")
            db.commit()


# ======================
# GIVEAWAY START
# ======================
@dp.message(F.text.startswith("/giveaway"))
async def giveaway_cmd(message: Message):
    try:
        _, text, winners, minutes = message.text.split("|")

        winners = int(winners)
        minutes = int(minutes)

        end_time = datetime.now() + timedelta(minutes=minutes)

        cur.execute("DELETE FROM users")
        db.commit()

        msg = await message.answer_photo(
            photo=LOGO,
            caption="🌙 <b>NIGHTBOT</b>\n⏳ Загрузка...",
            reply_markup=kb()
        )

        giveaway.update({
            "msg": msg,
            "end": end_time,
            "text": text,
            "winners": winners,
            "active": True
        })

        await message.answer("🚀 Giveaway запущен")

    except Exception as e:
        await message.answer("❌ Ошибка")
        print(e)


# ======================
# START BOT
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

@dp.message(F.photo)
async def get_file_id(message: Message):
    file_id = message.photo[-1].file_id
    await message.answer(f"📸 FILE_ID:\n\n<code>{file_id}</code>")
