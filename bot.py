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

# --- DYNAMIC HELPERS ---
async def get_channels():
    data = await settings_col.find_one({"type": "channels"})
    return data["list"] if data and "list" in data else []

async def is_user_joined(user_id):
    channels = await get_channels()
    if not channels: return True # Agar koi channel nahi toh allow karein
    for channel_id in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except Exception as e:
            logging.error(f"Join Check Error: {e}")
            return False
    return True

# --- ADMIN COMMANDS ---

@dp.message(Command("addchannel"), F.from_user.id == ADMIN_ID)
async def add_channel_cmd(message: types.Message):
    try:
        channel_id = message.text.split()[1]
        if not channel_id.startswith("-100"):
            return await message.answer("❌ Invalid ID! Channel ID must start with -100")
        await settings_col.update_one({"type": "channels"}, {"$addToSet": {"list": channel_id}}, upsert=True)
        await message.answer(f"✅ Channel `{channel_id}` added successfully!")
    except:
        await message.answer("❌ Usage: `/addchannel -100XXXXXXXX`")

@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast_handler(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("❌ Reply to a message with /broadcast")
    users = users_col.find({})
    sent = 0
    async for user in users:
        try:
            await message.reply_to_message.send_copy(chat_id=user['user_id'])
            sent += 1
        except: pass
    await message.answer(f"📢 Broadcast sent to {sent} users.")

# --- MAIN LOGIC ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Save User & Referral
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": referrer, "name": message.from_user.full_name})
        if referrer:
            await users_col.update_one({"user_id": referrer}, {"$inc": {"points": 10}})
            try: await bot.send_message(referrer, "🎁 Someone joined! You got 10 points.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer_info"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!", reply_markup=builder.as_markup())
    else:
        channels = await get_channels()
        builder = InlineKeyboardBuilder()
        for ch in channels:
            # Create a direct link (removing -100 for public links or keep it simple)
            builder.row(types.InlineKeyboardButton(text="Join Channel", url=f"https://t.me/{(str(ch)).replace('-100', '')}"))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check_join"))
        await message.answer("❌ You must join our channels first!", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check_join")
async def check_join_callback(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer_info"))
        await callback.message.edit_text("✅ Verification successful! Choose an option:", reply_markup=builder.as_markup())
    else:
        await callback.answer("❌ You haven't joined all channels yet!", show_alert=True)

# --- METHOD MANAGEMENT ---

@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def start_add(message: types.Message, state: FSMContext):
    await message.answer("🆗 Send Button Title:")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def get_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("✅ Now send Content (Text/Video/Photo):")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def get_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    p_id = message.photo[-1].file_id if message.photo else None
    txt = message.text or message.caption
    await methods_col.insert_one({"title": data['title'], "content": txt, "video_id": v_id, "photo_id": p_id})
    await message.answer("🚀 Method Added!")
    await state.clear()

@dp.callback_query(F.data == "view_all")
async def list_methods(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=f"🔓 {m['title']}", callback_data=f"get_{m['_id']}"))
    await callback.message.edit_text("📚 Available Methods:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def unlock(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    if (user.get("points", 0) < 50) and (callback.from_user.id != ADMIN_ID):
        return await callback.answer(f"❌ 5 Refers required! Current Points: {user['points']}", show_alert=True)
    
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): await callback.message.answer_video(m["video_id"], caption=m["content"])
        elif m.get("photo_id"): await callback.message.answer_photo(m["photo_id"], caption=m["content"])
        else: await callback.message.answer(m["content"])
    await callback.answer()

@dp.callback_query(F.data == "refer_info")
async def refer_info(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 **Your Stats**\n\nPoints: `{user['points']}`\nInvites: `{user['points']//10}`\n\n🔗 **Your Link:**\n`{link}`")

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
