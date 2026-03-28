import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

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

def get_channels():
    return {
        row[0]: {"name": row[1]}
        for row in cur.execute("SELECT * FROM channels").fetchall()
    }

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
# SUB CHECK
# ======================
async def check_sub(user_id):
    for cid in get_channels():
        try:
            member = await bot.get_chat_member(cid, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

# ======================
# KEYBOARDS
# ======================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Розыгрыш", callback_data="create")],
        [InlineKeyboardButton(text="➕ Канал", callback_data="add")]
    ])

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎉 Участвовать", callback_data="join")],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check")]
    ])

# ======================
# FORMAT
# ======================
def format_time(sec):
    m, s = divmod(sec, 60)
    return f"{m:02}:{s:02}"

def build_caption():
    if not giveaway["end"]:
        return ""

    remaining = int((giveaway["end"] - datetime.utcnow()).total_seconds())
    remaining = max(0, remaining)

    return (
        f"🎁 <b>РОЗЫГРЫШ</b>\n\n"
        f"{giveaway['text']}\n\n"
        f"👥 Участников: <b>{len(users)}</b>\n"
        f"⏳ Осталось: <b>{format_time(remaining)}</b>"
    )

# ======================
# START
# ======================
@dp.message(F.text == "/start")
async def start(m: Message, state: FSMContext):
    if m.from_user.id == ADMIN_ID:
        await state.clear()
        await m.answer("⚙️ Панель управления", reply_markup=main_kb())
    else:
        await m.answer("👋 Бот активен")

# ======================
# ADD CHANNEL
# ======================
@dp.callback_query(F.data == "add")
async def add(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.cid)
    await c.message.answer("ID канала:")

@dp.message(StateFilter(AddChannel.cid))
async def add2(m: Message, state: FSMContext):
    if not m.text.strip().lstrip("-").isdigit():
        return await m.answer("❌ Неверный ID")

    await state.update_data(cid=int(m.text))
    await state.set_state(AddChannel.name)
    await m.answer("Название:")

@dp.message(StateFilter(AddChannel.name))
async def add3(m: Message, state: FSMContext):
    data = await state.get_data()

    cur.execute("INSERT OR REPLACE INTO channels VALUES (?,?)",
                (data["cid"], m.text))
    db.commit()

    await state.clear()
    await m.answer("✅ Канал добавлен")

# ======================
# CREATE
# ======================
@dp.callback_query(F.data == "create")
async def create(c: CallbackQuery, state: FSMContext):
    if giveaway["active"]:
        return await c.answer("❌ Уже есть активный розыгрыш", show_alert=True)

    await state.set_state(Giveaway.text)
    await c.message.answer("Текст розыгрыша:")

@dp.message(StateFilter(Giveaway.text))
async def step1(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(Giveaway.winners)
    await m.answer("Кол-во победителей:")

@dp.message(StateFilter(Giveaway.winners))
async def step2(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Введите число")

    data = await state.get_data()

    giveaway["text"] = data["text"]
    giveaway["winners"] = int(m.text)
    giveaway["msgs"] = {}

    await state.clear()
    await m.answer("Время в минутах (например 5):")

@dp.message()
async def start_time(m: Message):
    if not giveaway["text"]:
        return

    if not m.text.isdigit():
        return

    if not get_channels():
        return await m.answer("❌ Нет каналов")

    minutes = int(m.text)

    giveaway["end"] = datetime.utcnow() + timedelta(minutes=minutes)
    giveaway["active"] = True
    users.clear()

    for cid in get_channels():
        try:
            msg = await bot.send_photo(
                cid,
                LOGO,
                caption=build_caption(),
                reply_markup=kb()
            )
            giveaway["msgs"][cid] = msg
        except:
            pass

    await m.answer("🚀 Запущено")

# ======================
# JOIN
# ======================
@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    if c.from_user.id in users:
        return await c.answer("⚠️ Уже участвуешь")

    if not await check_sub(c.from_user.id):
        return await c.answer("❌ Подпишись на каналы", show_alert=True)

    users.add(c.from_user.id)
    await c.answer("🎉 Ты участвуешь")

# ======================
# CHECK BUTTON
# ======================
@dp.callback_query(F.data == "check")
async def check_btn(c: CallbackQuery):
    if await check_sub(c.from_user.id):
        users.add(c.from_user.id)
        await c.answer("✅ Всё ок, ты участвуешь")
    else:
        await c.answer("❌ Подпишись на все каналы", show_alert=True)

# ======================
# UPDATE LOOP
# ======================
async def updater():
    while True:
        await asyncio.sleep(5)

        if not giveaway["active"]:
            continue

        text = build_caption()

        for cid, msg in giveaway["msgs"].items():
            try:
                await bot.edit_message_caption(
                    chat_id=cid,
                    message_id=msg.message_id,
                    caption=text,
                    reply_markup=kb()
                )
            except:
                continue

# ======================
# FINISH
# ======================
async def finish():
    if not users:
        text = "🏆 Нет участников"
    else:
        winners = random.sample(list(users), min(len(users), giveaway["winners"]))
        text = "🏆 ПОБЕДИТЕЛИ:\n\n" + "\n".join(
            [f"<a href='tg://user?id={u}'>Победитель</a>" for u in winners]
        )

    for cid in giveaway["msgs"]:
        try:
            await bot.send_message(cid, text)
        except:
            pass

    giveaway.update({
        "active": False,
        "end": None,
        "text": "",
        "winners": 0,
        "msgs": {}
    })

    users.clear()

# ======================
# TIMER
# ======================
async def timer():
    while True:
        await asyncio.sleep(2)

        if giveaway["active"] and datetime.utcnow() >= giveaway["end"]:
            await finish()

# ======================
# MAIN
# ======================
async def main():
    asyncio.create_task(timer())
    asyncio.create_task(updater())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
