import os
import asyncio
import logging
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
def home(): return "Bot is Running!"
def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))))
    t.start()

# --- SETUP ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
CHANNELS = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
BOT_USERNAME = "FreeMethodAll_Bot" # Aapka bot username

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
users_col = db.users
methods_col = db.methods

# --- STATES ---
class AddMethod(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

# --- HELPERS ---
async def is_user_joined(user_id):
    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: return False
    return True

# --- COMMANDS ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Referral Logic
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        referrer = None
        if len(args) > 1 and args[1].isdigit():
            referrer_id = int(args[1])
            if referrer_id != user_id:
                referrer = referrer_id
        
        await users_col.insert_one({
            "user_id": user_id,
            "points": 0,
            "referred_by": referrer,
            "name": message.from_user.full_name
        })
        
        if referrer:
            await users_col.update_one({"user_id": referrer}, {"$inc": {"points": 10}}) # 10 points per refer
            await bot.send_message(referrer, "🎁 Someone joined using your link! You got 10 points.")

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 Methods", callback_data="view_methods"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer_info"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!\n\nUse buttons below:", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Join Channel 1", url="https://t.me/sanatani_methods"))
        builder.row(types.InlineKeyboardButton(text="Join Channel 2", url="https://t.me/did9ydyddofydo"))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check_join"))
        await message.answer("❌ Please join channels first!", reply_markup=builder.as_markup())

@dp.message(Command("refer"))
@dp.callback_query(F.data == "refer_info")
async def refer_info(event):
    user_id = event.from_user.id if isinstance(event, types.Message) else event.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    points = user.get("points", 0) if user else 0
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    
    text = f"👥 **Referral System**\n\n💰 Your Points: `{points}`\n🔗 Your Link: `{ref_link}`\n\nInvite friends and get 10 points for each join!"
    
    if isinstance(event, types.Message):
        await event.answer(text)
    else:
        await event.message.edit_text(text)

# --- METHOD HANDLERS (Same as before) ---
@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def start_add_method(message: types.Message, state: FSMContext):
    await message.answer("🆗 Send Button Title (e.g. Netflix):")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("✅ Now send the Method Content (Text/Video/Link):")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def process_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    content = message.text or message.caption
    v_id = message.video.file_id if message.video else None
    await methods_col.insert_one({"title": data['title'], "content": content, "video_id": v_id})
    await message.answer("🚀 Method Added Successfully!")
    await state.clear()

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
