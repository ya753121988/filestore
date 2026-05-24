import os
import telebot
import uuid
import requests
from flask import Flask, request, redirect, Response
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী) ---
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
WEB_URL = "https://filestore-jet.vercel.app"

# শর্ট লিঙ্ক সেটিংস
SHORTENER_URL = "https://urlbotsot.vercel.app/api"
SHORTENER_API = "akashdeveloper"

bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)

# --- ডাটাবেস সেটআপ ---
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
links_col = db['links']
settings_col = db['settings']

def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {
            "id": "bot_settings", 
            "log_channel": None, 
            "send_channel": None, 
            "force_channels": []
        }
        settings_col.insert_one(default)
        return default
    return settings

# --- লিঙ্ক শর্টনার ফাংশন ---
def get_short_link(long_url):
    try:
        params = {'api': SHORTENER_API, 'url': long_url}
        res = requests.get(SHORTENER_URL, params=params)
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
        except: continue
    
    markup.add(*btns)
    if extra_buttons:
        for b in extra_buttons: markup.add(b)
    return markup

# --- ফ্লাস্ক রুটস (Webhook & Download Server) ---

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "<h1>File Store & Download Server is Active!</h1>", 200

# সরাসরি ব্রাউজার ডাউনলোড রুট
@app.route("/dl/<key>")
def download_file(key):
    data = links_col.find_one({"key": key})
    if not data:
        return "<h1>File Not Found!</h1>", 404
    
    try:
        file_id = data.get('file_id')
        file_info = bot.get_file(file_id)
        # টেলিগ্রাম থেকে সরাসরি ডাউনলোড লিঙ্ক তৈরি
        direct_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
        # ইউজারকে টেলিগ্রামের ডিরেক্ট লিঙ্কে পাঠিয়ে দেওয়া (টেলিগ্রাম সার্ভার ব্রাউজার ডাউনলোড সাপোর্ট করে)
        return redirect(direct_url)
    except Exception as e:
        return f"Error: {str(e)}", 500

# --- বটের কমান্ড হ্যান্ডলারস ---

@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        settings = get_settings()
        if data and settings.get('send_channel'):
            try:
                sent = bot.copy_message(settings['send_channel'], data['log_channel'], data['msg_id'])
                c_info = bot.get_chat(settings['send_channel'])
                msg_link = f"https://t.me/{c_info.username}/{sent.message_id}" if c_info.username else f"https://t.me/c/{str(settings['send_channel']).replace('-100','')}/{sent.message_id}"
                
                btn = types.InlineKeyboardButton("🚀 ক্লিক করে ফাইলটি দেখুন", url=msg_link)
                bot.send_message(message.chat.id, "✅ আপনার ফাইলটি রেডি!", reply_markup=get_channel_buttons([btn]))
            except: pass
        return
    bot.send_message(message.chat.id, "👋 স্বাগতম! ফাইল পেতে চ্যানেলগুলোতে জয়েন করুন।", reply_markup=get_channel_buttons())

# --- এডমিন কমান্ডস (চ্যানেল ম্যানেজমেন্ট) ---

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids = [int(i.strip()) for i in message.text.replace('/set_force','').split(',')]
        curr = get_settings().get('force_channels', [])
        new_list = list(set(curr + ids))
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": new_list}}, upsert=True)
        bot.reply_to(message, "✅ চ্যানেলগুলো আপডেট হয়েছে।")
    except: bot.reply_to(message, "আইডিগুলো কমা দিয়ে দিন।")

@bot.message_handler(commands=['manage_channels'])
def manage_channels(message):
    if message.from_user.id != ADMIN_ID: return
    channels = get_settings().get('force_channels', [])
    if not channels: return bot.reply_to(message, "কোনো চ্যানেল নেই।")
    markup = types.InlineKeyboardMarkup()
    for cid in channels:
        markup.add(types.InlineKeyboardButton(f"ID: {cid}", callback_data="n"), 
                   types.InlineKeyboardButton("❌ Delete", callback_data=f"del_{cid}"))
    bot.send_message(message.chat.id, "⚙️ চ্যানেল ম্যানেজমেন্ট:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def del_channel(call):
    cid = int(call.data.split('_')[1])
    channels = get_settings().get('force_channels', [])
    if cid in channels:
        channels.remove(cid)
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": channels}})
        bot.answer_callback_query(call.id, "ডিলিট হয়েছে")
        bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def set_channels(message):
    if message.from_user.id != ADMIN_ID: return
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} সেট হয়েছে।")
    except: pass

# --- ফাইল স্টোরিং ও লিঙ্ক জেনারেশন ---

@bot.message_handler(content_types=['document', 'video', 'audio'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'): return bot.reply_to(message, "আগে `/log_cnl` দিন।")

    # ফাইল টাইপ অনুযায়ী আইডি নেওয়া
    file_id = ""
    if message.document: file_id = message.document.file_id
    elif message.video: file_id = message.video.file_id
    elif message.audio: file_id = message.audio.file_id

    # লিঙ্ক জেনারেট করা
    key = str(uuid.uuid4())[:8]
    bot_link = f"https://t.me/{bot.get_me().username}?start={key}"
    web_download_url = f"{WEB_URL}/dl/{key}" # আপনার ভার্সেল সার্ভার লিঙ্ক
    
    short_bot_link = get_short_link(bot_link)
    short_web_link = get_short_link(web_download_url)

    # বাটন তৈরি
    btn_bot = types.InlineKeyboardButton("🤖 Telegram Link", url=short_bot_link)
    btn_web = types.InlineKeyboardButton("🌐 Browser Download", url=short_web_link)
    markup = get_channel_buttons([btn_bot, btn_web])

    # লগ চ্যানেলে ফাইল কপি করা (বাটন সহ)
    sent = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id, reply_markup=markup)
    
    # ডাটাবেসে ফাইল আইডি সহ সেভ (ডাউনলোডের জন্য জরুরি)
    links_col.insert_one({
        "key": key, 
        "msg_id": sent.message_id, 
        "log_channel": settings['log_channel'],
        "file_id": file_id
    })

    res_text = (f"✅ **ফাইল সাকসেসফুলি সেভ হয়েছে!**\n\n"
                f"🤖 **বট লিঙ্ক:**\n`{short_bot_link}`\n\n"
                f"🌐 **ওয়েব ডাউনলোড লিঙ্ক:**\n`{short_web_link}`")
    
    bot.reply_to(message, res_text, reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
