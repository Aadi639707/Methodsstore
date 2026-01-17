import os
import logging
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from dotenv import load_dotenv

# --- DUMMY SERVER FOR RENDER PORT FIX ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run():
    # Render uses port 10000 or a dynamic port
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT LOGIC ---
load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MONGO_URL = os.getenv('MONGO_URL')
CHANNELS = os.getenv('CHANNELS').split(',') 
PRIVATE_LINKS = os.getenv('PRIVATE_LINKS').split(',')

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
client = MongoClient(MONGO_URL)
db = client['referral_bot']
users = db.users
methods_db = db.methods

async def check_user_joined(user_id):
    for ch_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch_id.strip(), user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

def get_start_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for i, link in enumerate(PRIVATE_LINKS, 1):
        kb.add(InlineKeyboardButton(text=f"Join Channel {i} ↗️", url=link.strip()))
    kb.add(InlineKeyboardButton(text="✅ I Joined / Check", callback_data="check_join"))
    return kb

def get_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton(text="🧠 Get Method", callback_data="view_methods"))
    kb.add(InlineKeyboardButton(text="🔗 Referral Link", callback_data="my_ref"))
    return kb

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_id
    args = message.get_args()
    user = users.find_one({"_id": user_id})
    if not user:
        referrer = int(args) if args and args.isdigit() else None
        users.insert_one({"_id": user_id, "points": 0, "referred_by": referrer})
        if referrer and referrer != user_id:
            users.update_one({"_id": referrer}, {"$inc": {"points": 1}})
            try: await bot.send_message(referrer, "<b>🎉 New Referral!</b>\nYou earned +1 point.")
            except: pass
    await message.answer("<b>Welcome! Join our channels to unlock the methods:</b>", reply_markup=get_start_kb())

@dp.callback_query_handler(text="check_join")
async def check_join(call: types.CallbackQuery):
    joined = await check_user_joined(call.from_user.id)
    if joined:
        await call.message.edit_text("<b>Verified! ✅</b>\n\nInvite 5 friends to unlock 1 method.", reply_markup=get_main_menu())
    else:
        await call.answer("❌ You haven't joined all channels yet!", show_alert=True)

@dp.callback_query_handler(text="my_ref")
async def my_ref(call: types.CallbackQuery):
    user = users.find_one({"_id": call.from_user.id})
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    await call.message.answer(f"<b>Points:</b> {user['points']}\n<b>Link:</b> <code>{ref_link}</code>")

@dp.callback_query_handler(text="view_methods")
async def view_methods(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    # Updated Methods List
    method_list = ["ChatGPT Pro", "Ocoya Ai", "Youtube Premium", "Disney+", "CapCut Pro", "Gemini Bin", "Canva Pro", "Telegram Premium"]
    for i, name in enumerate(method_list, 1):
        kb.add(InlineKeyboardButton(text=f"Unlock {name} (5 pts)", callback_data=f"unlock_{i}"))
    await call.message.answer("<b>Select a method:</b>", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('unlock_'))
async def process_unlock(call: types.CallbackQuery):
    method_id = call.data.split('_')[1]
    user = users.find_one({"_id": call.from_user.id})
    if user['points'] >= 5:
        method_data = methods_db.find_one({"m_id": method_id})
        if method_data:
            users.update_one({"_id": call.from_user.id}, {"$inc": {"points": -5}})
            await bot.copy_message(chat_id=call.from_user.id, from_chat_id=ADMIN_ID, message_id=method_data['msg_id'])
            await call.message.answer("<b>✅ Method Unlocked!</b>")
        else:
            await call.answer("❌ Admin has not uploaded this content yet.", show_alert=True)
    else:
        await call.answer(f"❌ Need 5 points. (Current: {user['points']})", show_alert=True)

@dp.message_handler(commands=['setmethod'], user_id=ADMIN_ID)
async def set_method(message: types.Message):
    m_id = message.get_args()
    if not m_id or not message.reply_to_message:
        return await message.reply("Reply to content with: <code>/setmethod 1</code>")
    methods_db.update_one({"m_id": m_id}, {"$set": {"msg_id": message.reply_to_message.message_id}}, upsert=True)
    await message.reply(f"✅ Method {m_id} saved!")

@dp.message_handler(commands=['broadcast'], user_id=ADMIN_ID)
async def broadcast(message: types.Message):
    msg = message.get_args()
    if not msg: return
    all_users = users.find()
    for u in all_users:
        try: await bot.send_message(u['_id'], msg)
        except: pass
    await message.reply("Broadcast Done!")

if __name__ == '__main__':
    keep_alive()
    # Yahan skip_updates=True hona chahiye
    executor.start_polling(dp, skip_updates=True)

