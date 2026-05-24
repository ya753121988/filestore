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

# [CRITICAL FIX] Python 3.10+ এবং Render/Koyeb-এর ইভেন্ট লুপ এরর ফিক্স
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# --- [ কনফিগারেশন ] ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
BOT_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-jet.vercel.app" # আপনার রেন্ডার লিঙ্ক এখানে দিন

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

# --- [ ডাটাবেস ও ইনিশিয়ালাইজেশন ] ---
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
users_col = db['users']
links_col = db['links']
settings_col = db['settings']

# Pyrogram Client (Memory storage ব্যবহার করা হয়েছে যাতে সেশন ফাইল এরর না দেয়)
tg_client = Client("StreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# --- [ সেটিংস ও হেল্পার ফাংশন ] ---
def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {"id": "bot_settings", "log_channel": None, "force_channels": [], "caption": "<b>{file_name}</b>"}
        settings_col.insert_one(default)
        return default
    return settings

def is_subscribed(user_id):
    settings = get_settings()
    for cid in settings.get('force_channels', []):
        try:
            member = bot.get_chat_member(cid, user_id)
            if member.status in ['left', 'kicked']: return False
        except: continue
    return True

def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url}, timeout=5)
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- [ ফাইল স্ট্রিমিং লজিক (WEB) ] ---
@app.route('/dl/<key>')
def stream_file(key):
    data = links_col.find_one({"key": key})
    if not data: return "File Not Found!", 404
    
    file_name = data.get('file_name', 'video.mp4')
    
    def generate():
        with tg_client:
            msg = tg_client.get_messages(data['log_channel'], data['msg_id'])
            for chunk in tg_client.stream_media(msg):
                yield chunk

    return Response(stream_with_context(generate()), headers={
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Type': 'application/octet-stream'
    })

# --- [ বটের মেইন হ্যান্ডলার ] ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{BOT_TOKEN}")
    return "<h1>Bot is Running Successfully!</h1>", 200

# --- [ বটের কমান্ডস ] ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    # ইউজার ডাটাবেসে সেভ
    if not users_col.find_one({"user_id": uid}):
        users_col.insert_one({"user_id": uid, "date": datetime.datetime.now()})

    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        if not is_subscribed(uid):
            settings = get_settings()
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, cid in enumerate(settings['force_channels'], 1):
                try:
                    chat = bot.get_chat(cid)
                    link = f"https://t.me/{chat.username}" if chat.username else bot.export_chat_invite_link(cid)
                    markup.add(types.InlineKeyboardButton(f"Join Channel {i} 📢", url=link))
                except: continue
            markup.add(types.InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{bot.get_me().username}?start={key}"))
            return bot.send_message(message.chat.id, "❌ ফাইলটি পেতে নিচের চ্যানেলে জয়েন করুন!", reply_markup=markup)

        data = links_col.find_one({"key": key})
        if data:
            bot.copy_message(message.chat.id, data['log_channel'], data['msg_id'])
            web_url = get_short_link(f"{WEB_URL}/dl/{key}")
            btn = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🌐 High Speed Web Download", url=web_url))
            bot.send_message(message.chat.id, "✅ ফাইল উপরে পাঠানো হয়েছে। ব্রাউজারে ডাউনলোড করতে নিচের বাটন ক্লিক করুন:", reply_markup=btn)
        return
    bot.send_message(message.chat.id, "👋 হ্যালো! আমাকে ফাইল পাঠান লিঙ্ক তৈরি করতে।")

# --- [ অ্যাডমিন প্যানেল ] ---

@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id != ADMIN_ID: return
    u_count = users_col.count_documents({})
    l_count = links_col.count_documents({})
    bot.reply_to(message, f"📊 **স্ট্যাটাস:**\n\n👤 মোট ইউজার: {u_count}\n📂 মোট ফাইল: {l_count}")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    msg = message.reply_to_message
    if not msg: return bot.reply_to(message, "মেসেজ রিপ্লাই দিয়ে কমান্ড দিন।")
    
    users = users_col.find({})
    success = 0
    bot.send_message(message.chat.id, "🚀 ব্রডকাস্ট শুরু হয়েছে...")
    for user in users:
        try:
            bot.copy_message(user['user_id'], message.chat.id, msg.message_id)
            success += 1
            time.sleep(0.1)
        except: continue
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট শেষ! সফল: {success}")

@bot.message_handler(commands=['log_cnl'])
def set_log(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"log_channel": cid}}, upsert=True)
        bot.reply_to(message, "✅ Log Channel আপডেট হয়েছে!")
    except: bot.reply_to(message, "ব্যবহার: `/log_cnl -100xxxxxxx`")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids = [int(i.strip()) for i in message.text.replace('/set_force', '').split(',')]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": ids}}, upsert=True)
        bot.reply_to(message, "✅ Force Join চ্যানেল সেট হয়েছে!")
    except: bot.reply_to(message, "ব্যবহার: `/set_force -1001, -1002`")

# --- [ ফাইল সেভিং লজিক ] ---

@bot.message_handler(content_types=['video', 'document', 'audio'])
def handle_docs(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    log_id = settings.get('log_channel')
    if not log_id: return bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")

    file_obj = message.video or message.document or message.audio
    f_name = getattr(file_obj, 'file_name', f"file_{int(time.time())}.mp4")
    key = str(uuid.uuid4())[:10]
    
    sent = bot.copy_message(log_id, message.chat.id, message.message_id)
    links_col.insert_one({
        "key": key, 
        "msg_id": sent.message_id, 
        "log_channel": log_id, 
        "file_name": f_name
    })

    tg_link = f"https://t.me/{bot.get_me().username}?start={key}"
    web_link = f"{WEB_URL}/dl/{key}"
    bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🤖 TG Link: `{tg_link}`\n\n🌐 Web Link: `{web_link}`", parse_mode="Markdown")

# --- [ সার্ভার রানিং ] ---
if __name__ == "__main__":
    # Pyrogram স্টার্ট
    tg_client.start()
    print(">>> Pyrogram Started Successfully!")
    
    # Flask রান (Render Port অনুযায়ী)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
