import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Config
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MONGO_URL = os.getenv('MONGO_URL')
CHANNELS = os.getenv('CHANNELS').split(',')

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

# --- Referral & Start Logic ---
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
            try: await bot.send_message(referrer, "<b>🎉 New Referral! +1 Point</b>")
            except: pass
    await message.answer("<b>Welcome! Join our channels to continue:</b>", reply_markup=get_start_kb())

@dp.callback_query_handler(text="check_join")
async def check_join(call: types.CallbackQuery):
    await call.message.edit_text("<b>Verified! ✅</b>\nChoose an option:", reply_markup=get_main_menu())

@dp.callback_query_handler(text="my_ref")
async def my_ref(call: types.CallbackQuery):
    user = users.find_one({"_id": call.from_user.id})
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    await call.message.answer(f"<b>Your Points:</b> {user['points']}\n<b>Link:</b> <code>{ref_link}</code>")

@dp.callback_query_handler(text="view_methods")
async def view_methods(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    method_list = ["ChatGPT Pro", "Youtube Premium", "Netflix", "Canva Pro", "Telegram Premium", "VPN Method", "Dev Club", "Framer Pro"]
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
            # This will copy the exact message (video/file/text) you saved
            await bot.copy_message(chat_id=call.from_user.id, from_chat_id=ADMIN_ID, message_id=method_data['msg_id'])
            await call.message.answer("<b>✅ Method Unlocked!</b>")
        else:
            await call.answer("❌ This method is empty.", show_alert=True)
    else:
        await call.answer(f"❌ Need 5 points. You have {user['points']}", show_alert=True)

# --- Admin Content Upload ---
@dp.message_handler(commands=['setmethod'], user_id=ADMIN_ID)
async def set_method_cmd(message: types.Message):
    try:
        m_id = message.get_args()
        if not m_id: return await message.reply("Format: Reply to a Video/File with <code>/setmethod 1</code>")
        
        if not message.reply_to_message:
            return await message.reply("<b>Error:</b> Please <b>Reply</b> to the Video, File, or Text you want to set as this method.")

        # Save the Message ID from the admin's chat
        methods_db.update_one({"m_id": m_id}, {"$set": {"msg_id": message.reply_to_message.message_id}}, upsert=True)
        await message.reply(f"✅ Method {m_id} saved successfully!")
    except Exception as e:
        await message.reply(f"Error: {e}")

@dp.message_handler(commands=['broadcast'], user_id=ADMIN_ID)
async def broadcast(message: types.Message):
    msg_args = message.get_args()
    if not msg_args: return
    all_users = users.find()
    for u in all_users:
        try: await bot.send_message(u['_id'], msg_args)
        except: pass
    await message.reply("Broadcast Done!")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
    
