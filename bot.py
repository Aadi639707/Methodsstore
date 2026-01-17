import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# Config (Variables to be set on Render Dashboard)
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MONGO_URL = os.getenv('MONGO_URL')
CHANNELS = os.getenv('CHANNELS').split(',') # Format: @ch1,@ch2,@ch3

# Initialization
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
client = MongoClient(MONGO_URL)
db = client['referral_bot']
users = db.users
methods_db = db.methods

# --- Keyboards ---
def get_start_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(CHANNELS, 1):
        kb.add(InlineKeyboardButton(text=f"Join Channel {i}", url=f"https://t.me/{ch.strip().replace('@','')}"))
    kb.add(InlineKeyboardButton(text="✅ I Joined / Check", callback_data="check_join"))
    return kb

def get_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton(text="🧠 Get Method", callback_data="view_methods"))
    kb.add(InlineKeyboardButton(text="🔗 Referral", callback_data="my_ref"))
    return kb

# --- Handlers ---
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_id
    args = message.get_args()
    
    user = users.find_one({"_id": user_id})
    if not user:
        referrer = int(args) if args and args.isdigit() else None
        users.insert_one({
            "_id": user_id,
            "points": 0,
            "referred_by": referrer
        })
        if referrer and referrer != user_id:
            users.update_one({"_id": referrer}, {"$inc": {"points": 1}})
            try:
                await bot.send_message(referrer, "<b>🎉 New Referral Alert!</b>\nYou have earned +1 point.")
            except: pass

    await message.answer("<b>Welcome! Please join all channels first to access the methods:</b>", reply_markup=get_start_kb())

@dp.callback_query_handler(text="check_join")
async def check_join(call: types.CallbackQuery):
    # Success message after verification
    await call.message.edit_text("<b>Status: Verified Successfully! ✅</b>\n\nInvite 5 friends to unlock any 1 method.", reply_markup=get_main_menu())

@dp.callback_query_handler(text="my_ref")
async def my_ref(call: types.CallbackQuery):
    user = users.find_one({"_id": call.from_user.id})
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    
    text = (f"<b>👤 Your Statistics</b>\n\n"
            f"<b>Total Points:</b> {user['points']}\n"
            f"<b>Referral Link:</b>\n<code>{ref_link}</code>\n\n"
            f"<i>Instructions: 5 points are required to unlock 1 single method.</i>")
    await call.message.answer(text)

@dp.callback_query_handler(text="view_methods")
async def view_methods(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    # Define your method names here
    method_list = [
        "ChatGPT 1 Month Pro", "Ocoya Ai Method", "Youtube Premium", 
        "Disney+ Premium", "CapCut Pro", "Gemini Bin", 
        "Canva Pro Method", "Telegram Premium Method"
    ]
    
    for i, name in enumerate(method_list, 1):
        kb.add(InlineKeyboardButton(text=f"Unlock {name} (5 pts)", callback_data=f"unlock_{i}"))
    
    await call.message.answer("<b>Select a method to unlock:</b>\n(5 points will be deducted per unlock)", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('unlock_'))
async def process_unlock(call: types.CallbackQuery):
    method_id = call.data.split('_')[1]
    user = users.find_one({"_id": call.from_user.id})
    
    if user['points'] >= 5:
        method_data = methods_db.find_one({"m_id": method_id})
        if method_data:
            # Deduct 5 points and provide content
            users.update_one({"_id": call.from_user.id}, {"$inc": {"points": -5}})
            await call.message.answer(f"<b>✅ Method Unlocked Successfully!</b>\n\n{method_data['content']}")
        else:
            await call.answer("❌ This method is not available yet. Please wait for the Admin to upload.", show_alert=True)
    else:
        await call.answer(f"❌ Insufficient Points! You need 5 points. (Current: {user['points']})", show_alert=True)

# --- Admin Only Commands ---
@dp.message_handler(commands=['setmethod'], user_id=ADMIN_ID)
async def set_method(message: types.Message):
    # Syntax:
  
