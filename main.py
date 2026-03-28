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
    return {row[0]: {"name": row[1]} for row in cur.execute("SELECT * FROM channels").fetchall()}

# ======================
# FSM
class Giveaway(StatesGroup):
    text = State()
    winners = State()
    time = State()

class AddChannel(StatesGroup):
    wait_forward = State()

# ======================
# STATE
giveaway = {
    "active": False,
    "end": None,
    "text": "",
    "winners": 0,
    "msgs": {},
    "channels": []
}
users = set()

# ======================
# SUB CHECK
async def check_sub(user_id):
    for cid in get_channels():
        try:
            member = await bot.get_chat_member(cid, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            print(f"Sub check error for {cid}: {e}")
            return False
    return True

# ======================
# KEYBOARDS
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎁 Розыгрыш", callback_data="create")],
        [InlineKeyboardButton("➕ Добавить канал", callback_data="add")],
        [InlineKeyboardButton("📋 Список каналов", callback_data="list")]
    ])

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎉 Участвовать", callback_data="join")],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check")]
    ])

def channels_kb():
    kb = []
    for cid, data in get_channels().items():
        kb.append([InlineKeyboardButton(f"{data['name']} ({cid})", callback_data=f"del_{cid}")])
    return InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

# ======================
# FORMAT
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
@dp.message(F.text == "/start")
async def start(m: Message, state: FSMContext):
    if m.from_user.id == ADMIN_ID:
        await state.clear()
        await m.answer("⚙️ Панель управления", reply_markup=main_kb())
    else:
        await m.answer("👋 Бот активен")

# ======================
# ADD CHANNEL
@dp.callback_query(F.data == "add")
async def add(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.wait_forward)
    await c.message.answer("📩 Перешли сюда любой пост из канала")

@dp.message(StateFilter(AddChannel.wait_forward))
async def add_channel(m: Message, state: FSMContext):
    if not m.forward_from_chat:
        return await m.answer("❌ Перешли сообщение именно из канала")
    chat = m.forward_from_chat
    if chat.type != "channel":
        return await m.answer("❌ Это не канал")
    cid = chat.id
    name = chat.title
    try:
        cur.execute("INSERT OR REPLACE INTO channels VALUES (?,?)", (cid, name))
        db.commit()
        await bot.send_message(cid, "✅ Бот подключен к каналу")
    except Exception as e:
        return await m.answer(f"❌ Ошибка: {e}")
    await state.clear()
    await m.answer(f"✅ Канал добавлен:\n{name}\n<code>{cid}</code>")

# ======================
# LIST CHANNELS
@dp.callback_query(F.data == "list")
async def list_channels(c: CallbackQuery):
    ch = get_channels()
    if not ch:
        return await c.message.answer("❌ Нет каналов")
    kb = channels_kb()
    await c.message.answer("📋 Подключенные каналы:", reply_markup=kb)

# ======================
# DELETE CHANNEL
@dp.callback_query(F.data.startswith("del_"))
async def del_channel(c: CallbackQuery):
    cid = int(c.data.split("_")[1])
    cur.execute("DELETE FROM channels WHERE channel_id = ?", (cid,))
    db.commit()
    await c.answer("✅ Канал удален", show_alert=True)
    kb = channels_kb()
    text = "📋 Подключенные каналы:" if get_channels() else "❌ Нет каналов"
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except:
        pass

# ======================
# CREATE GIVEAWAY
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
    await state.set_state(Giveaway.time)
    await m.answer("Время розыгрыша в минутах:")

@dp.message(StateFilter(Giveaway.time))
async def start_giveaway(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Введите число минут")
    if not get_channels():
        return await m.answer("❌ Нет каналов")
    minutes = int(m.text)
    giveaway["end"] = datetime.utcnow() + timedelta(minutes=minutes)
    giveaway["active"] = True
    users.clear()
    giveaway["channels"] = list(get_channels().keys())
    for cid in giveaway["channels"]:
        try:
            msg = await bot.send_photo(
                cid,
                LOGO,
                caption=build_caption(),
                reply_markup=kb()
            )
            giveaway["msgs"][cid] = msg
        except Exception as e:
            print(f"ERROR sending to {cid}: {e}")
    await state.clear()
    await m.answer("🚀 Розыгрыш запущен")

# ======================
# JOIN
@dp.callback_query(F.data == "join")
async def join(c: CallbackQuery):
    if c.from_user.id in users:
        return await c.answer("⚠️ Уже участвуешь")
    if not await check_sub(c.from_user.id):
        return await c.answer("❌ Подпишись на все каналы", show_alert=True)
    users.add(c.from_user.id)
    await c.answer("🎉 Ты участвуешь")

# ======================
# CHECK BUTTON
@dp.callback_query(F.data == "check")
async def check_btn(c: CallbackQuery):
    if await check_sub(c.from_user.id):
        users.add(c.from_user.id)
        await c.answer("✅ Всё ок, ты участвуешь")
    else:
        await c.answer("❌ Подпишись на все каналы", show_alert=True)

# ======================
# UPDATE LOOP (1 сек)
async def updater():
    while True:
        await asyncio.sleep(1)
        if not giveaway["active"]:
            continue
        text = build_caption()
        for cid, msg in giveaway["msgs"].items():
            try:
                await bot.edit_message_caption(chat_id=cid, message_id=msg.message_id, caption=text, reply_markup=kb())
            except Exception:
                continue

# ======================
# FINISH
async def finish():
    if not users:
        text = "🏆 Нет участников"
    else:
        winners = random.sample(list(users), min(len(users), giveaway["winners"]))
        text = "🏆 ПОБЕДИТЕЛИ:\n\n" + "\n".join([f"<a href='tg://user?id={u}'>Победитель</a>" for u in winners])
    for cid in giveaway["msgs"]:
        try:
            await bot.send_message(cid, text)
        except Exception:
            continue
    giveaway.update({"active": False, "end": None, "text": "", "winners": 0, "msgs": {}, "channels": []})
    users.clear()

# ======================
# TIMER
async def timer():
    while True:
        await asyncio.sleep(1)
        if giveaway["active"] and datetime.utcnow() >= giveaway["end"]:
            await finish()

# ======================
# MAIN
async def main():
    asyncio.create_task(timer())
    asyncio.create_task(updater())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
