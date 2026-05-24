import os
import telebot
import uuid
import requests
import asyncio
from flask import Flask, request, Response, stream_with_context
from pymongo import MongoClient
from telebot import types
from pyrogram import Client

# --- কনফিগারেশন ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-eclu.onrender.com" # আপনার বর্তমান অ্যাপ ইউআরএল

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

# বট ও ডাটাবেস ইনিশিয়ালাইজ
bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
links_col = db['links']
settings_col = db['settings']

# Pyrogram Client (বড় ফাইল স্ট্রিমিংয়ের জন্য)
tg_client = Client("stream_bot", api_id=API_ID, api_hash=API_HASH, bot_token=API_TOKEN)

def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {"id": "bot_settings", "log_channel": None, "send_channel": None, "force_channels": []}
        settings_col.insert_one(default)
        return default
    return settings

# --- লিঙ্ক শর্টনার ফাংশন ---
def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url})
        data = res.json()
        if data.get('status') == 'success':
            return data.get('shortenedUrl')
        return long_url
    except:
        return long_url

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
        except:
            continue
    markup.add(*btns)
    if extra_buttons:
        for b in extra_buttons:
            markup.add(b)
    return markup

# --- ফাইল স্ট্রিমিং রুট (ডাউনলোড লজিক) ---
@app.route("/dl/<key>")
def stream_file(key):
    data = links_col.find_one({"key": key})
    if not data:
        return "File not found!", 404
    
    file_name = data.get('file_name', 'video_file.mp4')
    
    def generate():
        # Pyrogram সেশন ব্যবহার করে ফাইল স্ট্রিম করা
        with tg_client:
            msg = tg_client.get_messages(data['log_channel'], data['msg_id'])
            for chunk in tg_client.stream_media(msg):
                yield chunk

    return Response(
        stream_with_context(generate()),
        headers={
            'Content-Disposition': f'attachment; filename="{file_name}"',
            'Content-Type': 'application/octet-stream'
        }
    )

# --- বটের মূল কমান্ডসমূহ ---

@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    settings = get_settings()

    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        
        if data:
            web_link = get_short_link(f"{WEB_URL}/dl/{key}")
            
            # ইউজার চ্যানেলের জন্য বাটন তৈরি (লাল টিক সমাধান)
            btn_browser = types.InlineKeyboardButton("🌐 Browser Download", url=web_link)
            user_markup = get_channel_buttons([btn_browser])

            # যদি সেন্ড চ্যানেল সেট করা থাকে তবে সেখানে ফাইল কপি হবে বাটনসহ
            if settings.get('send_channel'):
                try:
                    sent = bot.copy_message(
                        chat_id=settings['send_channel'],
                        from_chat_id=data['log_channel'],
                        message_id=data['msg_id'],
                        reply_markup=user_markup # এখানে বাটন যুক্ত করা হয়েছে
                    )
                    
                    # ইনবক্সে ইউজারকে মেসেজ দেওয়া
                    c_info = bot.get_chat(settings['send_channel'])
                    if c_info.username:
                        tg_file_link = f"https://t.me/{c_info.username}/{sent.message_id}"
                    else:
                        tg_file_link = f"https://t.me/c/{str(settings['send_channel']).replace('-100','')}/{sent.message_id}"
                    
                    btn_watch = types.InlineKeyboardButton("🚀 Telegram Link", url=tg_file_link)
                    bot.send_message(
                        message.chat.id, 
                        "✅ আপনার ফাইলটি প্রস্তুত। নিচের বাটনগুলো দেখুন:", 
                        reply_markup=get_channel_buttons([btn_watch, btn_browser])
                    )
                except Exception as e:
                    bot.send_message(message.chat.id, f"Error copying message: {e}")
            else:
                bot.send_message(message.chat.id, "Send Channel নট সেট। অ্যাডমিনকে জানান।")
        return

    bot.send_message(message.chat.id, "স্বাগতম! চ্যানেলগুলোতে জয়েন করে সার্ভিসটি ব্যবহার করুন।", reply_markup=get_channel_buttons())

# --- অ্যাডমিন কন্ট্রোলস ---

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def set_channels(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cmd = message.text.split()
        key = "log_channel" if "log" in cmd[0] else "send_channel"
        cid = int(cmd[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} সফলভাবে সেট হয়েছে: {cid}")
    except:
        bot.reply_to(message, "সঠিক ফরম্যাট: `/log_cnl -100xxxxxx` অথবা `/send_cnl -100xxxxxx`", parse_mode="Markdown")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids = [int(i.strip()) for i in message.text.replace('/set_force','').split(',') if i.strip()]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": ids}}, upsert=True)
        bot.reply_to(message, "✅ Force Subscribe চ্যানেলগুলো আপডেট হয়েছে।")
    except:
        bot.reply_to(message, "ভুল ইনপুট! আইডিগুলো কমা দিয়ে লিখুন।")

# --- ফাইল হ্যান্ডলিং (অ্যাডমিন ফাইল পাঠালে) ---

@bot.message_handler(content_types=['document', 'video', 'audio'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    
    settings = get_settings()
    if not settings.get('log_channel'):
        return bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")

    file_obj = message.document or message.video or message.audio
    file_name = getattr(file_obj, 'file_name', 'video.mp4')
    
    # ইউনিক আইডি জেনারেট
    key = str(uuid.uuid4())[:8]
    
    # লিংকগুলো তৈরি করা
    bot_user = bot.get_me().username
    tg_short_link = get_short_link(f"https://t.me/{bot_user}?start={key}")
    web_short_link = get_short_link(f"{WEB_URL}/dl/{key}")

    # লগ চ্যানেলের জন্য বাটন (সবুজ টিক সমাধান)
    btn_bot = types.InlineKeyboardButton("🤖 Bot Link", url=tg_short_link)
    btn_web = types.InlineKeyboardButton("🌐 Direct Web Download", url=web_short_link)
    log_markup = get_channel_buttons([btn_bot, btn_web])

    # লগ চ্যানেলে ফাইল পাঠানো
    sent = bot.copy_message(
        chat_id=settings['log_channel'],
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup=log_markup
    )
    
    # ডাটাবেসে সেভ করা
    links_col.insert_one({
        "key": key,
        "msg_id": sent.message_id,
        "log_channel": settings['log_channel'],
        "file_name": file_name
    })

    bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🤖 বট লিঙ্ক: `{tg_short_link}`\n🌐 ওয়েব লিঙ্ক: `{web_short_link}`", 
                 parse_mode="Markdown", reply_markup=log_markup)

# --- Flask & Webhook ---

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "<h1>Server is Running...</h1>", 200

if __name__ == "__main__":
    tg_client.start() # Pyrogram স্টার্ট
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
