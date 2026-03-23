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

db = sqlite3.connect("db.sqlite")
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# ======================
# GIVEAWAY STATE
# ======================
giveaway = {
    "msgs": {},
    "end": None,
    "text": "",
    "winners": 0,
    "active": False,
    "last_winners": []
}

# ======================
# FILE ID
# ======================
@dp.message(F.photo)
async def file_id(message: Message):
    await message.answer(f"<code>{message.photo[-1].file_id}</code>")

# ======================
# UTIL
# ======================
def get_link(cid):
    return f"https://t.me/c/{str(cid)[4:]}"

def kb():
    buttons = []

    for cid, name in CHANNELS.items():
        buttons.append([InlineKeyboardButton(text=name, url=get_link(cid))])

    buttons.append([InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")])
    buttons.append([InlineKeyboardButton(text="🔄 Проверить", callback_data="check")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def is_sub(user_id):
    for cid in CHANNELS:
        m = await bot.get_chat_member(cid, user_id)
        if m.status not in ("member", "creator", "administrator"):
            return False
    return True

# ======================
# JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(call):
    if not await is_sub(call.from_user.id):
        return await call.answer("❌ Нет подписки", show_alert=True)

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
    db.commit()

    await call.answer("🎉 Участвуешь!")

# ======================
# CHECK
# ======================
@dp.callback_query(F.data == "check")
async def check(call):
    if await is_sub(call.from_user.id):
        cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (call.from_user.id,))
        db.commit()
        await call.answer("✅ ОК")
    else:
        await call.answer("❌ Подпишись", show_alert=True)

# ======================
# STATS (3)
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
# ADD CHANNEL (1)
# ======================
@dp.message(F.text.startswith("/addchannel"))
async def add_channel(m):
    if m.from_user.id != ADMIN_ID:
        return

    try:
        _, cid, name = m.text.split("|")
        CHANNELS[int(cid)] = name
        await m.answer("✅ Added")
    except:
        await m.answer("❌ /addchannel|id|name")

# ======================
# REMOVE CHANNEL (2)
# ======================
@dp.message(F.text.startswith("/removechannel"))
async def remove_channel(m):
    if m.from_user.id != ADMIN_ID:
        return

    try:
        _, cid = m.text.split("|")
        CHANNELS.pop(int(cid), None)
        await m.answer("🗑 Removed")
    except:
        await m.answer("❌ /removechannel|id")

# ======================
# END GIVEAWAY (4)
# ======================
@dp.message(F.text == "/end")
async def end(m):
    if m.from_user.id != ADMIN_ID:
        return

    giveaway["active"] = False
    await m.answer("⛔ Giveaway stopped")

# ======================
# REROLL (5)
# ======================
@dp.message(F.text == "/reroll")
async def reroll(m):
    if m.from_user.id != ADMIN_ID:
        return

    users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]
    if not users:
        return await m.answer("❌ No users")

    winners = random.sample(users, min(3, len(users)))
    giveaway["last_winners"] = winners

    text = "🎲 REROLL WINNERS:\n\n" + "\n".join(
        [f"👤 <a href='tg://user?id={u}'>Winner</a>" for u in winners]
    )

    await m.answer(text)

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

        for cid in CHANNELS:
            msg = await bot.send_photo(
                cid,
                LOGO,
                caption=f"🎁 {text}\n⏳ Loading...",
                reply_markup=kb()
            )
            giveaway["msgs"][cid] = msg

        await m.answer("🚀 Started")

    except:
        await m.answer("❌ /giveaway|text|winners|minutes")

# ======================
# LIVE LOOP
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

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
