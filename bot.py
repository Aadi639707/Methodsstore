import os
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# Config from Render/Environment
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MONGO_URL = os.getenv('MONGO_URL')
# Use IDs for verification (e.g., -100123456)
CHANNELS = os.getenv('CHANNELS').split(',') 
# Use Invite Links for buttons (e.g., https://t.me/+)
PRIVATE_LINKS = os.getenv('PRIVATE_LINKS').split(',')

# Initialization
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
client = MongoClient(MONGO_URL)
db = client['referral_bot']
users = db.users
methods_db = db.methods

# --- Check Subscription Logic ---
async def check_user_joined(user_id):
    for ch_id in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch_id.strip(), user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            # If bot is not admin in one of the channels
            return False
    return True

# --- Keyboards ---
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

# --- Start & Referral Logic ---
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
                await bot.send_message(referrer, "<b>🎉 Someone joined using your link!</b>\nYou earned +1 point.")
            except: pass

    await message.answer("<b>Welcome! To access our paid methods for free, please join our channels:</b>", reply_markup=get_start_kb())

@dp.callback_query_handler(text="check_join")
async def check_join(call: types.CallbackQuery):
    joined = await check_user_joined(call.from_user.id)
    if joined:
        await call.message.edit_text("<b>Verified! ✅</b>\n\nYou need 5 points to unlock any 1 method.\nShare your referral link to earn points.", reply_markup=get_main_menu())
    else:
        await call.answer("❌ You haven't joined all channels yet!", show_alert=True)

@dp.callback_query_handler(text="my_ref")
async def my_ref(call: types.CallbackQuery):
    user = users.find_one({"_id": call.from_user.id})
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    
    text = (f"<b>👤 USER STATISTICS</b>\n\n"
            f"<b>Your Points:</b> {user['points']}\n"
            f"<b>Referral Link:</b>\n<code>{ref_link}</code>\n\n"
            f"<i>*Every 5 referrals = 1 Method Unlock*</i>")
    await call.message.answer(text)

@dp.callback_query_handler(text="view_methods")
async def view_methods(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    # Button Labels
    method_list = [
        "ChatGPT 1 Month Pro", "Ocoya Ai Method", "Youtube Premium", 
        "Disney+ Premium", "CapCut Pro", "Gemini Bin", 
        "Canva Pro Method", "Telegram Premium Method"
    ]
    
    for i, name in enumerate(method_list, 1):
        kb.add(InlineKeyboardButton(text=f"Unlock {name} (5 pts)", callback_data=f"unlock_{i}"))
    
    await call.message.answer("<b>Select a method to unlock:</b>\n(5 points will be deducted from your balance)", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('unlock_'))
async def process_unlock(call: types.CallbackQuery):
    method_id = call.data.split('_')[1]
    user = users.find_one({"_id": call.from_user.id})
    
    if user['points'] >= 5:
        method_data = methods_db.find_one({"m_id": method_id})
        if method_data:
            users.update_one({"_id": call.from_user.id}, {"$inc": {"points": -5}})
            # Copy the message (video/file/text) from Admin's storage
            await bot.copy_message(
                chat_id=call.from_user.id, 
                from_chat_id=ADMIN_ID, 
                message_id=method_data['msg_id']
            )
            await call.message.answer("<b>✅ Method Unlocked! Check above.</b>")
        else:
            await call.answer("❌ This method has not been uploaded by Admin yet.", show_alert=True)
    else:
        await call.answer(f"❌ Not enough points! You need 5. (Current: {user['points']})", show_alert=True)

# --- Admin Controls ---
@dp.message_handler(commands=['setmethod'], user_id=ADMIN_ID)
async def set_method_handler(message: types.Message):
    # Admin must reply to a video/file/text with: /setmethod 1
    m_id = message.get_args()
    if not m_id:
        return await message.reply("Please specify ID: <code>/setmethod 1</code>")
    
    if not message.reply_to_message:
        return await message.reply("Reply to the Video/File/Text you want to set for this method.")

    methods_db.update_one(
        {"m_id": m_id}, 
        {"$set": {"msg_id": message.reply_to_message.message_id}}, 
        upsert=True
    )
    await message.reply(f"✅ Method {m_id} updated successfully!")

@dp.message_handler(commands=['broadcast'], user_id=ADMIN_ID)
async def broadcast_msg(message: types.Message):
    msg_text = message.get_args()
    if not msg_text: return
    
    all_users = users.find()
    count = 0
    for u in all_users:
        try:
            await bot.send_message(u['_id'], msg_text)
            count += 1
        except: pass
    await message.reply(f"<b>Broadcast Completed!</b>\nSent to {count} users.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True)
        
