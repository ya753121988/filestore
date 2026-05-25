import os
import telebot
import uuid
import requests
import threading
import time
from flask import Flask, request
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-jet.vercel.app" # আপনার Vercel/Render URL

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
users_col = db['users']

# ডিফল্ট সেটিংস লোড
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

# --- লিঙ্ক শর্টনার ফাংশন ---
def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url}, timeout=10)
        data = res.json()
        if data.get('status') == 'success':
            return data.get('shortenedUrl')
        return long_url
    except:
        return long_url

# --- কমান্ড হ্যান্ডলার ---

@bot.message_handler(commands=['start'])
def start(message):
    # নতুন ইউজার সেভ (ব্রডকাস্টের জন্য)
    if not users_col.find_one({"user_id": message.from_user.id}):
        users_col.insert_one({"user_id": message.from_user.id})

    settings = get_settings()
    args = message.text.split()
    
    # যদি স্টার্ট লিঙ্কে ফাইল কি (Key) থাকে
    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        
        if data:
            if settings.get('send_channel'):
                # ইউজার চ্যানেলে ফাইল কপি করে পাঠানো
                bot_link = f"https://t.me/{bot.get_me().username}?start={key}"
                # ইউজার চ্যানেলের বাটন
                u_btn = types.InlineKeyboardButton("🤖 Bot Link", url=get_short_link(bot_link))
                markup = get_channel_buttons([u_btn])
                
                try:
                    bot.copy_message(settings['send_channel'], data['log_channel'], data['msg_id'], reply_markup=markup)
                    bot.send_message(message.chat.id, "✅ ফাইলটি ইউজার চ্যানেলে পাঠানো হয়েছে। দয়া করে চেক করুন।", reply_markup=get_channel_buttons())
                except Exception as e:
                    bot.send_message(message.chat.id, f"❌ ভুল: {str(e)}")
            else:
                bot.send_message(message.chat.id, "❌ এডমিন এখনো 'Send Channel' সেট করেনি।")
        else:
            bot.send_message(message.chat.id, "❌ দুঃখিত, ফাইলটি খুঁজে পাওয়া যায়নি।")
        return

    # সাধারণ স্টার্ট মেসেজ
    user = message.from_user
    start_text = (
        f"👋 হ্যালো, **{user.first_name}**\n\n"
        f"🆔 ইউজার আইডি: `{user.id}`\n"
        f"👤 ইউজার নাম: {user.first_name} {user.last_name or ''}\n"
        f"👤 ইউজারনেম: @{user.username or 'N/A'}\n\n"
        "ফাইল পেতে নিচের বাটন থেকে চ্যানেলে জয়েন করুন।"
    )
    
    try:
        bot.send_photo(message.chat.id, settings.get('logo_url'), caption=start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")

# --- এডমিন কমান্ডস ---

@bot.message_handler(commands=['set_logo'])
def set_logo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        url = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"logo_url": url}}, upsert=True)
        bot.reply_to(message, "✅ লগো সফলভাবে সেট করা হয়েছে।")
    except:
        bot.reply_to(message, "ব্যবহার: `/set_logo URL_LINK`")

@bot.message_handler(commands=['status'])
def status(message):
    if message.from_user.id != ADMIN_ID: return
    u_count = users_col.count_documents({})
    f_count = links_col.count_documents({})
    bot.reply_to(message, f"📊 **বট স্ট্যাটাস**\n\n👥 মোট ইউজার: {u_count}\n📁 মোট ফাইল: {f_count}", parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message:
        return bot.reply_to(message, "যে মেসেজটি পাঠাতে চান সেটি রিপ্লাই দিয়ে লিখুন `/broadcast`")
    
    users = users_col.find({})
    success = 0
    for u in users:
        try:
            bot.copy_message(u['user_id'], message.chat.id, message.reply_to_message.message_id)
            success += 1
            time.sleep(0.2)
        except: continue
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট শেষ! {success} জন ইউজারকে পাঠানো হয়েছে।")

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def set_channels(message):
    if message.from_user.id != ADMIN_ID: return
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} আপডেট হয়েছে: `{cid}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "সঠিক আইডি দিন। উদাহরণ: `/log_cnl -100xxxxxxx`")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids = [int(i.strip()) for i in message.text.replace('/set_force','').split(',')]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": ids}}, upsert=True)
        bot.reply_to(message, "✅ ফোর্স সাবস্ক্রাইব চ্যানেল আপডেট হয়েছে।")
    except:
        bot.reply_to(message, "কমা দিয়ে আইডি দিন। উদাহরণ: `/set_force -1001, -1002`")

# --- ফাইল হ্যান্ডলিং (সব ফাইল সাপোর্ট) ---

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo', 'voice', 'animation'])
def handle_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'):
        return bot.reply_to(message, "❌ আগে `/log_cnl` দিয়ে লগ চ্যানেল সেট করুন।")

    # ফাইল টাইপ এবং আইডি বের করা
    file_id = ""
    if message.photo: file_id = message.photo[-1].file_id
    elif message.video: file_id = message.video.file_id
    elif message.document: file_id = message.document.file_id
    elif message.audio: file_id = message.audio.file_id
    elif message.voice: file_id = message.voice.file_id
    elif message.animation: file_id = message.animation.file_id

    key = str(uuid.uuid4())[:8]
    raw_link = f"https://t.me/{bot.get_me().username}?start={key}"
    short_link = get_short_link(raw_link)

    # বাটন তৈরি
    btn = types.InlineKeyboardButton("🤖 Bot Link", url=short_link)
    markup = get_channel_buttons([btn])

    # লগ চ্যানেলে পাঠানো
    try:
        sent_log = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id, reply_markup=markup)
        
        # ডাটাবেসে সেভ
        links_col.insert_one({
            "key": key,
            "msg_id": sent_log.message_id,
            "log_channel": settings['log_channel'],
            "file_id": file_id
        })

        bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🔗 সর্ট লিঙ্ক: `{short_link}`", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"❌ এরর: {str(e)}")

# --- সার্ভার সেটআপ ---

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "Bot is Running Live!", 200

if __name__ == "__main__":
    # বট সচল রাখতে আলাদা থ্রেড
    def run_bot():
        while True:
            try:
                app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
            except:
                time.sleep(5)
    
    threading.Thread(target=run_bot).start()
