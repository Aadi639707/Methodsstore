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

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = 8401733642
BOT_USERNAME = "FreeMethodAll_Bot"

REQUIRED_CHANNELS = [
    {"id": -1002454723830, "link": "https://t.me/SENPAI_GC", "name": "Senpai GC"},
    {"id": -1003801897984, "link": "https://t.me/sanatanigojo", "name": "Sanatani Gojo"},
    {"id": -1002331607869, "link": "https://t.me/Yonko_Crew", "name": "Yonko Crew"},
    {"id": -1003337157467, "link": "https://t.me/+dazyWXu95IxlMzg9", "name": "New GC"}
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
users_col, methods_col = db.users, db.methods

class AddMethod(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

async def is_user_joined(user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: return False
    return True

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        await users_col.insert_one({"user_id": user_id, "points": 0, "referred_by": ref})
        if ref:
            await users_col.update_one({"user_id": ref}, {"$inc": {"points": 10}})
            try: await bot.send_message(ref, "🎁 **+10 Points!** Someone joined via your link.")
            except: pass

    if await is_user_joined(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await message.answer(f"✅ Hello {message.from_user.first_name}!", reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        for ch in REQUIRED_CHANNELS:
            builder.row(types.InlineKeyboardButton(text=f"Join {ch['name']}", url=ch["link"]))
        builder.row(types.InlineKeyboardButton(text="✅ Check Membership", callback_data="check"))
        await message.answer("❌ Join all channels to use the bot:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check")
async def check_cb(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.delete()
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📚 View Methods", callback_data="view_all"))
        builder.row(types.InlineKeyboardButton(text="👥 Refer & Earn", callback_data="refer"))
        await callback.message.answer("✅ Verified!", reply_markup=builder.as_markup())
    else: await callback.answer("❌ Join all channels first!", show_alert=True)

@dp.callback_query(F.data == "refer")
async def refer_cb(callback: types.CallbackQuery):
    user = await users_col.find_one({"user_id": callback.from_user.id})
    link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    await callback.message.edit_text(f"💰 **Points:** `{user['points']}`\n🔗 **Referral Link:** `{link}`")

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
    if user.get("points", 0) < 50 and callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ You need 50 points!", show_alert=True)
    m = await methods_col.find_one({"_id": ObjectId(callback.data.split("_")[1])})
    if m:
        if m.get("video_id"): await callback.message.answer_video(m["video_id"], caption=m["content"])
        elif m.get("photo_id"): await callback.message.answer_photo(m["photo_id"], caption=m["content"])
        else: await callback.message.answer(m["content"])
    await callback.answer()

# --- FLASK ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is Alive"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- MAIN ---
async def main():
    # Start Flask in background
    Thread(target=run_flask, daemon=True).start()
    logger.info("Bot Polling Started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
