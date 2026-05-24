import os
import uuid
import asyncio
import requests
import telebot
from flask import Flask, request, Response, stream_with_context
from pymongo import MongoClient
from telebot import types
from pyrogram import Client
from pyrogram.errors import UserNotParticipant

# --- আপনার দেওয়া কনফিগারেশন ---
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
BOT_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-eclu.onrender.com"

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

# বট ও ডাটাবেস ইনিশিয়ালাইজ
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
links_col = db['links']
settings_col = db['settings']

# Pyrogram Client (বড় ফাইল স্ট্রিমিংয়ের জন্য)
tg_client = Client("stream_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- সেটিংস ফাংশন ---
def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {"id": "bot_settings", "log_channel": None, "send_channel": None, "force_channels": []}
        settings_col.insert_one(default)
        return default
    return settings

# --- Force Join চেক করা ---
def is_user_joined(user_id):
    settings = get_settings()
    channels = settings.get('force_channels', [])
    for cid in channels:
        try:
            status = bot.get_chat_member(cid, user_id).status
            if status in ['left', 'kicked']: return False
        except: continue
    return True

# --- বাটন জেনারেটর ---
def get_channel_buttons(extra_buttons=None):
    settings = get_settings()
    channels = settings.get('force_channels', [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, cid in enumerate(channels, 1):
        try:
            chat = bot.get_chat(cid)
            link = f"https://t.me/{chat.username}" if chat.username else bot.export_chat_invite_link(cid)
            markup.add(types.InlineKeyboardButton(f"Join Channel {i} 📢", url=link))
        except: continue
    if extra_buttons:
        for b in extra_buttons: markup.add(b)
    return markup

# --- লিঙ্ক শর্টনার ---
def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url}, timeout=10)
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- ফাইল স্ট্রিমিং (Flask Route) ---
@app.route("/dl/<key>")
def stream_file(key):
    data = links_col.find_one({"key": key})
    if not data: return "File not found!", 404
    
    file_name = data.get('file_name', 'video_file.mp4')
    
    def generate():
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

# --- বটের কমান্ডস (User Side) ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1:
        file_key = args[1]
        if not is_user_joined(user_id):
            btn_try = types.InlineKeyboardButton("Check Again 🔄", url=f"https://t.me/{bot.get_me().username}?start={file_key}")
            return bot.send_message(message.chat.id, "❌ আপনি আমাদের চ্যানেলে জয়েন করেননি! ফাইলটি পেতে নিচের চ্যানেলগুলোতে জয়েন করুন এবং আবার ট্রাই করুন।", 
                                    reply_markup=get_channel_buttons([btn_try]))
        
        data = links_col.find_one({"key": file_key})
        if data:
            # টেলিগ্রামে ফাইল পাঠানো
            bot.copy_message(message.chat.id, data['log_channel'], data['msg_id'])
            # ব্রাউজার লিঙ্ক
            web_url = f"{WEB_URL}/dl/{file_key}"
            short_web = get_short_link(web_url)
            btn_web = types.InlineKeyboardButton("🌐 Web Download (Browser)", url=short_web)
            bot.send_message(message.chat.id, "✅ আপনার ফাইলটি উপরে দেওয়া হয়েছে। ব্রাউজারে হাই স্পিড ডাউনলোডের জন্য নিচের বাটনটি ব্যবহার করুন:", 
                             reply_markup=types.InlineKeyboardMarkup().add(btn_web))
        else:
            bot.send_message(message.chat.id, "❌ ফাইলটি খুঁজে পাওয়া যায়নি।")
        return
    
    bot.send_message(message.chat.id, "স্বাগতম! ফাইল পেতে লিঙ্কে ক্লিক করুন বা আমাদের চ্যানেলগুলো ভিজিট করুন।", reply_markup=get_channel_buttons())

# --- এডমিন কমান্ডস ---

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def set_channels(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.split()
    if len(text) < 2: return bot.reply_to(message, "ব্যবহার: `/log_cnl -100xxxx` অথবা `/send_cnl -100xxxx`", parse_mode="Markdown")
    
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(text[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} সফলভাবে সেট করা হয়েছে!")
    except: bot.reply_to(message, "ভুল আইডি ফরম্যাট।")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace('/set_force', '').strip()
    if not text: return bot.reply_to(message, "আইডি দিন। উদাহরণ: `/set_force -1001, -1002`", parse_mode="Markdown")
    
    try:
        ids = [int(i.strip()) for i in text.split(',')]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": ids}}, upsert=True)
        bot.reply_to(message, "✅ Force Join চ্যানেলগুলো আপডেট করা হয়েছে।")
    except: bot.reply_to(message, "ভুল ফরম্যাট।")

@bot.message_handler(commands=['manage_channels'])
def manage_channels(message):
    if message.from_user.id != ADMIN_ID: return
    channels = get_settings().get('force_channels', [])
    if not channels: return bot.send_message(message.chat.id, "কোনো চ্যানেল সেট করা নেই।")
    
    markup = types.InlineKeyboardMarkup()
    for cid in channels:
        markup.add(types.InlineKeyboardButton(f"❌ Delete {cid}", callback_data=f"del_{cid}"))
    bot.send_message(message.chat.id, "⚙️ চ্যানেল ম্যানেজমেন্ট:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_force(call):
    cid = int(call.data.split('_')[1])
    channels = get_settings().get('force_channels', [])
    if cid in channels:
        channels.remove(cid)
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": channels}})
        bot.answer_callback_query(call.id, "রিমুভ করা হয়েছে!")
        bot.edit_message_text("✅ আপডেট করা হয়েছে!", call.message.chat.id, call.message.message_id)

# --- ফাইল হ্যান্ডলিং ---

@bot.message_handler(content_types=['document', 'video', 'audio'])
def handle_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    log_id = settings.get('log_channel')
    if not log_id: return bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")

    file_obj = message.document or message.video or message.audio
    file_name = getattr(file_obj, 'file_name', 'file.mp4')
    key = str(uuid.uuid4())[:8]
    
    # লগ চ্যানেলে ফাইল পাঠানো
    sent = bot.copy_message(log_id, message.chat.id, message.message_id)
    
    # ডাটাবেসে সেভ
    links_col.insert_one({
        "key": key,
        "msg_id": sent.message_id,
        "log_channel": log_id,
        "file_name": file_name
    })
    
    bot_username = bot.get_me().username
    tg_link = f"https://t.me/{bot_username}?start={key}"
    web_link = f"{WEB_URL}/dl/{key}"
    
    bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🤖 TG Link: `{tg_link}`\n\n🌐 Web Link: `{web_link}`", parse_mode="Markdown")

# --- সার্ভার ও রানিং ---

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route("/")
def home():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{BOT_TOKEN}")
    return "<h1>Bot is Running!</h1>", 200

if __name__ == "__main__":
    # Pyrogram সেশন
    tg_client.start()
    # Flask সার্ভার
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
