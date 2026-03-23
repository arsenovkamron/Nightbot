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
#DB
# ======================
db = sqlite3.connect("db.sqlite")
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

# ======================
#STATE
# ======================
giveaway = {
    "active": False,
    "paused": False,
    "end": None,
    "text": "",
    "winners": 0,
    "msgs": {}
}

# ======================
#FILE ID
# ======================
@dp.message(F.photo)
async def file_id(m: Message):
    await m.answer(f"<code>{m.photo[-1].file_id}</code>")

# ======================
#FORMAT TIME
# ======================
def format_time(s: int):
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    return f"{h:02}ч {m:02}м {s:02}с"

# ======================
#KEYBOARD (FIXED v3)
# ======================
def kb():
    btn = []

    for cid, name in CHANNELS.items():
        btn.append([
            InlineKeyboardButton(
                text=f"📢 {name}",
                url=f"https://t.me/c/{str(cid)[4:]}"
            )
        ])

    btn.append([
        InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")
    ])

    btn.append([
        InlineKeyboardButton(text="🔄 Проверить", callback_data="check")
    ])

    btn.append([
        InlineKeyboardButton(
            text="📤 Поделиться",
            switch_inline_query="Я участвую в розыгрыше!"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=btn)

# ======================
#CHECK SUB
# ======================
async def sub(user_id: int):
    try:
        for cid in CHANNELS:
            m = await bot.get_chat_member(cid, user_id)
            if m.status not in ("member", "creator", "administrator"):
                return False
        return True
    except:
        return False

# ======================
#JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    if not await sub(c.from_user.id):
        return await c.answer("❌ Подпишись", show_alert=True)

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
    db.commit()
    await c.answer("🎉 Ты участвуешь!")

# ======================
#CHECK
# ======================
@dp.callback_query(F.data == "check")
async def check(c: CallbackQuery):
    if await sub(c.from_user.id):
        cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
        db.commit()
        await c.answer("✅ Ок")
    else:
        await c.answer("❌ Нет подписки", show_alert=True)

# ======================
#COMMANDS
# ======================
@dp.message(F.text == "/pause")
async def pause(m: Message):
    if m.from_user.id == ADMIN_ID:
        giveaway["paused"] = True
        await m.answer("⏸ Пауза")

@dp.message(F.text == "/resume")
async def resume(m: Message):
    if m.from_user.id == ADMIN_ID:
        giveaway["paused"] = False
        await m.answer("▶️ Продолжено")

@dp.message(F.text == "/end")
async def end(m: Message):
    if m.from_user.id == ADMIN_ID:
        giveaway["active"] = False
        await m.answer("⛔ Завершено")

@dp.message(F.text == "/reroll")
async def reroll(m: Message):
    if m.from_user.id != ADMIN_ID:
        return

    users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

    if users and giveaway["winners"] > 0:
        w = random.sample(users, min(len(users), giveaway["winners"]))
        text = "🏆 НОВЫЕ ПОБЕДИТЕЛИ:\n\n" + "\n".join(
            [f"👤 <a href='tg://user?id={u}'>Winner</a>" for u in w]
        )

        for cid in giveaway["msgs"]:
            await bot.send_message(cid, text)

# ======================
#GIVEAWAY START (SAFE)
# ======================
@dp.message(F.text.startswith("/giveaway"))
async def start(m: Message):
    try:
        _, text, winners, minutes = m.text.split("|")

        giveaway.update({
            "active": True,
            "paused": False,
            "text": text,
            "winners": int(winners),
            "end": datetime.now() + timedelta(minutes=int(minutes)),
            "msgs": {}
        })

        cur.execute("DELETE FROM users")
        db.commit()

        for cid in CHANNELS:
            msg = await bot.send_photo(
                cid,
                LOGO,
                caption="🎁 РОЗЫГРЫШ ЗАПУЩЕН",
                reply_markup=kb()
            )
            giveaway["msgs"][cid] = msg

        await m.answer("🚀 Запущено")

    except:
        await m.answer("❌ Формат: /giveaway|текст|победители|минуты")

# ======================
#LIVE ENGINE (FIXED)
# ======================
async def live():
    while True:
        await asyncio.sleep(1)

        if not giveaway["active"] or giveaway["paused"]:
            continue

        remaining = int((giveaway["end"] - datetime.now()).total_seconds())

        if remaining <= 0:
            giveaway["active"] = False

            users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

            if users and giveaway["winners"] > 0:
                w = random.sample(users, min(len(users), giveaway["winners"]))

                text = "🏆 ПОБЕДИТЕЛИ:\n\n" + "\n".join(
                    [f"👤 <a href='tg://user?id={u}'>Winner</a>" for u in w]
                )

                for cid in giveaway["msgs"]:
                    await bot.send_message(cid, text)

            cur.execute("DELETE FROM users")
            db.commit()
            continue

        users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        caption = (
            f"🎁 <b>{giveaway['text']}</b>\n\n"
            f"⏳ Таймер: {format_time(remaining)}\n"
            f"👥 Участники: {users_count}\n"
            f"🏆 Победителей: {giveaway['winners']}\n"
            f"{'⏸ ПАУЗА' if giveaway['paused'] else '🔥 ИДЁТ'}"
        )

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
#STATS
# ======================
@dp.message(F.text == "/stats")
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return

    users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    await m.answer(
        f"👥 Пользователи: {users}\n"
        f"📢 Каналы: {len(CHANNELS)}\n"
        f"🎁 Активен: {giveaway['active']}"
    )

# ======================
#MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
