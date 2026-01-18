import os
import asyncio
import logging
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient

# --- KEEP ALIVE SERVER FOR RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running!"

def run():
    # Render default port 10000 use karta hai
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT LOGIC ---
logging.basicConfig(level=logging.INFO)

# Variables fetch
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7757213781"))
# IDs comma se split honge
CHANNELS = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# MongoDB setup
client = AsyncIOMotorClient(MONGO_URL)
db = client.get_database("ClonecartBot")
collection = db.users

# Join Check Function
async def is_user_joined(user_id):
    if not CHANNELS:
        return True
    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.error(f"Error checking {channel_id}: {e}")
            return False
    return True

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    
    # User data update in DB
    await collection.update_one(
        {"user_id": user_id},
        {"$set": {"username": message.from_user.username}},
        upsert=True
    )

    if await is_user_joined(user_id):
        await message.answer("✅ Welcome! Join process complete. You can now access methods.")
    else:
        builder = InlineKeyboardBuilder()
        # Buttons aapke links ke mutabiq
        builder.row(types.InlineKeyboardButton(text="Join Channel 1", url="https://t.me/sanatani_methods"))
        builder.row(types.InlineKeyboardButton(text="Join Channel 2", url="https://t.me/did9ydyddofydo"))
        builder.row(types.InlineKeyboardButton(text="✅ I Joined / Check", callback_data="check_join"))
        
        await message.answer("❌ Please join our channels to continue:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check_join")
async def check_callback(callback: types.CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.edit_text("✅ Success! You have joined all channels.")
    else:
        await callback.answer("❌ You haven't joined all channels yet!", show_alert=True)

async def main():
    logging.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive() # Render port binding fix
    asyncio.run(main())
    
