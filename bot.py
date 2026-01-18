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

# --- KEEP ALIVE SERVER (For Render Web Service) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive and Running!"
def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))))
    t.start()

# --- FSM STATES FOR ADDING METHODS ---
class AddMethod(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
CHANNELS = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
BOT_USERNAME = "FreeMethodAll_Bot" #

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
users_col, methods_col = db.users, db.methods

# --- HELPERS ---
async def is_user_joined(user_id):
    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: return False
    return True

# --- START & REFERRAL LOGIC ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        # Naya user database mein save
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": referrer, "name": message.from_user.full_name})
        if referrer:
            # 1 Referral = 10 Points
            await users_col.update_one({"user_id": referrer}, {"$inc": {"points": 10}})
            try: await bot.send_message(referrer, "🎁 Someone joined using your link! You got 10 points.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_methods"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer_info"))
        await message.answer(f"✅ Welcome {message.from_user.first_name}!\n\nEarn 50 points (5 Referrals) to unlock any method.", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        #
        builder.row(types.InlineKeyboardButton(text="Join Channel 1", url="https://t.me/sanatani_methods"))
        builder.row(types.InlineKeyboardButton(text="Join Channel 2", url="https://t.me/did9ydyddofydo"))
        builder.row(types.InlineKeyboardButton(text="✅ Check Join", callback_data="check_join"))
        await message.answer("❌ Please join our channels first to use the bot!", reply_markup=builder.as_markup())

# --- REFERRAL INFO ---
@dp.callback_query(F.data == "refer_info")
async def refer_callback(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    points = user.get("points", 0) if user else 0
    ref_link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 **Your Wallet**\n\nPoints: `{points}`\nReferrals: `{points // 10}`\n\n🔗 **Your Link:**\n`{ref_link}`\n\nInvite 5 friends (50 points) to unlock a method!")

# --- VIEW METHODS (WITH 5 REFERRAL CHECK) ---
@dp.callback_query(F.data == "view_methods")
async def show_all_methods(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=m["title"], callback_data=f"lock_{m['_id']}"))
    
    if not builder.as_markup().inline_keyboard:
        await callback.message.edit_text("Currently no methods available.")
    else:
        await callback.message.edit_text("📚 Available Methods (Need 50 points to open):", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("lock_"))
async def check_points_and_show(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    points = user.get("points", 0) if user else 0
    
    # Check for 5 referrals (50 points)
    if points < 50:
        needed = 50 - points
        await callback.answer(f"❌ Access Denied!\nAapko 50 points chahiye. Abhi {points} hain. Aur {needed} points earn karein.", show_alert=True)
        return

    # If points are enough, show content
    method_id = callback.data.split("_")[1]
    m = await methods_col.find_one({"_id": ObjectId(method_id)})
    if m:
        if m.get("video_id"):
            await callback.message.answer_video(m["video_id"], caption=m["content"])
        else:
            await callback.message.answer(f"📖 **{m['title']}**\n\n{m['content']}")
    await callback.answer()

# --- INTERACTIVE ADD METHOD (ADMIN ONLY) ---
@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def start_add(message: types.Message, state: FSMContext):
    await message.answer("🆗 **Step 1:** Button ka naam bhejiye (e.g. Netflix Method)")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def get_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(f"✅ Title Set: `{message.text}`\n\n**Step 2:** Ab iska content (Text/Video) bhejiye.")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def get_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    content = message.text or message.caption
    # Database mein save
    await methods_col.insert_one({"title": data['title'], "content": content, "video_id": v_id})
    await message.answer("🚀 **Done!** Method added successfully.")
    await state.clear()

@dp.callback_query(F.data == "check_join")
async def check_j(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id): await callback.message.edit_text("✅ Success! Use /start to view methods.")
    else: await callback.answer("❌ You still haven't joined!", show_alert=True)

async def main():
    keep_alive() # Port Binding for Render
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
