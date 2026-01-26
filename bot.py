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

# --- KEEP ALIVE SETUP ---
app = Flask('')

@app.route('/')
def home(): 
    return "Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = 8401733642
BOT_USERNAME = "FreeMethodAll_Bot"

# --- CHANNELS DATA ---
REQUIRED_CHANNELS = [
    {"id": -1002454723830, "link": "https://t.me/SENPAI_GC", "name": "Senpai GC"},
    {"id": -1003801897984, "link": "https://t.me/sanatanigojo", "name": "Sanatani Gojo"},
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
            if member.status in ["left", "kicked"]: 
                return False
        except Exception as e:
            logging.error(f"Error checking channel {ch['id']}: {e}")
            return False
    return True

# --- COMMAND HANDLERS ---
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
            try: 
                await bot.send_message(referrer, "🎁 **+10 Points!** Someone joined using your referral link.")
            except: 
                pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await message.answer(f"✅ **Hello {message.from_user.first_name}!**\nWelcome to the bot. Please choose an option below:", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        for ch in REQUIRED_CHANNELS:
            builder.row(types.InlineKeyboardButton(text=f"Join {ch['name']}", url=ch["link"]))
        builder.row(types.InlineKeyboardButton(text="✅ Check Membership", callback_data="check"))
        await message.answer("❌ **Access Denied!**\nYou must join all the channels below to use this bot:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check")
async def check_cb(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.delete()
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await callback.message.answer("✅ **Verification Successful!**\nYou can now use the bot.", reply_markup=builder.as_markup())
    else: 
        await callback.answer("❌ You haven't joined all channels yet!", show_alert=True)

# --- ADMIN COMMANDS ---
@dp.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message):
    if not message.reply_to_message: 
        return await message.answer("Please reply to a message to broadcast it.")
    
    users = users_col.find({})
    count = 0
    async for u in users:
        try:
            await message.reply_to_message.send_copy(chat_id=u['user_id'])
            count += 1
        except: 
            pass
    await message.answer(f"📢 **Broadcast Completed!** Sent to {count} users.")

@dp.message(Command("addmethod"), F.from_user.id == ADMIN_ID)
async def add_m(message: types.Message, state: FSMContext):
    await message.answer("🛠 **Step 1:** Send the title for the button:")
    await state.set_state(AddMethod.waiting_for_title)

@dp.message(AddMethod.waiting_for_title)
async def m_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("🛠 **Step 2:** Send the content (Text, Photo, or Video) for the method:")
    await state.set_state(AddMethod.waiting_for_content)

@dp.message(AddMethod.waiting_for_content)
async def m_cont(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_id = message.video.file_id if message.video else None
    p_id = message.photo[-1].file_id if message.photo else None
    content = message.text or message.caption
    
    await methods_col.insert_one({
        "title": data['title'], 
        "content": content, 
        "video_id": v_id, 
        "photo_id": p_id
    })
    await message.answer("🚀 **Success!** Method has been added to the database.")
    await state.clear()

# --- USER FEATURES ---
@dp.callback_query(F.data == "view_all")
async def view_all(callback: types.CallbackQuery):
    cursor = methods_col.find({})
    builder = InlineKeyboardBuilder()
    async for m in cursor:
        builder.row(types.InlineKeyboardButton(text=f"🔓 {m['title']}", callback_data=f"get_{m['_id']}"))
    
    await callback.message.edit_text("📚 **Available Methods:**", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def get_m(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    points = user.get("points", 0)
    
    if points < 50 and callback.from_user.id != ADMIN_ID:
        return await callback.answer(f"❌ You need 50 points to unlock this! Your points: {points}", show_alert=True)
    
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): 
            await callback.message.answer_video(m["video_id"], caption=m["content"])
        elif m.get("photo_id"): 
            await callback.message.answer_photo(m["photo_id"], caption=m["content"])
        else: 
            await callback.message.answer(m["content"])
    await callback.answer()

@dp.callback_query(F.data == "refer")
async def refer_cb(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(
        f"💰 **My Points:** `{user['points']}`\n\n"
        f"🔗 **Referral Link:**\n`{link}`\n\n"
        f"Share this link! You get 10 points for every friend who joins."
    )

async def main():
    keep_alive()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
