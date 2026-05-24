import os
import uuid
import asyncio
import requests
import telebot
import time
import datetime
import logging
from flask import Flask, request, Response, stream_with_context
from pymongo import MongoClient
from telebot import types
from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- [ কনফিগারেশন ] ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
BOT_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-eclu.onrender.com"

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

# --- [ ডাটাবেস সেটআপ ] ---
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
users_db = db['users']
links_db = db['links']
settings_db = db['settings']

# --- [ ইনিশিয়ালাইজেশন ] ---
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
# Pyrogram for high-speed streaming
tg_client = Client("StreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# --- [ সেটিংস ম্যানেজমেন্ট ] ---
def get_config():
    config = settings_db.find_one({"id": "master_config"})
    if not config:
        default = {
            "id": "master_config",
            "log_channel": None,
            "fsub_channels": [],
            "is_shortener": True,
            "custom_caption": "🏷 <b>File Name:</b> {file_name}\n\n📥 <i>Join our channel for more!</i>",
            "maintenance": False
        }
        settings_db.insert_one(default)
        return default
    return config

# --- [ হেল্পার ফাংশন ] ---
def is_subscribed(user_id):
    config = get_config()
    for channel in config.get('fsub_channels', []):
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']: return False
        except: continue
    return True

def get_short_link(long_url):
    config = get_config()
    if not config.get('is_shortener'): return long_url
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url}, timeout=8)
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- [ Flask Streaming Engine ] ---
@app.route('/dl/<key>')
def stream_handler(key):
    file_data = links_db.find_one({"key": key})
    if not file_data: return "File not found or deleted!", 404
    
    def stream_gen():
        with tg_client:
            media_msg = tg_client.get_messages(file_data['log_channel'], file_data['msg_id'])
            for chunk in tg_client.stream_media(media_msg):
                yield chunk

    return Response(
        stream_with_context(stream_gen()),
        headers={
            'Content-Disposition': f'attachment; filename="{file_data.get("file_name", "video.mp4")}"',
            'Content-Type': 'application/octet-stream'
        }
    )

@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_update():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def status():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{BOT_TOKEN}")
    return "<h1>Multi-Feature File Store Bot is Running!</h1>", 200

