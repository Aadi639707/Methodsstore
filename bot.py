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
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
BOT_USERNAME = "FreeMethodAll_Bot"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
users_col, methods_col, settings_col = db.users, db.methods, db.settings

class AddMethod(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

# --- HELPERS ---
async def get_channels():
    data = await settings_col.find_one({"type": "channels"})
    return data["list"] if data and "list" in data else []

async def is_user_joined(user_id):
    channels = await get_channels()
    if not channels: return True
    for ch_id in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: return False
    return True

# --- ADMIN PANEL ---
@dp.message(Command("addchannel"), F.from_user.id == ADMIN_ID)
async def add_ch(message: types.Message):
    try:
        ch_id = message.text.split()[1]
        await settings_col.update_one({"type": "channels"}, {"$addToSet": {"list": ch_id}}, upsert=True)
        await message.answer(f"✅ Channel `{ch_id}` Added!")
    except: await message.answer("Usage: `/addchannel -100xxx`")

@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message):
    if not message.reply_to_message: return await message.answer("Reply to a message!")
    users = users_col.find({})
    async for u in users:
        try: await message.reply_to_message.send_copy(chat_id=u['user_id'])
        except: pass
    await message.answer("📢 Broadcast Done!")

# --- MAIN LOGIC ---
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        ref_id = int(message.text.split()[1]) if len(message.text.split()) > 1 and message.text.split()[1].isdigit() else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": ref_id})
        if ref_id and ref_id != user_id:
            await users_col.update_one({"user_id": ref_id}, {"$inc": {"points": 10}})
            try: await bot.send_message(ref_id, "🎁 +10 Points! Someone joined.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 Methods", callback_data="view_all"),
                    types.InlineKeyboardButton(text="👥 Refer", callback_data="refer"))
        await message.answer("✅ Welcome! Select an option:", reply_markup=builder.as_markup())
    else:
        channels = await get_channels()
        builder = InlineKeyboardBuilder()
        for ch in channels:
            builder.row(types.InlineKeyboardButton(text="Join Channel", url=f"https://t.me/{str(ch).replace('-100','') }"))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check"))
        await message.answer("❌ Join our channels first!", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check")
async def check_cb(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.answer("✅ Success! Use /start")
        await callback.message.delete()
    else: await callback.answer("❌ Join all channels!", show_alert=True)

@dp.callback_query(F.data == "view_all")
async def view_all(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=m['title'], callback_data=f"get_{m['_id']}"))
    await callback.message.edit_text("📚 Select Method:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def get_m(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    if user.get("points", 0) < 50 and callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ 50 Points (5 Refers) Required!", show_alert=True)
    
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): await callback.message.answer_video(m["video_id"], caption=m["content"])
        else: await callback.message.answer(m["content"])
    await callback.answer()

@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def add_m(message: types.Message, state: FSMContext):
    await message.answer("Enter Title:")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def m_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Send Content (Text/Video):")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def m_cont(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    await methods_col.insert_one({"title": data['title'], "content": message.text or message.caption, "video_id": v_id})
    await message.answer("🚀 Added!")
    await state.clear()

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
