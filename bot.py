import asyncio
import os
import sys
import uuid
import time
import datetime
import requests
import telebot
from flask import Flask, request, Response, stream_with_context
from pymongo import MongoClient
from telebot import types
from pyrogram import Client
from pyrogram.errors import FloodWait

# [CRITICAL FIX] Python 3.10+ এবং Render-এর Event Loop এরর সমাধান
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ================= [ আপনার কনফিগারেশন ] =================
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
BOT_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-eclu.onrender.com"

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"
# ========================================================

# --- [ ডাটাবেস সেটআপ ] ---
db_client = MongoClient(MONGO_URI)
db = db_client['DramaStoreDB']
users_col = db['users']
links_col = db['links']
settings_col = db['settings']

# --- [ বট ইনিশিয়ালাইজেশন ] ---
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
tg_client = Client("MegaStreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# --- [ সেটিংস ম্যানেজার ] ---
def get_config():
    config = settings_col.find_one({"id": "master_config"})
    if not config:
        default = {
            "id": "master_config",
            "log_channel": None,
            "fsub_channels": [],
            "is_shortener": True,
            "maintenance": False,
            "custom_caption": "<b>{file_name}</b>"
        }
        settings_col.insert_one(default)
        return default
    return config

# --- [ সাবস্ক্রিপশন চেক ] ---
def check_fsub(user_id):
    config = get_config()
    for channel in config.get('fsub_channels', []):
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']: return False
        except: continue
    return True

# --- [ লিঙ্ক শর্টনার ] ---
def get_short(long_url):
    config = get_config()
    if not config.get('is_shortener'): return long_url
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url}, timeout=8)
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- [ ফাইল স্ট্রিমিং ইঞ্জিন ] ---
@app.route('/dl/<key>')
def stream_file(key):
    data = links_col.find_one({"key": key})
    if not data: return "File not found!", 404
    
    def generate():
        with tg_client:
            msg = tg_client.get_messages(data['log_channel'], data['msg_id'])
            for chunk in tg_client.stream_media(msg):
                yield chunk

    return Response(stream_with_context(generate()), headers={
        'Content-Disposition': f'attachment; filename="{data.get("file_name", "video.mp4")}"',
        'Content-Type': 'application/octet-stream'
    })

# --- [ বটের মেইন হ্যান্ডলার ] ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return '', 200

@app.route('/')
def home():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{BOT_TOKEN}")
    return "<h1>Mega File Store Bot is Running!</h1>", 200

