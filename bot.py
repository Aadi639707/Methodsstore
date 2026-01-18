import os, asyncio, logging
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# --- KEEP ALIVE ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive!"
def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))))
    t.start()

# --- SETUP ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
BOT_USERNAME = "FreeMethodAll_Bot"

# UPDATED CHANNELS DATA (Ab sirf 1 channel hai)
REQUIRED_CHANNELS = [
    {"id": -1002331607869, "link": "https://t.me/Yonko_Crew", "name": "Yonko Crew"}
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
users_col, methods_col = db.users, db.methods

class AddMethod(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

# --- HELPERS ---
async def is_user_joined(user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except Exception:
            return False
    return True

# --- COMMANDS ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": referrer})
        if referrer:
            await users_col.update_one({"user_id": referrer}, {"$inc": {"points": 10}})
            try: await bot.send_message(referrer, "🎁 +10 Points! Someone joined using your link.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!\nOptions select karein:", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        for ch in REQUIRED_CHANNELS:
            builder.row(types.InlineKeyboardButton(text=f"Join {ch['name']}", url=ch["link"]))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check"))
        await message.answer("❌ Niche diya gaya channel join karein tabhi bot chalega:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check")
async def check_cb(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.delete()
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await callback.message.answer("✅ Verification successful!", reply_markup=builder.as_markup())
    else: 
        await callback.answer("❌ Aapne abhi tak channel join nahi kiya!", show_alert=True)

# --- BROADCAST & ADMIN ---
@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message):
    if not message.reply_to_message: return await message.answer("Message par reply karein.")
    users = users_col.find({})
    count = 0
    async for u in users:
        try:
            await message.reply_to_message.send_copy(chat_id=u['user_id'])
            count += 1
        except: pass
    await message.answer(f"📢 Broadcast done! {count} users ko bhej diya gaya.")

@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def add_m(message: types.Message, state: FSMContext):
    await message.answer("Step 1: Button Title bhejein:")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def m_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Step 2: Method Content (Video/Photo/Text) bhejein:")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def m_cont(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    p_id = message.photo[-1].file_id if message.photo else None
    await methods_col.insert_one({"title": data['title'], "content": message.text or message.caption, "video_id": v_id, "photo_id": p_id})
    await message.answer("🚀 Method add ho gaya!")
    await state.clear()

@dp.callback_query(F.data == "view_all")
async def view_all(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=f"🔓 {m['title']}", callback_data=f"get_{m['_id']}"))
    await callback.message.edit_text("📚 Methods List:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def get_m(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    if user.get("points", 0) < 50 and callback.from_user.id != ADMIN_ID:
        return await callback.answer(f"❌ Unlock ke liye 50 points chahiye!", show_alert=True)
    
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): await callback.message.answer_video(m["video_id"], caption=m["content"])
        elif m.get("photo_id"): await callback.message.answer_photo(m["photo_id"], caption=m["content"])
        else: await callback.message.answer(m["content"])
    await callback.answer()

@dp.callback_query(F.data == "refer")
async def refer_cb(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 Points: `{user['points']}`\n🔗 Referral Link:\n`{link}`")

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
