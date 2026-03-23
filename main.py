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
if not TOKEN:
    raise ValueError("BOT_TOKEN не задан")

ADMIN_ID = 7468497968

LOGO = "AgACAgIAAxkBAAIBEmnBGRn8bTmeyYndGFAFwf3HNjg5AAL1FGsbHMMISofDqjxORKtwAQADAgADdwADOgQ"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ======================
# DB (только для каналов)
# ======================
db = sqlite3.connect("db.sqlite", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY, name TEXT)")
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
# STATE (главное состояние)
# ======================
giveaway = {
    "active": False,
    "end": None,
    "text": "",
    "winners": 0,
    "msgs": {}
}

# 👇 КЕШ пользователей (ОЧЕНЬ ВАЖНО)
users = set()

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
def format_time(sec: int):
    sec = max(0, sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}ч {m:02}м {s:02}с"

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
        ],
        [
            InlineKeyboardButton("30", callback_data="t_30"),
            InlineKeyboardButton("45", callback_data="t_45"),
            InlineKeyboardButton("60", callback_data="t_60"),
            InlineKeyboardButton("90", callback_data="t_90")
        ]
    ])

def kb():
    btn = []

    for cid, data in get_channels().items():
        btn.append([
            InlineKeyboardButton(
                text=f"📢 {data['name']}",
                url=f"https://t.me/c/{str(cid)[4:]}"
            )
        ])

    btn.append([InlineKeyboardButton("🎉 Участвовать", callback_data="join")])
    return InlineKeyboardMarkup(inline_keyboard=btn)

# ======================
# START
# ======================
@dp.message(F.text == "/start")
async def start(m: Message):
    if m.from_user.id == ADMIN_ID:
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
    try:
        cid = int(m.text)
    except:
        return await m.answer("❌ Неверный ID")

    await state.update_data(cid=cid)
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
# DELETE CHANNEL
# ======================
@dp.callback_query(F.data == "del")
async def del_menu(c: CallbackQuery):
    ch = get_channels()

    kb = [
        [InlineKeyboardButton(f"❌ {v['name']}", callback_data=f"del_{k}")]
        for k, v in ch.items()
    ]

    await c.message.answer("Выберите:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_"))
async def delete(c: CallbackQuery):
    cid = int(c.data.split("_")[1])
    cur.execute("DELETE FROM channels WHERE channel_id=?", (cid,))
    db.commit()
    await c.message.answer("🗑 Удалено")

# ======================
# LIST CHANNELS
# ======================
@dp.callback_query(F.data == "list")
async def list_ch(c: CallbackQuery):
    ch = get_channels()
    text = "📋 Каналы:\n\n" + "\n".join([f"{v['name']} ({k})" for k, v in ch.items()])
    await c.message.answer(text)

# ======================
# GIVEAWAY CREATE
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

@dp.message(StateFilter(Giveaway.winners))
async def step2(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Введите число")

    w = max(1, int(m.text))
    data = await state.get_data()

    giveaway.update({
        "text": data["text"],
        "winners": w,
        "msgs": {},
        "active": False,
        "end": None
    })

    await state.clear()
    await m.answer("⏱ Выберите время", reply_markup=time_kb())

# ======================
# START TIME
# ======================
@dp.callback_query(F.data.startswith("t_"))
async def start_time(c: CallbackQuery):
    global users

    minutes = int(c.data.split("_")[1])

    giveaway["end"] = datetime.now() + timedelta(minutes=minutes)
    giveaway["active"] = True

    users.clear()

    for cid in get_channels():
        msg = await bot.send_photo(cid, LOGO, caption="🎁 РОЗЫГРЫШ", reply_markup=kb())
        giveaway["msgs"][cid] = msg

    await c.message.answer("🚀 Розыгрыш запущен")

# ======================
# JOIN
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
    global users

    if not await check_sub(c.from_user.id):
        return await c.answer("❌ Подпишись", show_alert=True)

    users.add(c.from_user.id)
    await c.answer("🎉 Участвуешь")

# ======================
# FINISH GIVEAWAY
# ======================
async def finish():
    global giveaway, users

    user_list = list(users)

    if user_list and giveaway["winners"] > 0:
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

    giveaway = {
        "active": False,
        "end": None,
        "text": "",
        "winners": 0,
        "msgs": {}
    }

    users.clear()

# ======================
# STABLE LOOP (НЕ ЛОМАЕТСЯ)
# ======================
async def live():
    while True:
        await asyncio.sleep(2)

        if not giveaway["active"] or not giveaway["end"]:
            continue

        try:
            remaining = int((giveaway["end"] - datetime.now()).total_seconds())

            if remaining <= 0:
                await finish()
                continue

            text = f"🎁 {giveaway['text']}\n⏳ {format_time(remaining)}\n👥 {len(users)}"

            for cid, msg in list(giveaway["msgs"].items()):
                try:
                    await bot.edit_message_caption(
                        chat_id=cid,
                        message_id=msg.message_id,
                        caption=text,
                        reply_markup=kb()
                    )
                except:
                    pass

        except Exception as e:
            print("LIVE ERROR:", e)

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(live())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