# --- [ ইউজার কমান্ডস ] ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    config = get_config()
    
    # ইউজার সেভ
    if not users_col.find_one({"user_id": uid}):
        users_col.insert_one({"user_id": uid, "date": datetime.datetime.now(), "ban": False})

    # মেইনটেন্যান্স চেক
    if config['maintenance'] and uid != ADMIN_ID:
        return bot.send_message(message.chat.id, "🚧 <b>বট এখন মেইনটেন্যান্স মোডে আছে।</b>", parse_mode="HTML")

    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        if not check_fsub(uid):
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, cid in enumerate(config['fsub_channels'], 1):
                try:
                    chat = bot.get_chat(cid)
                    markup.add(types.InlineKeyboardButton(f"Join Channel {i} 📢", url=f"https://t.me/{chat.username}"))
                except: continue
            markup.add(types.InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{bot.get_me().username}?start={key}"))
            return bot.send_message(message.chat.id, "❌ <b>ফাইলটি পেতে আপনাকে আমাদের চ্যানেলে জয়েন করতে হবে!</b>", reply_markup=markup, parse_mode="HTML")

        file_data = links_col.find_one({"key": key})
        if file_data:
            caption = config['custom_caption'].format(file_name=file_data['file_name'])
            bot.copy_message(message.chat.id, file_data['log_channel'], file_data['msg_id'], caption=caption, parse_mode="HTML")
            
            w_url = get_short(f"{WEB_URL}/dl/{key}")
            btn = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🌐 High Speed Download (Web)", url=w_url))
            bot.send_message(message.chat.id, "⬇️ <b>ব্রাউজারে ডাউনলোড করতে নিচের বাটনটি ব্যবহার করুন:</b>", reply_markup=btn, parse_mode="HTML")
        return

    bot.send_message(message.chat.id, "👋 <b>স্বাগতম! আমাকে ফাইল পাঠান লিঙ্ক তৈরি করতে।</b>", parse_mode="HTML")

# --- [ অ্যাডমিন কমান্ডস ও প্যানেল ] ---

@bot.message_handler(commands=['admin', 'panel'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="b_cast"),
        types.InlineKeyboardButton("⚙️ Settings", callback_data="set_menu"),
        types.InlineKeyboardButton("🛠 Maintenance", callback_data="toggle_mt")
    )
    bot.send_message(message.chat.id, "🛠 <b>Admin Control Panel:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.from_user.id != ADMIN_ID: return
    config = get_config()
    
    if call.data == "stats":
        u = users_col.count_documents({})
        l = links_col.count_documents({})
        bot.answer_callback_query(call.id, "Stats Loaded")
        bot.edit_message_text(f"📊 **Statistics:**\n\n👤 Total Users: {u}\n📂 Total Files: {l}", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "toggle_mt":
        new_val = not config['maintenance']
        settings_col.update_one({"id": "master_config"}, {"$set": {"maintenance": new_val}})
        bot.answer_callback_query(call.id, f"Maintenance: {'ON' if new_val else 'OFF'}")
        bot.edit_message_text(f"⚙️ Maintenance mode is now {'ON' if new_val else 'OFF'}", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    msg = message.reply_to_message
    if not msg: return bot.reply_to(message, "মেসেজ রিপ্লাই দিয়ে কমান্ডটি দিন।")
    
    users = users_col.find({})
    success = 0
    bot.send_message(message.chat.id, "🚀 ব্রডকাস্ট শুরু হয়েছে...")
    for user in users:
        try:
            bot.copy_message(user['user_id'], message.chat.id, msg.message_id)
            success += 1
            time.sleep(0.05)
        except: continue
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট শেষ! মোট: {success}")

@bot.message_handler(commands=['log_cnl'])
def set_log(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "master_config"}, {"$set": {"log_channel": cid}}, upsert=True)
        bot.reply_to(message, "✅ Log Channel Updated!")
    except: bot.reply_to(message, "Error: Use `/log_cnl -100xxxx`")

@bot.message_handler(commands=['add_fsub'])
def add_fsub(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "master_config"}, {"$push": {"fsub_channels": cid}})
        bot.reply_to(message, "✅ Channel Added to Force Join!")
    except: pass

@bot.message_handler(commands=['del_fsub'])
def del_fsub(message):
    if message.from_user.id != ADMIN_ID: return
    settings_col.update_one({"id": "master_config"}, {"$set": {"fsub_channels": []}})
    bot.reply_to(message, "✅ Force Join List Cleared!")

# --- [ ফাইল সেভিং লজিক ] ---

@bot.message_handler(content_types=['video', 'document', 'audio', 'photo'])
def handle_incoming_files(message):
    if message.from_user.id != ADMIN_ID: return
    config = get_config()
    if not config['log_channel']: return bot.reply_to(message, "❌ আগে `/log_cnl` সেট করুন।")

    file_obj = message.video or message.document or message.audio or (message.photo[-1] if message.photo else None)
    file_name = getattr(file_obj, 'file_name', f"File_{int(time.time())}")
    key = str(uuid.uuid4())[:10]
    
    sent = bot.copy_message(config['log_channel'], message.chat.id, message.message_id)
    links_col.insert_one({
        "key": key,
        "msg_id": sent.message_id,
        "log_channel": config['log_channel'],
        "file_name": file_name
    })

    tg_link = f"https://t.me/{bot.get_me().username}?start={key}"
    web_link = f"{WEB_URL}/dl/{key}"
    
    bot.reply_to(message, f"✅ **Saved!**\n\n🤖 Link: `{tg_link}`\n\n🌐 Web: `{web_link}`", parse_mode="Markdown")

# --- [ স্টার্ট সার্ভার ] ---
if __name__ == "__main__":
    # Pyrogram স্টার্ট
    tg_client.start()
    print(">>> Pyrogram Streamer Online")
    
    # Flask সার্ভার রান
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
