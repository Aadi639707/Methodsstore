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
    if not channels: return True
    for ch_id in channels:
        try:
            # Ye user ka real-time status check karta hai
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]: 
                return False
        except Exception as e:
            print(f"Error checking {ch_id}: {e}")
            return False
    return True

# --- ADMIN PANEL ---
@dp.message(Command("addchannel"), F.from_user.id == ADMIN_ID)
async def add_ch(message: types.Message):
    try:
        ch_id = message.text.split()[1]
        await settings_col.update_one({"type": "channels"}, {"$addToSet": {"list": ch_id}}, upsert=True)
        await message.answer(f"✅ Channel `{ch_id}` Added to Database!")
    except: await message.answer("Usage: `/addchannel -100XXXXXXXX` (Use ID only)")

@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message):
    if not message.reply_to_message: return await message.answer("Reply to a message!")
    users = users_col.find({})
    count = 0
    async for u in users:
        try: 
            await message.reply_to_message.send_copy(chat_id=u['user_id'])
            count += 1
        except: pass
    await message.answer(f"📢 Broadcast Done! Sent to {count} users.")

# --- MAIN LOGIC ---
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    
    if not user:
        args = message.text.split()
        ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": ref_id})
        if ref_id:
            await users_col.update_one({"user_id": ref_id}, {"$inc": {"points": 10}})
            try: await bot.send_message(ref_id, "🎁 Congratulations! Someone joined using your link. You got 10 points.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!\nYou have joined all channels. Select an option:", reply_markup=builder.as_markup())
    else:
        channels = await get_channels()
        builder = InlineKeyboardBuilder()
        for ch in channels:
            try:
                chat = await bot.get_chat(ch)
                link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else "Join Link Not Found"
                builder.row(types.InlineKeyboardButton(text=f"Join {chat.title}", url=link))
            except:
                builder.row(types.InlineKeyboardButton(text="Join Private Channel", url="https://t.me/sanatani_methods"))
        
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check"))
        await message.answer("❌ You haven't joined our channels yet! Please join and click the button below.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check")
async def check_cb(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.delete()
        # Direct Menu Show karein
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await callback.message.answer("✅ Verification successful! Choose an option:", reply_markup=builder.as_markup())
    else: 
        await callback.answer("❌ Abhi bhi join nahi kiya! Saare channels join karke check karein.", show_alert=True)

@dp.callback_query(F.data == "view_all")
async def view_all(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=f"🔓 {m['title']}", callback_data=f"get_{m['_id']}"))
    await callback.message.edit_text("📚 Available Methods (Unlock for 50 Points):", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def get_m(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    if user.get("points", 0) < 50 and callback.from_user.id != ADMIN_ID:
        return await callback.answer(f"❌ You need 50 points (5 Refers) to unlock! Current: {user['points']}", show_alert=True)
    
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): await callback.message.answer_video(m["video_id"], caption=m["content"])
        else: await callback.message.answer(f"📖 **{m['title']}**\n\n{m['content']}")
    await callback.answer()

@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def add_m(message: types.Message, state: FSMContext):
    await message.answer("Step 1: Send Button Title:")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def m_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Step 2: Send Content (Text/Video/Photo):")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def m_cont(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    await methods_col.insert_one({"title": data['title'], "content": message.text or message.caption, "video_id": v_id})
    await message.answer("🚀 Method Added to Bot!")
    await state.clear()

@dp.callback_query(F.data == "refer")
async def refer_cb(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 **Wallet Balance**\n\nPoints: `{user['points']}`\nInvites: `{user['points']//10}`\n\n🔗 **Your Invite Link:**\n`{link}`")

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
