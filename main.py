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
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не задан")

ADMIN_ID = 7468497968

LOGO = "AgACAgIAAxkBAAIBEmnBGRn8bTmeyYndGFAFwf3HNjg5AAL1FGsbHMMISofDqjxORKtwAQADAgADdwADOgQ"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ======================
# DB
# ======================
db = sqlite3.connect("db.sqlite")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

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
# GIVEAWAY STATE
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
# CHANNELS
# ======================
def get_channels():
    return {
        row[0]: {"name": row[1]}
        for row in cur.execute("SELECT * FROM channels").fetchall()
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
        [InlineKeyboardButton(text="🎁 Розыгрыш", callback_data="create")],
        [InlineKeyboardButton(text="➕ Канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="❌ Канал удалить", callback_data="del_channel")],
        [InlineKeyboardButton(text="📋 Каналы", callback_data="list_channels")]
    ])

def time_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("5 мин", callback_data="t_5"),
            InlineKeyboardButton("10 мин", callback_data="t_10")
        ],
        [
            InlineKeyboardButton("30 мин", callback_data="t_30"),
            InlineKeyboardButton("60 мин", callback_data="t_60")
        ]
    ])

def kb():
    btn = []

    channels = get_channels()

    for cid, data in channels.items():
        btn.append([
            InlineKeyboardButton(
                text=f"📢 {data['name']}",
                url=f"https://t.me/c/{str(cid)[4:]}"
            )
        ])

    btn.append([InlineKeyboardButton("🎉 Участвовать", callback_data="join")])
    btn.append([InlineKeyboardButton("🔄 Проверка", callback_data="check")])

    return InlineKeyboardMarkup(inline_keyboard=btn)

# ======================
# START
# ======================
@dp.message(F.text == "/start")
async def start(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("⚙️ Панель", reply_markup=main_kb())
    else:
        await m.answer("👋 Бот работает")

# ======================
# ADD CHANNEL
# ======================
@dp.callback_query(F.data == "add_channel")
async def add1(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.cid)
    await c.message.answer("📌 Введи ID канала")

@dp.message(AddChannel.cid)
async def add2(m: Message, state: FSMContext):
    try:
        cid = int(m.text)
    except:
        return await m.answer("❌ Ошибка ID")

    await state.update_data(cid=cid)
    await state.set_state(AddChannel.name)
    await m.answer("📌 Название канала")

@dp.message(AddChannel.name)
async def add3(m: Message, state: FSMContext):
    data = await state.get_data()

    cur.execute("INSERT OR REPLACE INTO channels VALUES (?,?)",
                (data["cid"], m.text))
    db.commit()

    await state.clear()
    await m.answer("✅ Канал добавлен")

# ======================
# DELETE CHANNELS
# ======================
@dp.callback_query(F.data == "del_channel")
async def del_menu(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return

    channels = get_channels()

    if not channels:
        return await c.message.answer("❌ Каналов нет")

    kb = [
        [InlineKeyboardButton(
            text=f"❌ {v['name']}",
            callback_data=f"del_{k}"
        )]
        for k, v in channels.items()
    ]

    await c.message.answer("Выбери канал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_"))
async def delete(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return

    cid = int(c.data.split("_")[1])

    cur.execute("DELETE FROM channels WHERE channel_id=?", (cid,))
    db.commit()

    await c.message.answer("🗑 Канал удалён")

# ======================
# LIST CHANNELS
# ======================
@dp.callback_query(F.data == "list_channels")
async def list_ch(c: CallbackQuery):
    channels = get_channels()

    if not channels:
        return await c.message.answer("❌ Пусто")

    text = "📋 Каналы:\n\n" + "\n".join(
        [f"• {v['name']} ({k})" for k, v in channels.items()]
    )

    await c.message.answer(text)

# ======================
# CREATE GIVEAWAY
# ======================
@dp.callback_query(F.data == "create")
async def create(c: CallbackQuery, state: FSMContext):
    await state.set_state(Giveaway.text)
    await c.message.answer("🎁 Текст приза")

@dp.message(Giveaway.text)
async def step1(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(Giveaway.winners)
    await m.answer("🏆 Победители")

@dp.message(Giveaway.winners)
async def step2(m: Message, state: FSMContext):
    try:
        w = int(m.text)
    except:
        return await m.answer("❌ число")

    data = await state.get_data()

    giveaway.update({
        "active": True,
        "paused": False,
        "text": data["text"],
        "winners": w,
        "end": None,
        "msgs": {}
    })

    await state.clear()
    await m.answer("⏱ Выбери время", reply_markup=time_kb())

# ======================
# TIME SELECT
# ======================
@dp.callback_query(F.data.startswith("t_"))
async def time_set(c: CallbackQuery):
    minutes = int(c.data.split("_")[1])

    giveaway["end"] = datetime.now() + timedelta(minutes=minutes)

    cur.execute("DELETE FROM users")
    db.commit()

    for cid in get_channels():
        msg = await bot.send_photo(cid, LOGO, caption="🎁 START", reply_markup=kb())
        giveaway["msgs"][cid] = msg

    await c.message.answer("🚀 Запущено")

# ======================
# JOIN CHECK
# ======================
async def check_sub(user_id):
    for cid in get_channels():
        try:
            m = await bot.get_chat_member(cid, user_id)
            if m.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    if not await check_sub(c.from_user.id):
        return await c.answer("❌ Подпишись", show_alert=True)

    cur.execute("INSERT OR IGNORE INTO users VALUES (?)", (c.from_user.id,))
    db.commit()

    await c.answer("🎉 участвуешь")

# ======================
# LIVE ENGINE
# ======================
async def live():
    last = ""

    while True:
        await asyncio.sleep(1)

        if not giveaway["active"] or not giveaway["end"]:
            continue

        remaining = int((giveaway["end"] - datetime.now()).total_seconds())

        if remaining <= 0:
            giveaway["active"] = False

            users = [u[0] for u in cur.execute("SELECT user_id FROM users").fetchall()]

            if users:
                w = random.sample(users, min(len(users), giveaway["winners"]))
                text = "\n".join([f"<a href='tg://user?id={u}'>Winner</a>" for u in w])

                for cid in giveaway["msgs"]:
                    await bot.send_message(cid, f"🏆 Победители:\n{text}")

            cur.execute("DELETE FROM users")
            db.commit()
            continue

        count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        cap = f"🎁 {giveaway['text']}\n⏳ {format_time(remaining)}\n👥 {count}"

        if cap == last:
            continue
        last = cap

        for cid, msg in giveaway["msgs"].items():
            try:
                await bot.edit_message_caption(cid, msg.message_id, cap, reply_markup=kb())
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
