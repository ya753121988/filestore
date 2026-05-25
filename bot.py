import os
import telebot
import uuid
import requests
import threading
import time
from flask import Flask, request
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী) ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-jet.vercel.app"

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

# বট ও ডাটাবেস ইনিশিয়ালাইজ
bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
links_col = db['links']
settings_col = db['settings']
users_col = db['users'] # ব্রডকাস্টের জন্য ইউজার ডাটাবেস

def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {
            "id": "bot_settings", 
            "log_channel": None, 
            "send_channel": None, 
            "force_channels": [],
            "logo_url": "https://telegra.ph/file/default-logo.jpg"
        }
        settings_col.insert_one(default)
        return default
    return settings

# --- বাটন জেনারেটর ---
def get_channel_buttons(extra_buttons=None):
    settings = get_settings()
    channels = settings.get('force_channels', [])
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    for i, cid in enumerate(channels, 1):
        try:
            chat = bot.get_chat(cid)
            link = f"https://t.me/{chat.username}" if chat.username else bot.export_chat_invite_link(cid)
            btns.append(types.InlineKeyboardButton(f"Join Channel {i} 📢", url=link))
        except: continue
    
    if btns:
        markup.add(*btns)
    
    if extra_buttons:
        for b in extra_buttons:
            markup.add(b)
    return markup

# --- লিঙ্ক শর্টনার ---
def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url})
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- বটের কমান্ডস ও ফিচারস ---

@bot.message_handler(commands=['start'])
def start(message):
    # ইউজার সেভ করা ব্রডকাস্টের জন্য
    if not users_col.find_one({"user_id": message.from_user.id}):
        users_col.insert_one({"user_id": message.from_user.id})

    settings = get_settings()
    args = message.text.split()
    
    # ফাইল রিকোয়েস্ট হ্যান্ডেলিং
    if len(args) > 1:
        data = links_col.find_one({"key": args[1]})
        if data and settings.get('send_channel'):
            # ফাইল কপি করার সময় বাটন সহ পাঠানো (ইউজার চ্যানেলে)
            btn_tg = types.InlineKeyboardButton("🚀 Watch on Telegram", url=f"https://t.me/{bot.get_me().username}?start={args[1]}")
            markup = get_channel_buttons([btn_tg])
            
            sent = bot.copy_message(settings['send_channel'], data['log_channel'], data['msg_id'], reply_markup=markup)
            
            c_info = bot.get_chat(settings['send_channel'])
            m_link = f"https://t.me/{c_info.username}/{sent.message_id}" if c_info.username else f"https://t.me/c/{str(settings['send_channel']).replace('-100','')}/{sent.message_id}"
            
            bot.send_message(message.chat.id, "✅ ফাইল আপনার চ্যানেলে পাঠানো হয়েছে।", reply_markup=get_channel_buttons())
        return

    # সাধারণ স্টার্ট মেসেজ
    user = message.from_user
    full_name = f"{user.first_name} {user.last_name or ''}"
    start_text = (
        f"👋 স্বাগতম, **{full_name}**\n\n"
        f"🆔 **ইউজার আইডি:** `{user.id}`\n"
        f"👤 **ইউজার নেম:** @{user.username or 'N/A'}\n"
        f"📛 **ফার্স্ট নেম:** {user.first_name}\n"
        f"📛 **লাস্ট নেম:** {user.last_name or 'N/A'}\n\n"
        "নিচের চ্যানেলগুলোতে জয়েন করে ফাইল রিসিভ করুন।"
    )
    
    try:
        bot.send_photo(message.chat.id, settings.get('logo_url'), caption=start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")

# --- এডমিন প্যানেল ---

@bot.message_handler(commands=['set_logo'])
def set_logo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_logo = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"logo_url": new_logo}}, upsert=True)
        bot.reply_to(message, "✅ বটের লগো আপডেট হয়েছে!")
    except:
        bot.reply_to(message, "সঠিকভাবে কমান্ড দিন: `/set_logo URL`")

@bot.message_handler(commands=['status'])
def status(message):
    if message.from_user.id != ADMIN_ID: return
    total_users = users_col.count_documents({})
    total_files = links_col.count_documents({})
    bot.reply_to(message, f"📊 **বট স্ট্যাটাস:**\n\n👥 মোট ইউজার: {total_users}\n📁 মোট ফাইল লিঙ্ক: {total_files}", parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message:
        return bot.reply_to(message, "যে মেসেজটি ব্রডকাস্ট করতে চান সেটি রিপ্লাই দিন।")
    
    users = users_col.find({})
    count = 0
    for user in users:
        try:
            bot.copy_message(user['user_id'], message.chat.id, message.reply_to_message.message_id)
            count += 1
            time.sleep(0.1) # টেলিগ্রাম লিমিট এড়াতে
        except: continue
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট সম্পন্ন! {count} জন ইউজারের কাছে পাঠানো হয়েছে।")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids = [int(i.strip()) for i in message.text.replace('/set_force','').split(',')]
        curr = get_settings().get('force_channels', [])
        new = list(set(curr + ids))
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": new}}, upsert=True)
        bot.reply_to(message, "✅ চ্যানেলগুলো যোগ হয়েছে।")
    except: bot.reply_to(message, "সঠিক আইডি দিন।")

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def admin_set_cnl(message):
    if message.from_user.id != ADMIN_ID: return
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} আপডেট হয়েছে!")
    except: pass

# --- সব ধরণের ফাইল হ্যান্ডলিং (Video, Audio, Photo, Document) ---

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo', 'voice', 'animation'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'): return bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")

    file_id = ""
    file_name = "File"
    
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        file_name = "Photo"
    elif message.content_type == 'video':
        file_id = message.video.file_id
        file_name = getattr(message.video, 'file_name', 'Video')
    elif message.content_type == 'document':
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.content_type == 'audio':
        file_id = message.audio.file_id
        file_name = getattr(message.audio, 'file_name', 'Audio')
    else:
        # voice/animation
        file_id = message.voice.file_id if message.voice else message.animation.file_id
        file_name = "Media File"

    key = str(uuid.uuid4())[:8]
    tg_link = get_short_link(f"https://t.me/{bot.get_me().username}?start={key}")

    # বাটন তৈরি (লগ চ্যানেল এবং ইউজার চ্যানেলের জন্য)
    btn_tg = types.InlineKeyboardButton("🤖 Bot Link", url=tg_link)
    markup = get_channel_buttons([btn_tg])

    # লগ চ্যানেলে ফাইল পাঠানো
    sent = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id, reply_markup=markup)
    
    # ডাটাবেসে তথ্য রাখা
    links_col.insert_one({
        "key": key, 
        "msg_id": sent.message_id, 
        "log_channel": settings['log_channel'],
        "file_id": file_id,
        "file_name": file_name
    })

    bot.reply_to(message, f"✅ **ফাইল লিঙ্ক তৈরি হয়েছে!**\n\n🤖 TG লিঙ্ক: `{tg_link}`", 
                 reply_markup=markup, parse_mode="Markdown")

# --- বট সচল রাখার মেকানিজম (Keep Alive) ---
def keep_alive():
    while True:
        try:
            requests.get(WEB_URL)
            time.sleep(600) # প্রতি ১০ মিনিটে একবার পিং করবে
        except: pass

# --- ফ্লাস্ক ও সার্ভার ---
@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "<h1>Bot is Running...</h1>", 200

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
