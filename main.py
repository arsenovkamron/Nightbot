import asyncio
import html
import logging
import os
import random
import time

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


DB_PATH = "db.sqlite3"
CAPTION_PREFIX = "🎁 <b>Розыгрыш</b>"
UPDATE_INTERVAL = 5


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задана обязательная переменная окружения {name}")
    return value


TOKEN = require_env("BOT_TOKEN")
ADMIN_ID = int(require_env("ADMIN_ID"))
CHANNEL_ID = int(require_env("CHANNEL_ID"))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
pending: dict[int, dict] = {}


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                winners_count INTEGER NOT NULL,
                text TEXT NOT NULL,
                photo_file_id TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT NOT NULL,
                joined_at INTEGER NOT NULL,
                PRIMARY KEY (giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
            )
            """
        )
        await db.commit()


def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def join_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Участвовать", callback_data=f"join:{giveaway_id}")]
        ]
    )


def format_time_left(seconds: int) -> str:
    seconds = max(0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_caption(text: str, winners_count: int, participants_count: int, seconds_left: int) -> str:
    safe_text = html.escape(text)
    return (
        f"{CAPTION_PREFIX}\n\n"
        f"📝 {safe_text}\n"
        f"⏱ Осталось: {format_time_left(seconds_left)}\n"
        f"👥 Участников: {participants_count}\n"
        f"🏆 Победителей: {winners_count}\n\n"
        f"Нажми кнопку ниже, чтобы участвовать."
    )


async def get_active_giveaway() -> tuple | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, message_id, end_time, winners_count, text, photo_file_id
            FROM giveaways
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return await cursor.fetchone()


async def get_participants_count(giveaway_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def finish_giveaway(giveaway_id: int, winners_count: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, username, full_name
            FROM participants
            WHERE giveaway_id = ?
            ORDER BY joined_at ASC
            """,
            (giveaway_id,),
        )
        participants = await cursor.fetchall()

        await db.execute(
            "UPDATE giveaways SET is_active = 0 WHERE id = ?",
            (giveaway_id,),
        )
        await db.commit()

    if participants:
        winners = random.sample(participants, min(len(participants), winners_count))
        winner_lines = []
        for index, (user_id, username, full_name) in enumerate(winners, start=1):
            if username:
                mention = f"@{html.escape(username)}"
            else:
                mention = f'<a href="tg://user?id={user_id}">{html.escape(full_name)}</a>'
            winner_lines.append(f"{index}. {mention}")

        result_text = "🏆 <b>Победители розыгрыша</b>\n\n" + "\n".join(winner_lines)
    else:
        result_text = "❌ <b>Розыгрыш завершён</b>\n\nУчастников не было."

    await bot.send_message(CHANNEL_ID, result_text)


async def refresh_giveaway_message(giveaway: tuple) -> None:
    giveaway_id, message_id, end_time, winners_count, text, _photo_file_id = giveaway
    participants_count = await get_participants_count(giveaway_id)
    seconds_left = end_time - int(time.time())
    caption = build_caption(text, winners_count, participants_count, seconds_left)

    try:
        await bot.edit_message_caption(
            chat_id=CHANNEL_ID,
            message_id=message_id,
            caption=caption,
            reply_markup=join_keyboard(giveaway_id),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


async def create_giveaway(admin_id: int) -> None:
    data = pending[admin_id]
    duration = data["duration"]
    winners_count = data["winners_count"]
    text = data["text"]
    photo_file_id = data["photo_file_id"]
    end_time = int(time.time()) + duration

    existing = await get_active_giveaway()
    if existing:
        raise RuntimeError("Сначала заверши текущий активный розыгрыш.")

    initial_caption = build_caption(text, winners_count, 0, duration)
    message = await bot.send_photo(
        chat_id=CHANNEL_ID,
        photo=photo_file_id,
        caption=initial_caption,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🎉 Участвовать", callback_data="noop")]]
        ),
    )

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO giveaways (message_id, end_time, winners_count, text, photo_file_id, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (message.message_id, end_time, winners_count, text, photo_file_id),
        )
        giveaway_id = cursor.lastrowid
        await db.commit()

    await bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID,
        message_id=message.message_id,
        reply_markup=join_keyboard(giveaway_id),
    )
    pending.pop(admin_id, None)


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except Exception:
        return False
    return member.status in {"member", "administrator", "creator"}


@dp.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(
        "🎁 <b>Giveaway Bot</b>\n\n"
        "Запускаю розыгрыши в канале, показываю живой таймер и выбираю победителей автоматически.\n\n"
        "Админу доступны команды /panel, /status и /start_giveaway."
    )


