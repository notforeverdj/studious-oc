import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ChatJoinRequest,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

TOKEN        = "8950152316:AAHjF3IFPjOf9VIA522qVClZ1eNqLtNvYA4"
ADMIN_IDS    = [8309061996]
CHANNEL_ID   = -1003994139298
CHANNEL_LINK = "https://t.me/+JNZSVXkMJ9oxMWEy"
DB_FILE      = "kino.db"

logging.basicConfig(level=logging.INFO)
bot    = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp     = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ── BAZA ──────────────────────────────
def db():
    return sqlite3.connect(DB_FILE)

def db_init():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS movies (code TEXT PRIMARY KEY, file_id TEXT, title TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subscribers (user_id INTEGER PRIMARY KEY)")

def movie_add(code, file_id, title):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO movies VALUES (?,?,?)", (code, file_id, title))

def movie_get(code):
    with db() as c:
        return c.execute("SELECT file_id, title FROM movies WHERE code=?", (code,)).fetchone()

def movie_del(code):
    with db() as c:
        c.execute("DELETE FROM movies WHERE code=?", (code,))
        return c.execute("SELECT changes()").fetchone()[0] > 0

def movie_list():
    with db() as c:
        return c.execute("SELECT code, title FROM movies ORDER BY rowid DESC LIMIT 50").fetchall()

def movie_count():
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM movies").fetchone()[0]

def sub_add(uid):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO subscribers VALUES (?)", (uid,))

def sub_check(uid):
    with db() as c:
        return c.execute("SELECT 1 FROM subscribers WHERE user_id=?", (uid,)).fetchone() is not None

def is_admin(uid):
    return uid in ADMIN_IDS

# ── KLAVIATURALAR ─────────────────────
def kb_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Kino qo'sh",   callback_data="add"),
            InlineKeyboardButton(text="🗑 Kino o'chir", callback_data="delete"),
        ],
        [
            InlineKeyboardButton(text="📋 Ro'yxat",    callback_data="list"),
            InlineKeyboardButton(text="📊 Statistika", callback_data="stats"),
        ]
    ])

def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor", callback_data="cancel")]
    ])

def kb_subscribe(code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga o'tish", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"check_{code}")]
    ])

# ── FSM ───────────────────────────────
class Add(StatesGroup):
    video = State()
    code  = State()
    title = State()

class Delete(StatesGroup):
    code = State()

# ── BUYRUQLAR ─────────────────────────
@router.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "🎬 <b>Kino botga xush kelibsiz!</b>\n\n"
        "Kino olish uchun kodni yuboring.\n"
        "Misol: <code>1234</code>"
    )

@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer("⚙️ <b>Admin panel</b>", reply_markup=kb_admin())

# ── JOIN REQUEST ──────────────────────
@router.chat_join_request()
async def on_join_request(update: ChatJoinRequest):
    if update.chat.id == CHANNEL_ID:
        sub_add(update.from_user.id)

# ── CALLBACK TUGMALAR ─────────────────
@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⚙️ <b>Admin panel</b>", reply_markup=kb_admin())

@router.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    await call.message.edit_text(f"📊 Bazada: <b>{movie_count()}</b> ta kino", reply_markup=kb_admin())

@router.callback_query(F.data == "list")
async def lst(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    rows = movie_list()
    text = "📋 <b>Kinolar:</b>\n\n" + "\n".join(f"<code>{c}</code> — {t}" for c, t in rows) if rows else "Hozircha kino yo'q."
    await call.message.edit_text(text, reply_markup=kb_admin())

@router.callback_query(F.data == "add")
async def add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer()
    await state.set_state(Add.video)
    await call.message.edit_text("🎬 Kino videosini yuboring:", reply_markup=kb_cancel())

@router.callback_query(F.data == "delete")
async def del_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer()
    await state.set_state(Delete.code)
    await call.message.edit_text("🗑 O'chiriladigan kino kodini kiriting:", reply_markup=kb_cancel())

@router.callback_query(F.data.startswith("check_"))
async def check_sub(call: CallbackQuery):
    code = call.data.split("_", 1)[1]
    if not sub_check(call.from_user.id):
        await call.answer("❌ Hali zayavka tashlamagansiz!\nKanalga o'tib Join tugmasini bosing.", show_alert=True)
        return
    row = movie_get(code)
    if not row:
        await call.answer("❌ Kino topilmadi.", show_alert=True)
        return
    file_id, title = row
    await call.message.delete()
    try:
        await bot.send_video(call.from_user.id, file_id, caption=f"🎬 {title}")
    except Exception:
        await bot.send_document(call.from_user.id, file_id, caption=f"🎬 {title}")
    await call.answer("✅")

# ── FSM XABARLAR ─────────────────────
@router.message(Add.video)
async def add_video(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    v = msg.video or msg.document
    if not v:
        await msg.answer("⚠️ Video yoki fayl yuboring.", reply_markup=kb_cancel())
        return
    await state.update_data(file_id=v.file_id)
    await state.set_state(Add.code)
    await msg.answer("🔢 Kino kodini kiriting (masalan: 1234):", reply_markup=kb_cancel())

@router.message(Add.code)
async def add_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    code = msg.text.strip()
    if movie_get(code):
        await msg.answer(f"⚠️ <code>{code}</code> kodi band. Boshqa kod kiriting:", reply_markup=kb_cancel())
        return
    await state.update_data(code=code)
    await state.set_state(Add.title)
    await msg.answer("✏️ Kino nomini kiriting:", reply_markup=kb_cancel())

@router.message(Add.title)
async def add_title(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    title = msg.text.strip()
    movie_add(data["code"], data["file_id"], title)
    await state.clear()
    await msg.answer(f"✅ Saqlandi!\nKod: <code>{data['code']}</code>\nNom: {title}", reply_markup=kb_admin())

@router.message(Delete.code)
async def del_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    code = msg.text.strip()
    await state.clear()
    if movie_del(code):
        await msg.answer(f"✅ <code>{code}</code> o'chirildi.", reply_markup=kb_admin())
    else:
        await msg.answer("❌ Bunday kod topilmadi.", reply_markup=kb_admin())

# ── KOD QABUL QILISH ─────────────────
@router.message(F.text, StateFilter(None))
async def handle_code(msg: Message):
    if msg.text.startswith("/"):
        return
    code = msg.text.strip()
    row = movie_get(code)
    if not row:
        await msg.answer("❌ Bunday kod topilmadi.")
        return
    if not sub_check(msg.from_user.id):
        await msg.answer(
            "🔒 Kinoni olish uchun kanalimizga a'zo bo'lishingiz kerak.\n\n"
            "1️⃣ Kanalga o'ting\n"
            "2️⃣ <b>Join</b> tugmasini bosing\n"
            "3️⃣ <b>✅ Tekshirish</b> tugmasini bosing",
            reply_markup=kb_subscribe(code)
        )
        return
    file_id, title = row
    try:
        await msg.answer_video(file_id, caption=f"🎬 {title}")
    except Exception:
        await msg.answer_document(file_id, caption=f"🎬 {title}")

# ── ISHGA TUSHIRISH ───────────────────
async def main():
    db_init()
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