# --- [ বটের মেইন ফিচার ও কমান্ডস ] ---

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    # ইউজার রেকর্ড আপডেট
    if not users_db.find_one({"user_id": user_id}):
        users_db.insert_one({"user_id": user_id, "date": datetime.datetime.now(), "ban": False})

    # মেইনটেন্যান্স চেক
    config = get_config()
    if config['maintenance'] and user_id != ADMIN_ID:
        return bot.send_message(message.chat.id, "🛠 <b>বট এখন মেইনটেন্যান্স মোডে আছে। কিছুক্ষণ পর চেষ্টা করুন।</b>", parse_mode="HTML")

    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        # Force Join চেক
        if not is_subscribed(user_id):
            markup = types.InlineKeyboardMarkup()
            for i, c in enumerate(config['fsub_channels'], 1):
                try:
                    chat = bot.get_chat(c)
                    markup.add(types.InlineKeyboardButton(f"Join Channel {i} 📢", url=f"https://t.me/{chat.username}"))
                except: continue
            markup.add(types.InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{bot.get_me().username}?start={key}"))
            return bot.send_message(message.chat.id, "❌ <b>ফাইলটি পেতে আপনাকে আমাদের চ্যানেলে জয়েন করতে হবে!</b>", reply_markup=markup, parse_mode="HTML")

        # ফাইল ডাটাবেস থেকে খোঁজা
        data = links_db.find_one({"key": key})
        if data:
            # ফাইল কপি পাঠানো
            caption = config.get('custom_caption', '').format(file_name=data['file_name'])
            bot.copy_message(message.chat.id, data['log_channel'], data['msg_id'], caption=caption, parse_mode="HTML")
            
            # ওয়েব লিঙ্ক জেনারেট
            raw_url = f"{WEB_URL}/dl/{key}"
            web_url = get_short_link(raw_url)
            btn = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🌐 Watch/Download Online", url=web_url))
            bot.send_message(message.chat.id, "⬇️ <b>নিচের বাটন থেকে হাই-স্পিড ডাউনলোড করতে পারেন:</b>", reply_markup=btn, parse_mode="HTML")
        return

    bot.send_message(message.chat.id, "👋 <b>হ্যালো! আমি একটি ফাইল স্টোর বট।</b>\nযেকোনো ফাইলের লিঙ্ক তৈরি করতে আমাকে ফাইল পাঠান।", parse_mode="HTML")

# --- [ অ্যাডমিন প্যানেল কমান্ডস ] ---

@bot.message_handler(commands=['admin', 'panel'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="broadcast"),
        types.InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        types.InlineKeyboardButton("🛠 Maintenance", callback_data="toggle_mt")
    )
    bot.send_message(message.chat.id, "🕹 <b>Welcome to Admin Control Panel:</b>", reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    u_count = users_db.count_documents({})
    l_count = links_db.count_documents({})
    bot.reply_to(message, f"📈 <b>বট পরিসংখ্যান:</b>\n\n👥 মোট ইউজার: {u_count}\n📂 মোট ফাইল: {l_count}", parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    msg = message.reply_to_message
    if not msg: return bot.reply_to(message, "মেসেজ রিপ্লাই দিয়ে কমান্ডটি দিন।")
    
    users = users_db.find({})
    count = 0
    bot.send_message(message.chat.id, "🚀 ব্রডকাস্ট শুরু হয়েছে...")
    for user in users:
        try:
            bot.copy_message(user['user_id'], message.chat.id, msg.message_id)
            count += 1
            time.sleep(0.1) # FloodWait এড়াতে
        except: continue
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট সম্পন্ন! মোট পেয়েছেন: {count} জন।")

@bot.message_handler(commands=['log_cnl'])
def set_log(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_db.update_one({"id": "master_config"}, {"$set": {"log_channel": cid}})
        bot.reply_to(message, f"✅ Log Channel সেট হয়েছে: `{cid}`", parse_mode="Markdown")
    except: bot.reply_to(message, "সঠিক আইডি দিন।")

@bot.message_handler(commands=['add_fsub'])
def add_fsub(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_db.update_one({"id": "master_config"}, {"$push": {"fsub_channels": cid}})
        bot.reply_to(message, "✅ Force Join চ্যানেল যোগ হয়েছে।")
    except: bot.reply_to(message, "ব্যবহার: `/add_fsub -100xxxxxxx`")

# --- [ ফাইল হ্যান্ডলিং ও সেভিং ] ---

@bot.message_handler(content_types=['video', 'document', 'audio', 'photo'])
def file_receiver(message):
    if message.from_user.id != ADMIN_ID: return
    config = get_config()
    if not config['log_channel']: return bot.reply_to(message, "❌ আগে `/log_cnl` সেট করুন।")

    file_obj = message.video or message.document or message.audio or (message.photo[-1] if message.photo else None)
    file_name = getattr(file_obj, 'file_name', f"File_{int(time.time())}.jpg")
    
    key = str(uuid.uuid4())[:10]
    
    # লগ চ্যানেলে কপি পাঠানো
    sent = bot.copy_message(config['log_channel'], message.chat.id, message.message_id)
    
    # ডাটাবেসে সেভ
    links_db.insert_one({
        "key": key,
        "msg_id": sent.message_id,
        "log_channel": config['log_channel'],
        "file_name": file_name,
        "user_id": message.from_user.id
    })

    bot_user = bot.get_me().username
    tg_link = f"https://t.me/{bot_user}?start={key}"
    web_link = f"{WEB_URL}/dl/{key}"
    
    res_text = (
        f"✅ <b>File Successfully Saved!</b>\n\n"
        f"📂 <b>Name:</b> <code>{file_name}</code>\n\n"
        f"🤖 <b>Bot Link:</b> <code>{tg_link}</code>\n\n"
        f"🌐 <b>Web Link:</b> <code>{web_link}</code>"
    )
    bot.reply_to(message, res_text, parse_mode="HTML")

# --- [ সার্ভার রানিং লজিক ] ---
if __name__ == "__main__":
    # Pyrogram সেশন স্টার্ট (এটি স্ট্রিমিং এর জন্য মাস্ট)
    tg_client.start()
    print("Pyrogram Client Started!")
    
    # Flask রান
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
