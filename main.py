import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ======================
# CONFIG
# ======================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ Укажи BOT_TOKEN")

ADMIN_ID = 7468497968

LOGO = "AgACAgIAAxkBAAIBEmnBGRn8bTmeyYndGFAFwf3HNjg5AAL1FGsbHMMISofDqjxORKtwAQADAgADdwADOgQ"

CHANNELS = {
    -1003856582918: {"ItsNightmare1337": "ItsNightmare1337"},
    -1003794532196: {"killer_586": "killer_586"},
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
# FSM
# ======================
class CreateGiveaway(StatesGroup):
    text = State()
    winners = State()
    time = State()

# ======================
# STATE
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
# TIME FORMAT
# ======================
def format_time(s):
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    return f"{h:02}ч {m:02}м {s:02}с"

# ======================
# KEYBOARDS
# ======================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Создать розыгрыш", callback_data="create")]
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def kb():
    btn = []

    for cid, data in CHANNELS.items():
        btn.append([
            InlineKeyboardButton(
                text=f"📢 {data['name']}",
                url=f"https://t.me/c/{str(cid)[4:]}"
            )
        ])

    btn.append([InlineKeyboardButton(text="🎉 Участвовать", callback_data="join")])
    btn.append([InlineKeyboardButton(text="🔄 Проверить", callback_data="check")])

    return InlineKeyboardMarkup(inline_keyboard=btn)

# ======================
# START
# ======================
@dp.message(F.text == "/start")
async def start(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("👋 Панель управления", reply_markup=main_kb())
    else:
        await m.answer("👋 Бот работает")

# ======================
# FILE ID
# ======================
@dp.message(F.photo)
async def file_id(m: Message):
    await m.answer(f"<code>{m.photo[-1].file_id}</code>")

# ======================
# CREATE FLOW
# ======================
@dp.callback_query(F.data == "create")
async def create(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return
    await state.set_state(CreateGiveaway.text)
    await c.message.answer("✍️ Введи текст приза:", reply_markup=cancel_kb())

@dp.message(CreateGiveaway.text)
async def step1(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(CreateGiveaway.winners)
    await m.answer("🏆 Сколько победителей?")

@dp.message(CreateGiveaway.winners)
async def step2(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Введи число")
    await state.update_data(winners=int(m.text))
    await state.set_state(CreateGiveaway.time)
    await m.answer("⏱ Сколько минут?")

@dp.message(CreateGiveaway.time)
async def step3(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Введи число")

    data = await state.get_data()

    giveaway.update({
        "active": True,
        "paused": False,
        "text": data["text"],
        "winners": data["winners"],
        "end": datetime.now() + timedelta(minutes=int(m.text)),
        "msgs": {}
    })

    cur.execute("DELETE FROM users")
    db.commit()

    for cid in CHANNELS:
        msg = await bot.send_photo(
            cid,
            LOGO,
            caption="🎁 <b>РОЗЫГРЫШ ЗАПУЩЕН</b>",
            reply_markup=kb()
        )
        giveaway["msgs"][cid] = msg

    await state.clear()
    await m.answer("🚀 Розыгрыш запущен")

@dp.callback_query(F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("❌ Отменено")

# ======================
# JOIN / CHECK
# ======================
@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
    db.commit()
    await c.answer("🎉 Ты участвуешь!")

@dp.callback_query(F.data == "check")
async def check(c: CallbackQuery):
    await c.answer("✅ Проверено")

# ======================
# LIVE ENGINE (УЛЬТРА СТАБИЛЬНЫЙ)
# ======================
async def live():
    last_text = ""

    while True:
        await asyncio.sleep(1)

        try:
            if not giveaway["active"] or giveaway["paused"]:
                continue

            remaining = int((giveaway["end"] - datetime.now()).total_seconds())

            if remaining <= 0:
                giveaway["active"] = False

                users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

                if users:
                    winners = random.sample(users, min(len(users), giveaway["winners"]))

                    text = "🏆 <b>ПОБЕДИТЕЛИ</b>\n\n" + "\n".join(
                        [f"<a href='tg://user?id={u}'>Winner</a>" for u in winners]
                    )

                    for cid in giveaway["msgs"]:
                        await bot.send_message(cid, text)

                cur.execute("DELETE FROM users")
                db.commit()
                continue

            users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

            caption = (
                f"🎁 <b>{giveaway['text']}</b>\n\n"
                f"⏳ {format_time(remaining)}\n"
                f"👥 {users_count} участников\n"
                f"🏆 {giveaway['winners']} победителей"
            )

            if caption == last_text:
                continue

            last_text = caption

            for cid, msg in giveaway["msgs"].items():
                try:
                    await bot.edit_message_caption(
                        chat_id=cid,
                        message_id=msg.message_id,
                        caption=caption,
                        reply_markup=kb()
                    )
                except Exception as e:
                    if "message is not modified" in str(e):
                        continue

        except Exception as e:
            print("LOOP ERROR:", e)

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
