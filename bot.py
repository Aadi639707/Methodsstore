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
CHANNELS = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
BOT_USERNAME = "FreeMethodAll_Bot"

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
    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: return False
    return True

# --- START & REFERRAL ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": referrer, "name": message.from_user.full_name})
        if referrer:
            await users_col.update_one({"user_id": referrer}, {"$inc": {"points": 10}}) 
            try: await bot.send_message(referrer, "🎁 Someone joined using your link! You got 10 points.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all_methods"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer_info"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!\n\nEarn 50 points (5 Referrals) to unlock any method.", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Join Channel 1", url="https://t.me/sanatani_methods"))
        builder.row(types.InlineKeyboardButton(text="Join Channel 2", url="https://t.me/did9ydyddofydo"))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check_join"))
        await message.answer("❌ You must join our channels to use this bot!", reply_markup=builder.as_markup())

# --- REFERRAL INFO ---
@dp.callback_query(F.data == "refer_info")
async def refer_callback(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    points = user.get("points", 0) if user else 0
    ref_link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 **Your Balance**\n\nPoints: `{points}`\nReferrals: `{points // 10}`\n\n🔗 **Your Referral Link:**\n`{ref_link}`\n\nInvite 5 friends (50 points) to unlock any method!")

# --- VIEW METHODS LOGIC ---
@dp.callback_query(F.data == "view_all_methods")
async def list_methods(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    count = 0
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=f"🔓 {m['title']}", callback_data=f"get_{str(m['_id'])}"))
        count += 1
    
    if count == 0:
        await callback.answer("No methods available yet.", show_alert=True)
    else:
        await callback.message.edit_text("📚 Select a method to unlock (50 points required):", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def unlock_method(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    points = user.get("points", 0) if user else 0
    
    if points < 50:
        await callback.answer(f"❌ Access Denied! You have {points}/50 points. Need {50-points} more.", show_alert=True)
        return

    method_id = callback.data.split("_")[1]
    method = await methods_col.find_one({"_id": ObjectId(method_id)})
    
    if method:
        if method.get("video_id"):
            await callback.message.answer_video(method["video_id"], caption=f"📖 **{method['title']}**\n\n{method.get('content', '')}")
        else:
            await callback.message.answer(f"📖 **{method['title']}**\n\n{method.get('content', 'No description')}")
    await callback.answer()

# --- ADMIN: ADD METHOD ---
@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def start_add(message: types.Message, state: FSMContext):
    await message.answer("🆗 **Step 1:** Send the button title (e.g., Netflix Trick):")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def get_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(f"✅ Title: `{message.text}`\n\n**Step 2:** Now send the method content (Text or Video):")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def get_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    content = message.text or message.caption
    await methods_col.insert_one({"title": data['title'], "content": content, "video_id": v_id})
    await message.answer("🚀 **Success!** Method added to the list.")
    await state.clear()

# --- ADMIN: BROADCAST ---
@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast_msg(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Reply to any message with /broadcast to send it to all users.")
    
    users = users_col.find({})
    sent, failed = 0, 0
    async for user in users:
        try:
            await message.reply_to_message.send_copy(chat_id=user['user_id'])
            sent += 1
        except: failed += 1
    await message.answer(f"📢 **Broadcast Done!**\n✅ Sent: {sent}\n❌ Failed: {failed}")

@dp.callback_query(F.data == "check_join")
async def check_j(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id): 
        await callback.message.edit_text("✅ Verification successful! Use /start to see methods.")
    else: 
        await callback.answer("❌ You haven't joined yet!", show_alert=True)

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
