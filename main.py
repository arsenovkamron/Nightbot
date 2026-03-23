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
from aiogram.filters import StateFilter

# ======================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7468497968
LOGO = "AgACAgIAAxkBAAIBEmnBGRn8bTmeyYndGFAFwf3HNjg5AAL1FGsbHMMISofDqjxORKtwAQADAgADdwADOgQ"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ======================
# DB
# ======================
db = sqlite3.connect("db.sqlite", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS channels (
    channel_id INTEGER PRIMARY KEY,
    name TEXT
)
""")
db.commit()

# ======================
# FSM
# ======================
class Giveaway(StatesGroup):
    text = State()
    winners = State()

class AddChannel(StatesGroup):
    cid = State()
    name = State()

# ======================
# STATE
# ======================
giveaway = {
    "active": False,
    "end": None,
    "text": "",
    "winners": 0,
    "msgs": {}
}

users = set()

# ======================
# DB
# ======================
def get_channels():
    return {
        row[0]: {"name": row[1]}
        for row in cur.execute("SELECT * FROM channels").fetchall()
    }

# ======================
# KEYBOARDS
# ======================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Розыгрыш", callback_data="create")],
        [InlineKeyboardButton(text="➕ Канал", callback_data="add")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data="del")],
        [InlineKeyboardButton(text="📋 Каналы", callback_data="list")]
    ])

def time_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("1", callback_data="t_1"),
            InlineKeyboardButton("2", callback_data="t_2"),
            InlineKeyboardButton("4", callback_data="t_4"),
            InlineKeyboardButton("5", callback_data="t_5")
        ],
        [
            InlineKeyboardButton("10", callback_data="t_10"),
            InlineKeyboardButton("15", callback_data="t_15"),
            InlineKeyboardButton("20", callback_data="t_20")
        ]
    ])

def kb():
    btn = [
        [InlineKeyboardButton("🎉 Участвовать", callback_data="join")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=btn)

# ======================
# START
# ======================
@dp.message(F.text == "/start")
async def start(m: Message, state: FSMContext):
    if m.from_user.id == ADMIN_ID:
        await state.clear()  # 🔥 ВАЖНО: не ломаем FSM
        await m.answer("⚙️ Панель управления", reply_markup=main_kb())
    else:
        await m.answer("👋 Бот активен")

# ======================
# ADD CHANNEL
# ======================
@dp.callback_query(F.data == "add")
async def add(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.cid)
    await c.message.answer("📌 ID канала:")

@dp.message(StateFilter(AddChannel.cid))
async def add2(m: Message, state: FSMContext):
    if not m.text.strip().lstrip("-").isdigit():
        return await m.answer("❌ Неверный ID")

    await state.update_data(cid=int(m.text))
    await state.set_state(AddChannel.name)
    await m.answer("📌 Название:")

@dp.message(StateFilter(AddChannel.name))
async def add3(m: Message, state: FSMContext):
    data = await state.get_data()

    cur.execute("INSERT OR REPLACE INTO channels VALUES (?,?)",
                (data["cid"], m.text))
    db.commit()

    await state.clear()
    await m.answer("✅ Канал добавлен")

# ======================
# GIVEAWAY STEP 1
# ======================
@dp.callback_query(F.data == "create")
async def create(c: CallbackQuery, state: FSMContext):
    await state.set_state(Giveaway.text)
    await c.message.answer("🎁 Текст розыгрыша:")

@dp.message(StateFilter(Giveaway.text))
async def step1(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(Giveaway.winners)
    await m.answer("🏆 Кол-во победителей:")

# ======================
# STEP 2 FIXED
# ======================
@dp.message(StateFilter(Giveaway.winners))
async def step2(m: Message, state: FSMContext):
    text = m.text.strip()

    if not text.isdigit():
        return await m.answer("❌ Введите ТОЛЬКО число")

    winners = max(1, int(text))
    data = await state.get_data()

    giveaway["text"] = data["text"]
    giveaway["winners"] = winners
    giveaway["msgs"] = {}
    giveaway["active"] = False
    giveaway["end"] = None

    await state.clear()
    await m.answer("⏱ Выберите время", reply_markup=time_kb())

# ======================
# START TIME
# ======================
@dp.callback_query(F.data.startswith("t_"))
async def start_time(c: CallbackQuery):
    await c.answer()

    minutes = int(c.data.split("_")[1])

    giveaway["end"] = datetime.now() + timedelta(minutes=minutes)
    giveaway["active"] = True
    users.clear()

    for cid in get_channels():
        try:
            msg = await bot.send_photo(cid, LOGO, caption="🎁 РОЗЫГРЫШ", reply_markup=kb())
            giveaway["msgs"][cid] = msg
        except:
            pass

    await c.message.answer("🚀 Розыгрыш запущен")

# ======================
# JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    users.add(c.from_user.id)
    await c.answer("🎉 Участвуешь")

# ======================
# FINISH
# ======================
async def finish():
    user_list = list(users)

    if user_list and giveaway["winners"]:
        winners = random.sample(user_list, min(len(user_list), giveaway["winners"]))
        text = "🏆 ПОБЕДИТЕЛИ:\n\n" + "\n".join(
            [f"<a href='tg://user?id={u}'>Winner</a>" for u in winners]
        )
    else:
        text = "🏆 Нет участников"

    for cid in giveaway["msgs"]:
        try:
            await bot.send_message(cid, text)
        except:
            pass

    giveaway["active"] = False
    giveaway["end"] = None
    giveaway["msgs"] = {}
    giveaway["text"] = ""
    giveaway["winners"] = 0

    users.clear()

# ======================
# LIVE LOOP SAFE
# ======================
async def live():
    while True:
        await asyncio.sleep(2)

        if not giveaway["active"] or not giveaway["end"]:
            continue

        remaining = int((giveaway["end"] - datetime.now()).total_seconds())

        if remaining <= 0:
            await finish()
            continue

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