@dp.message(Command("panel"))
async def panel_handler(message: Message) -> None:
    if not is_admin(message):
        return

    await message.answer(
        "🛠 <b>Панель управления</b>\n\n"
        "/start_giveaway &lt;секунды&gt; &lt;победители&gt; - начать новый розыгрыш\n"
        "/status - состояние бота\n"
        "/cancel_giveaway - отменить создание черновика"
    )


@dp.message(Command("status"))
async def status_handler(message: Message) -> None:
    if not is_admin(message):
        return

    active = await get_active_giveaway()
    draft_exists = message.from_user.id in pending
    status_text = "есть активный розыгрыш" if active else "активного розыгрыша нет"

    await message.answer(
        "📊 <b>Статус бота</b>\n\n"
        "🟢 Бот в сети\n"
        f"🎁 Сейчас: {status_text}\n"
        f"📝 Черновик: {'есть' if draft_exists else 'нет'}\n"
        "💾 Хранилище: SQLite\n"
        "⚙️ Фреймворк: aiogram 3"
    )


@dp.message(Command("cancel_giveaway"))
async def cancel_giveaway_handler(message: Message) -> None:
    if not is_admin(message):
        return

    if pending.pop(message.from_user.id, None):
        await message.answer("Черновик розыгрыша удалён.")
    else:
        await message.answer("Активного черновика нет.")


@dp.message(Command("start_giveaway"))
async def start_giveaway_handler(message: Message) -> None:
    if not is_admin(message):
        return

    if await get_active_giveaway():
        await message.answer("Сейчас уже идёт активный розыгрыш. Дождись его завершения.")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: /start_giveaway 3600 3")
        return

    try:
        duration = int(parts[1])
        winners_count = int(parts[2])
    except ValueError:
        await message.answer("Длительность и количество победителей должны быть числами.")
        return

    if duration < 30:
        await message.answer("Минимальная длительность розыгрыша: 30 секунд.")
        return

    if winners_count < 1:
        await message.answer("Количество победителей должно быть не меньше 1.")
        return

    pending[message.from_user.id] = {
        "duration": duration,
        "winners_count": winners_count,
    }
    await message.answer("📸 Отправь фото для поста розыгрыша.")


@dp.message(F.photo)
async def photo_handler(message: Message) -> None:
    if not is_admin(message):
        return

    draft = pending.get(message.from_user.id)
    if not draft:
        return

    draft["photo_file_id"] = message.photo[-1].file_id
    await message.answer("📝 Теперь отправь текст розыгрыша одним сообщением.")


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    if not is_admin(message):
        return

    draft = pending.get(message.from_user.id)
    if not draft or "photo_file_id" not in draft:
        return

    draft["text"] = message.text.strip()
    if not draft["text"]:
        await message.answer("Текст не должен быть пустым.")
        return

    try:
        await create_giveaway(message.from_user.id)
    except RuntimeError as error:
        await message.answer(str(error))
        return

    await message.answer("✅ Розыгрыш опубликован в канале.")


@dp.callback_query(F.data.startswith("join:"))
async def join_handler(call: CallbackQuery) -> None:
    giveaway = await get_active_giveaway()
    if not giveaway:
        await call.answer("Розыгрыш уже завершён.", show_alert=True)
        return

    giveaway_id = int(call.data.split(":", 1)[1])
    active_giveaway_id = giveaway[0]
    if giveaway_id != active_giveaway_id:
        await call.answer("Этот розыгрыш уже неактуален.", show_alert=True)
        return

    if not await is_subscribed(call.from_user.id):
        await call.answer("Сначала подпишись на канал.", show_alert=True)
        return

    full_name = call.from_user.full_name or "Участник"
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO participants (giveaway_id, user_id, username, full_name, joined_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                giveaway_id,
                call.from_user.id,
                call.from_user.username,
                full_name,
                int(time.time()),
            ),
        )
        await db.commit()
        inserted = cursor.rowcount

    if inserted:
        await call.answer("Ты участвуешь. Удачи!")
    else:
        await call.answer("Ты уже в списке участников.")

    await refresh_giveaway_message(giveaway)


@dp.callback_query(F.data == "noop")
async def noop_handler(call: CallbackQuery) -> None:
    await call.answer()


async def giveaway_loop() -> None:
    while True:
        try:
            giveaway = await get_active_giveaway()
            if giveaway:
                giveaway_id, _message_id, end_time, winners_count, _text, _photo_file_id = giveaway
                seconds_left = end_time - int(time.time())
                if seconds_left > 0:
                    await refresh_giveaway_message(giveaway)
                else:
                    await refresh_giveaway_message(giveaway)
                    await finish_giveaway(giveaway_id, winners_count)
            await asyncio.sleep(UPDATE_INTERVAL)
        except Exception:
            logging.exception("Ошибка в цикле обновления розыгрыша")
            await asyncio.sleep(UPDATE_INTERVAL)


async def main() -> None:
    await init_db()
    asyncio.create_task(giveaway_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
