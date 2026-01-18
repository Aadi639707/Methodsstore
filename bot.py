import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient

# Logs setup
logging.basicConfig(level=logging.INFO)

# Variables (Render/Replit se fetch karega)
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
CHANNELS = os.getenv("CHANNELS", "").split(",")

# Bot aur Dispatcher setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
collection = db.users

# --- JOIN CHECK LOGIC ---
async def is_user_joined(user_id):
    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id.strip(), user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.error(f"Error checking channel {channel_id}: {e}")
            return False
    return True

# --- COMMANDS ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # Database check
    user = await collection.find_one({"user_id": user_id})
    if not user:
        await collection.insert_one({"user_id": user_id, "points": 0})

    if await is_user_joined(user_id):
        await message.answer(f"Welcome back! You have access to all methods.")
    else:
        # Join buttons setup
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="Join Channel 1", url="https://t.me/sanatani_methods"))
        builder.row(types.InlineKeyboardButton(text="Join Channel 2", url="https://t.me/did9ydyddofydo"))
        builder.row(types.InlineKeyboardButton(text="✅ I Joined / Check", callback_data="check_join"))
        
        await message.answer("❌ Join all channels first!", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check_join")
async def check_callback(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.edit_text("✅ Success! Now you can use the bot.")
    else:
        await callback.answer("❌ You still haven't joined all channels!", show_alert=True)

# --- MAIN RUNNER ---
async def main():
    logging.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
