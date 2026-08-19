import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
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
CARD_NUMBER  = "8600 1234 5678 9012"   # <-- o'z karta raqamingizni yozing
CARD_OWNER   = "Ism Familiya"          # <-- karta egasining ismi
PREMIUM_PRICE = 7000                   # so'm
PREMIUM_DAYS  = 30                     # obuna muddati (kun)
DB_FILE      = "kino.db"

logging.basicConfig(level=logging.INFO)
bot    = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp     = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ═══════════════════════════════════════
#               BAZA
# ═══════════════════════════════════════
def db():
    return sqlite3.connect(DB_FILE)

def db_init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_id TEXT,
            title TEXT,
            is_premium INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            submitted_at TEXT
        )""")

def movie_add(code, file_id, title, is_premium=0):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO movies VALUES (?,?,?,?)", (code, file_id, title, is_premium))

def movie_get(code):
    with db() as c:
        return c.execute("SELECT file_id, title, is_premium FROM movies WHERE code=?", (code,)).fetchone()

def movie_del(code):
    with db() as c:
        c.execute("DELETE FROM movies WHERE code=?", (code,))
        return c.execute("SELECT changes()").fetchone()[0] > 0

def movie_list():
    with db() as c:
        return c.execute("SELECT code, title, is_premium FROM movies ORDER BY rowid DESC LIMIT 50").fetchall()

def movie_count():
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM movies").fetchone()[0]

def sub_add(uid):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO subscribers VALUES (?)", (uid,))

def sub_check(uid):
    with db() as c:
        return c.execute("SELECT 1 FROM subscribers WHERE user_id=?", (uid,)).fetchone() is not None

def premium_add(uid, days=PREMIUM_DAYS):
    expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with db() as c:
        c.execute("INSERT OR REPLACE INTO premium_users VALUES (?,?)", (uid, expires))
    return expires

def premium_check(uid):
    with db() as c:
        row = c.execute("SELECT expires_at FROM premium_users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return False
    return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") > datetime.now()

def premium_expires(uid):
    with db() as c:
        row = c.execute("SELECT expires_at FROM premium_users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return None
    return row[0][:10]

def payment_add(uid, username, full_name):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO pending_payments VALUES (?,?,?,?)",
                  (uid, username or "—", full_name, datetime.now().strftime("%Y-%m-%d %H:%M")))

def payment_get(uid):
    with db() as c:
        return c.execute("SELECT * FROM pending_payments WHERE user_id=?", (uid,)).fetchone()

def payment_del(uid):
    with db() as c:
        c.execute("DELETE FROM pending_payments WHERE user_id=?", (uid,))

def is_admin(uid):
    return uid in ADMIN_IDS

# ═══════════════════════════════════════
#            KLAVIATURALAR
# ═══════════════════════════════════════
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

def kb_add_type():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🆓 Bepul", callback_data="type_free"),
            InlineKeyboardButton(text="👑 Premium", callback_data="type_premium"),
        ],
        [InlineKeyboardButton(text="❌ Bekor", callback_data="cancel")]
    ])

def kb_subscribe(code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga o'tish", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"check_{code}")]
    ])

def kb_premium(code):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👑 Premium olish ({PREMIUM_PRICE:,} so'm)", callback_data="buy_premium")],
        [InlineKeyboardButton(text="✅ Obuna bor", callback_data=f"check_premium_{code}")]
    ])

def kb_payment_confirm(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"),
            InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"pay_no_{uid}"),
        ]
    ])

def kb_check_payment():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'lovni tekshirdim", callback_data="check_payment")]
    ])

# ═══════════════════════════════════════
#               FSM
# ═══════════════════════════════════════
class Add(StatesGroup):
    video    = State()
    code     = State()
    title    = State()
    prem_type = State()

class Delete(StatesGroup):
    code = State()

class Payment(StatesGroup):
    waiting_receipt = State()

# ═══════════════════════════════════════
#           FOYDALANUVCHI
# ═══════════════════════════════════════
@router.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "🎬 <b>Kino botga xush kelibsiz!</b>\n\n"
        "Kino olish uchun kodni yuboring.\n"
        "Misol: <code>1234</code>\n\n"
        "👑 Premium kinolar uchun obuna kerak: /premium"
    )

@router.message(Command("premium"))
async def premium_info(msg: Message):
    uid = msg.from_user.id
    if premium_check(uid):
        await msg.answer(f"✅ Sizda faol premium obuna bor.\nMuddati: <b>{premium_expires(uid)}</b>")
        return
    await msg.answer(
        f"👑 <b>Premium obuna</b>\n\n"
        f"Narx: <b>{PREMIUM_PRICE:,} so'm / {PREMIUM_DAYS} kun</b>\n\n"
        f"Premium obuna orqali barcha maxsus kinolarni ko'rishingiz mumkin.\n\n"
        f"Obuna olish uchun /buy buyrug'ini yuboring."
    )

@router.message(Command("buy"))
async def buy_premium(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    if premium_check(uid):
        await msg.answer(f"✅ Sizda allaqachon faol premium bor.\nMuddati: <b>{premium_expires(uid)}</b>")
        return
    await state.set_state(Payment.waiting_receipt)
    await msg.answer(
        f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
        f"Karta: <code>{CARD_NUMBER}</code>\n"
        f"Egasi: <b>{CARD_OWNER}</b>\n"
        f"Miqdor: <b>{PREMIUM_PRICE:,} so'm</b>\n\n"
        f"To'lovni amalga oshirib, <b>chek rasmini</b> shu yerga yuboring.",
        reply_markup=kb_cancel()
    )

@router.message(Payment.waiting_receipt, F.photo)
async def receive_receipt(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    username = msg.from_user.username
    full_name = msg.from_user.full_name
    payment_add(uid, username, full_name)
    await state.clear()

    # Adminlarga xabar yuborish
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                msg.photo[-1].file_id,
                caption=(
                    f"💰 <b>Yangi to'lov so'rovi!</b>\n\n"
                    f"👤 Foydalanuvchi: {full_name}\n"
                    f"🔗 Username: @{username or '—'}\n"
                    f"🆔 ID: <code>{uid}</code>\n"
                    f"💵 Miqdor: {PREMIUM_PRICE:,} so'm"
                ),
                reply_markup=kb_payment_confirm(uid)
            )
        except Exception:
            pass

    await msg.answer(
        "✅ Chekingiz qabul qilindi!\n\n"
        "Admin tekshirib, tez orada obunangiz faollashtiriladi.",
        reply_markup=kb_check_payment()
    )

@router.message(Payment.waiting_receipt)
async def receipt_not_photo(msg: Message):
    await msg.answer("⚠️ Iltimos, chek <b>rasmini</b> yuboring.", reply_markup=kb_cancel())

@router.callback_query(F.data == "check_payment")
async def check_payment_status(call: CallbackQuery):
    uid = call.from_user.id
    if premium_check(uid):
        await call.message.edit_text(f"✅ Premium obunangiz faol!\nMuddati: <b>{premium_expires(uid)}</b>")
    else:
        await call.answer("⏳ Hali tasdiqlanmagan. Kutib turing.", show_alert=True)

# ── JOIN REQUEST ──────────────────────
@router.chat_join_request()
async def on_join_request(update: ChatJoinRequest):
    if update.chat.id == CHANNEL_ID:
        sub_add(update.from_user.id)

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

    file_id, title, is_premium = row
    uid = msg.from_user.id

    # Kanal obunasini tekshirish
    if not sub_check(uid):
        await msg.answer(
            "🔒 Kinoni olish uchun kanalimizga a'zo bo'lishingiz kerak.\n\n"
            "1️⃣ Kanalga o'ting\n"
            "2️⃣ <b>Join</b> tugmasini bosing\n"
            "3️⃣ <b>✅ Tekshirish</b> tugmasini bosing",
            reply_markup=kb_subscribe(code)
        )
        return

    # Premium tekshirish
    if is_premium and not premium_check(uid):
        await msg.answer(
            f"👑 Bu kino <b>premium</b> foydalanuvchilar uchun.\n\n"
            f"Obuna narxi: <b>{PREMIUM_PRICE:,} so'm / {PREMIUM_DAYS} kun</b>",
            reply_markup=kb_premium(code)
        )
        return

    # Kino yuborish
    try:
        await msg.answer_video(file_id, caption=f"🎬 {title}")
    except Exception:
        await msg.answer_document(file_id, caption=f"🎬 {title}")

@router.callback_query(F.data == "buy_premium")
async def buy_from_movie(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if premium_check(uid):
        await call.answer(f"✅ Sizda allaqachon premium bor!", show_alert=True)
        return
    await state.set_state(Payment.waiting_receipt)
    await call.message.edit_text(
        f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
        f"Karta: <code>{CARD_NUMBER}</code>\n"
        f"Egasi: <b>{CARD_OWNER}</b>\n"
        f"Miqdor: <b>{PREMIUM_PRICE:,} so'm</b>\n\n"
        f"To'lovni amalga oshirib, <b>chek rasmini</b> shu yerga yuboring.",
        reply_markup=kb_cancel()
    )

@router.callback_query(F.data.startswith("check_premium_"))
async def check_premium_then_send(call: CallbackQuery):
    code = call.data.split("check_premium_", 1)[1]
    uid = call.from_user.id
    if not premium_check(uid):
        await call.answer("❌ Premiumingiz hali faol emas.", show_alert=True)
        return
    row = movie_get(code)
    if not row:
        await call.answer("❌ Kino topilmadi.", show_alert=True)
        return
    file_id, title, _ = row
    await call.message.delete()
    try:
        await bot.send_video(uid, file_id, caption=f"🎬 {title}")
    except Exception:
        await bot.send_document(uid, file_id, caption=f"🎬 {title}")
    await call.answer("✅")

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
    file_id, title, is_premium = row
    uid = call.from_user.id
    if is_premium and not premium_check(uid):
        await call.message.edit_text(
            f"👑 Bu kino <b>premium</b> foydalanuvchilar uchun.\n\n"
            f"Obuna narxi: <b>{PREMIUM_PRICE:,} so'm / {PREMIUM_DAYS} kun</b>",
            reply_markup=kb_premium(code)
        )
        return
    await call.message.delete()
    try:
        await bot.send_video(uid, file_id, caption=f"🎬 {title}")
    except Exception:
        await bot.send_document(uid, file_id, caption=f"🎬 {title}")
    await call.answer("✅")

# ═══════════════════════════════════════
#           ADMIN: TO'LOV TASDIQLASH
# ═══════════════════════════════════════
@router.callback_query(F.data.startswith("pay_ok_"))
async def payment_approve(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    uid = int(call.data.split("pay_ok_")[1])
    expires = premium_add(uid)
    payment_del(uid)
    await call.message.edit_caption(
        call.message.caption + f"\n\n✅ <b>Tasdiqlandi</b> — muddati: {expires[:10]}"
    )
    try:
        await bot.send_message(
            uid,
            f"🎉 <b>Tabriklaymiz!</b>\n\n"
            f"Premium obunangiz faollashtirildi.\n"
            f"Muddati: <b>{expires[:10]}</b>\n\n"
            f"Endi barcha premium kinolarni ko'rishingiz mumkin!"
        )
    except Exception:
        pass
    await call.answer("✅ Tasdiqlandi")

@router.callback_query(F.data.startswith("pay_no_"))
async def payment_reject(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    uid = int(call.data.split("pay_no_")[1])
    payment_del(uid)
    await call.message.edit_caption(call.message.caption + "\n\n❌ <b>Rad etildi</b>")
    try:
        await bot.send_message(
            uid,
            "❌ To'lovingiz tasdiqlanmadi.\n\n"
            "Muammo bo'lsa, admin bilan bog'laning."
        )
    except Exception:
        pass
    await call.answer("❌ Rad etildi")

# ═══════════════════════════════════════
#           ADMIN PANEL
# ═══════════════════════════════════════
@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if not is_admin(msg.from_user.id): return
    await msg.answer("⚙️ <b>Admin panel</b>", reply_markup=kb_admin())

@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⚙️ <b>Admin panel</b>", reply_markup=kb_admin())

@router.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    with db() as c:
        total    = c.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        premium  = c.execute("SELECT COUNT(*) FROM movies WHERE is_premium=1").fetchone()[0]
        subs     = c.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        prem_usr = c.execute("SELECT COUNT(*) FROM premium_users WHERE expires_at > ?",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()[0]
        pending  = c.execute("SELECT COUNT(*) FROM pending_payments").fetchone()[0]
    await call.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"🎬 Jami kinolar: <b>{total}</b>\n"
        f"👑 Premium kinolar: <b>{premium}</b>\n"
        f"👥 Kanal a'zolari: <b>{subs}</b>\n"
        f"💎 Faol premium foydalanuvchilar: <b>{prem_usr}</b>\n"
        f"⏳ Kutilayotgan to'lovlar: <b>{pending}</b>",
        reply_markup=kb_admin()
    )

@router.callback_query(F.data == "list")
async def lst(call: CallbackQuery):
    if not is_admin(call.from_user.id): return await call.answer()
    rows = movie_list()
    if rows:
        lines = []
        for code, title, is_prem in rows:
            icon = "👑" if is_prem else "🆓"
            lines.append(f"{icon} <code>{code}</code> — {title}")
        text = "📋 <b>Kinolar:</b>\n\n" + "\n".join(lines)
    else:
        text = "Hozircha kino yo'q."
    await call.message.edit_text(text, reply_markup=kb_admin())

@router.callback_query(F.data == "add")
async def add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer()
    await state.set_state(Add.video)
    await call.message.edit_text("🎬 Kino videosini yuboring:", reply_markup=kb_cancel())

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
    await state.update_data(title=title)
    await state.set_state(Add.prem_type)
    await msg.answer(
        f"Kino turi:\n<b>{title}</b> — bepulmi yoki premiummi?",
        reply_markup=kb_add_type()
    )

@router.callback_query(F.data.in_({"type_free", "type_premium"}))
async def add_type(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer()
    data = await state.get_data()
    is_premium = 1 if call.data == "type_premium" else 0
    movie_add(data["code"], data["file_id"], data["title"], is_premium)
    await state.clear()
    icon = "👑 Premium" if is_premium else "🆓 Bepul"
    await call.message.edit_text(
        f"✅ Saqlandi!\n"
        f"Kod: <code>{data['code']}</code>\n"
        f"Nom: {data['title']}\n"
        f"Tur: {icon}",
        reply_markup=kb_admin()
    )

@router.callback_query(F.data == "delete")
async def del_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return await call.answer()
    await state.set_state(Delete.code)
    await call.message.edit_text("🗑 O'chiriladigan kino kodini kiriting:", reply_markup=kb_cancel())

@router.message(Delete.code)
async def del_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    code = msg.text.strip()
    await state.clear()
    if movie_del(code):
        await msg.answer(f"✅ <code>{code}</code> o'chirildi.", reply_markup=kb_admin())
    else:
        await msg.answer("❌ Bunday kod topilmadi.", reply_markup=kb_admin())

# ═══════════════════════════════════════
#          ISHGA TUSHIRISH
# ═══════════════════════════════════════
async def main():
    db_init()
    print("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
