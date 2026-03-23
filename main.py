import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ======================
TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 7468497968

LOGO = "AgACAgIAAxkBAAIBEmnBGRn8bTmeyYndGFAFwf3HNjg5AAL1FGsbHMMISofDqjxORKtwAQADAgADdwADOgQ"

CHANNELS = {
    -1003856582918: "ItsNightmare1337",
    -1003794532196: "killer_586",
}

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ======================
# DB
# ======================
db = sqlite3.connect("db.sqlite")
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# ======================
# STATE
# ======================
giveaway = {
    "msgs": {},
    "end": None,
    "text": "",
    "winners": 0,
    "active": False
}

# ======================
# FILE ID GETTER
# ======================
@dp.message(F.photo)
async def file_id(message: Message):
    await message.answer(message.photo[-1].file_id)

# ======================
# TEST
# ======================
@dp.message(F.text == "/test")
async def test(m):
    await m.answer("✅ Bot alive")

# ======================
# STATS
# ======================
@dp.message(F.text == "/stats")
async def stats(m):
    if m.from_user.id != ADMIN_ID:
        return

    users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    await m.answer(
        f"👥 Users: {users}\n📢 Channels: {len(CHANNELS)}\n🎁 Active: {giveaway['active']}"
    )

# ======================
# LINK
# ======================
def link(cid):
    return f"https://t.me/c/{str(cid)[4:]}"

# ======================
# KEYBOARD
# ======================
def kb():
    buttons = []

    for cid, name in CHANNELS.items():
        buttons.append([InlineKeyboardButton(text=name, url=link(cid))])

    buttons.append([InlineKeyboardButton(text="🎉 Join", callback_data="join")])
    buttons.append([InlineKeyboardButton(text="🔄 Check", callback_data="check")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ======================
# CHECK SUB
# ======================
async def check_sub(user_id):
    try:
        for cid in CHANNELS:
            m = await bot.get_chat_member(cid, user_id)
            if m.status not in ("member", "creator", "administrator"):
                return False
        return True
    except:
        return False

# ======================
# JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(c):
    if not await check_sub(c.from_user.id):
        return await c.answer("❌ No subscription", show_alert=True)

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
    db.commit()

    await c.answer("🎉 Joined")

# ======================
# CHECK
# ======================
@dp.callback_query(F.data == "check")
async def check(c):
    if await check_sub(c.from_user.id):
        cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
        db.commit()
        await c.answer("✅ OK")
    else:
        await c.answer("❌ Subscribe first", show_alert=True)

# ======================
# GIVEAWAY START
# ======================
@dp.message(F.text.startswith("/giveaway"))
async def giveaway_cmd(m):
    try:
        _, text, winners, minutes = m.text.split("|")

        winners = int(winners)
        minutes = int(minutes)

        giveaway["msgs"] = {}
        giveaway["text"] = text
        giveaway["winners"] = winners
        giveaway["end"] = datetime.now() + timedelta(minutes=minutes)
        giveaway["active"] = True

        cur.execute("DELETE FROM users")
        db.commit()

        caption = f"🎁 {text}\n⏳ Starting..."

        # SEND TO ALL CHANNELS
        for cid in CHANNELS:
            msg = await bot.send_photo(
                cid,
                LOGO,
                caption=caption,
                reply_markup=kb()
            )
            giveaway["msgs"][cid] = msg

        await m.answer("🚀 Giveaway started")

    except:
        await m.answer("❌ /giveaway|text|winners|minutes")

# ======================
# LIVE ENGINE (FIXED)
# ======================
async def live():
    while True:
        await asyncio.sleep(1)

        if not giveaway["active"]:
            continue

        remaining = int((giveaway["end"] - datetime.now()).total_seconds())

        if remaining <= 0:
            giveaway["active"] = False

            users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

            if users:
                winners = random.sample(users, min(len(users), giveaway["winners"]))

                text = "🏆 WINNERS:\n\n" + "\n".join(
                    [f"👤 <a href='tg://user?id={u}'>Winner</a>" for u in winners]
                )

                for cid in giveaway["msgs"]:
                    await bot.send_message(cid, text)

            cur.execute("DELETE FROM users")
            db.commit()
            continue

        users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        caption = f"""
🎁 <b>{giveaway['text']}</b>

⏱ Time: {remaining}s
👥 Users: {users_count}
🏆 Winners: {giveaway['winners']}
"""

        for cid, msg in giveaway["msgs"].items():
            try:
                await bot.edit_message_caption(
                    chat_id=cid,
                    message_id=msg.message_id,
                    caption=caption,
                    reply_markup=kb()
                )
            except:
                pass

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
