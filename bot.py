import os
import telebot
import uuid
import requests
import asyncio
from flask import Flask, request, Response, stream_with_context
from pymongo import MongoClient
from telebot import types
from pyrogram import Client

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

# --- বাটন জেনারেটর (ইউজারদের জন্য) ---
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
    markup.add(*btns)
    if extra_buttons:
        for b in extra_buttons: markup.add(b)
    return markup

# --- লিঙ্ক শর্টনার ---
def get_short_link(long_url):
    try:
        res = requests.get(SHORTENER_URL, params={'api': SHORTENER_API, 'url': long_url})
        data = res.json()
        return data.get('shortenedUrl') if data.get('status') == 'success' else long_url
    except: return long_url

# --- ফাইল স্ট্রিমিং লজিক (Bypassing 20MB Limit) ---
async def generate_file_stream(file_id):
    async with tg_client:
        async for chunk in tg_client.download_media(file_id, byte_offset=0, in_memory=True):
            yield chunk

@app.route("/dl/<key>")
def stream_file(key):
    data = links_col.find_one({"key": key})
    if not data: return "File not found!", 404
    
    file_id = data.get('file_id')
    file_name = data.get('file_name', 'download_file')
    
    # ব্রাউজারকে ফাইল ডাউনলোডের প্রম্পট পাঠানো
    headers = {
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Type': 'application/octet-stream'
    }
    
    # Async স্ট্রিমিং চালু করা
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def stream():
        # এটি টেলিগ্রাম থেকে ফাইল চাঙ্ক আকারে নিয়ে ব্রাউজারে পাঠাবে
        with tg_client:
            media = tg_client.get_messages(data['log_channel'], data['msg_id'])
            for chunk in tg_client.stream_media(media):
                yield chunk

    return Response(stream_with_context(stream()), headers=headers)

# --- বটের কমান্ডস ও ফিচারস ---

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "<h1>File Stream Bot & Server is Live!</h1>", 200

@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        data = links_col.find_one({"key": args[1]})
        settings = get_settings()
        if data and settings.get('send_channel'):
            sent = bot.copy_message(settings['send_channel'], data['log_channel'], data['msg_id'])
            c_info = bot.get_chat(settings['send_channel'])
            m_link = f"https://t.me/{c_info.username}/{sent.message_id}" if c_info.username else f"https://t.me/c/{str(settings['send_channel']).replace('-100','')}/{sent.message_id}"
            
            btn_watch = types.InlineKeyboardButton("🚀 Watch on Telegram", url=m_link)
            btn_browser = types.InlineKeyboardButton("🌐 Web Download (Browser)", url=get_short_link(f"{WEB_URL}/dl/{args[1]}"))
            bot.send_message(message.chat.id, "✅ ফাইল রেডি! নিচের বাটন থেকে ডাউনলোড করুন:", reply_markup=get_channel_buttons([btn_watch, btn_browser]))
        return
    bot.send_message(message.chat.id, "স্বাগতম! চ্যানেল জয়েন করে ফাইল রিসিভ করুন।", reply_markup=get_channel_buttons())

# --- এডমিন ম্যানেজমেন্ট ---

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

@bot.message_handler(commands=['manage_channels'])
def manage_channels(message):
    if message.from_user.id != ADMIN_ID: return
    channels = get_settings().get('force_channels', [])
    markup = types.InlineKeyboardMarkup()
    for cid in channels:
        markup.add(types.InlineKeyboardButton(f"Channel: {cid}", callback_data="n"),
                   types.InlineKeyboardButton("❌ Delete", callback_data=f"del_{cid}"))
    bot.send_message(message.chat.id, "⚙️ চ্যানেল রিমুভ করুন:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def del_callback(call):
    cid = int(call.data.split('_')[1])
    settings = get_settings()
    channels = settings.get('force_channels', [])
    if cid in channels:
        channels.remove(cid)
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": channels}})
        bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def admin_set_cnl(message):
    if message.from_user.id != ADMIN_ID: return
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} আপডেট হয়েছে!")
    except: pass

# --- ফাইল সেভ ও লগ চ্যানেলে বাটন যুক্ত করা ---

@bot.message_handler(content_types=['document', 'video', 'audio'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'): return bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")

    file_obj = message.document or message.video or message.audio
    file_id = file_obj.file_id
    file_name = getattr(file_obj, 'file_name', 'video_file.mp4')
    
    key = str(uuid.uuid4())[:8]
    tg_link = get_short_link(f"https://t.me/{bot.get_me().username}?start={key}")
    web_link = get_short_link(f"{WEB_URL}/dl/{key}")

    # বাটন তৈরি (লগ চ্যানেলের জন্য)
    btn_tg = types.InlineKeyboardButton("🤖 Bot Link", url=tg_link)
    btn_web = types.InlineKeyboardButton("🌐 Direct Web Download", url=web_link)
    markup = get_channel_buttons([btn_tg, btn_web])

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

    bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🤖 TG লিঙ্ক: `{tg_link}`\n🌐 ওয়েব লিঙ্ক: `{web_link}`", 
                 reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    tg_client.start() # Pyrogram স্টার্ট
    app.run(host="0.0.0.0", port=5000)
