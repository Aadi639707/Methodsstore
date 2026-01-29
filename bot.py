import os, asyncio, logging
from flask import Flask
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
        await callback.message.answer("✅ Verification successful!", reply_markup=builder.as_markup())
    else: await callback.answer("❌ Join all channels first!", show_alert=True)

# ... (Baki handlers same rahenge)

# --- FLASK ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is Alive"

async def main():
    logger.info("Bot Polling Starting...")
    # Delete Webhook specifically before starting
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Run Flask and Bot together
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), use_reloader=False))
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
