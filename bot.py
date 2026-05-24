import os
import telebot
import uuid
import requests
from flask import Flask, request, redirect
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন ---
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
# আপনার ভার্সেল অ্যাপের ফুল লিঙ্ক (যেমন: https://mybot.vercel.app)
WEB_URL = "https://your-app-name.vercel.app" 

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
        default = {"id": "bot_settings", "channel_id": None}
        settings_col.insert_one(default)
        return default
    return settings

# --- ফ্লাস্ক রুটস (Webhook & Browser Download) ---

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
    return "<h1>Bot is Active!</h1><p>Webhook has been set.</p>", 200

@app.route("/dl/<file_id>")
def download_file(file_id):
    """ব্রাউজারে ফাইল ডাউনলোড লিঙ্ক তৈরি করার চেষ্টা"""
    try:
        file_info = bot.get_file(file_id)
        direct_link = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
        return redirect(direct_link)
    except:
        return "ফাইলটি অনেক বড় অথবা পাওয়া যায়নি। বটের মাধ্যমে ডাউনলোড করুন।", 404

# --- বট হ্যান্ডলারস ---

@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        if data:
            bot.send_message(message.chat.id, "⌛ আপনার ফাইলগুলো পাঠানো হচ্ছে...")
            # যদি এটি ব্যাচ (Range) হয়
            if 'start_id' in data:
                for msg_id in range(int(data['start_id']), int(data['last_id']) + 1):
                    try: bot.copy_message(message.chat.id, data['channel_id'], msg_id)
                    except: continue
            # যদি এটি সিঙ্গেল ফাইল হয়
            elif 'file_id' in data:
                bot.copy_message(message.chat.id, data['channel_id'], data['msg_id'])
                
            bot.send_message(message.chat.id, "✅ ফাইল পাঠানো সম্পন্ন!")
        else:
            bot.reply_to(message, "❌ লিঙ্কটি ভুল বা মেয়াদ শেষ।")
    else:
        bot.reply_to(message, "স্বাগতম! আমি সব ধরনের ফাইল (APK, Video, PDF) স্টোর করতে পারি।\n\nফাইল স্টোর করতে সেটি আমাকে ফরোয়ার্ড করুন।")

@bot.message_handler(commands=['cnl'])
def set_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"channel_id": cid}}, upsert=True)
        bot.reply_to(message, f"✅ সোর্স চ্যানেল সেট হয়েছে: `{cid}`")
    except:
        bot.reply_to(message, "ব্যবহার: `/cnl -100xxxxxx`")

# --- সব ধরনের ফাইল রিসিভ করার লজিক (Audio, Video, Photo, Document/APK) ---
@bot.message_handler(content_types=['document', 'video', 'audio', 'photo', 'voice'])
def handle_files(message):
    if message.from_user.id != ADMIN_ID: return
    
    settings = get_settings()
    if not settings.get('channel_id'):
        bot.reply_to(message, "আগে `/cnl` দিয়ে চ্যানেল সেট করুন।")
        return

    # ফাইল ইনফো সংগ্রহ
    file_id = None
    if message.document: file_id = message.document.file_id
    elif message.video: file_id = message.video.file_id
    elif message.audio: file_id = message.audio.file_id
    elif message.photo: file_id = message.photo[-1].file_id
    
    # চ্যানেল এ ফাইল কপি করে রাখা (পার্মানেন্ট স্টোরেজ)
    sent_msg = bot.copy_message(settings['channel_id'], message.chat.id, message.message_id)
    
    key = str(uuid.uuid4())[:10]
    links_col.insert_one({
        "key": key,
        "msg_id": sent_msg.message_id,
        "channel_id": settings['channel_id'],
        "file_id": file_id # ফর ক্রোম ডাউনলোড
    })

    bot_user = bot.get_me().username
    bot_link = f"https://t.me/{bot_user}?start={key}"
    web_link = f"{WEB_URL}/dl/{file_id}" if file_id else "N/A"

    response_text = (
        f"✅ **ফাইল সাকসেসফুলি স্টোর হয়েছে!**\n\n"
        f"🔗 **বট লিঙ্ক (টেলিগ্রাম):**\n`{bot_link}`\n\n"
        f"🌐 **অনলাইন ডাউনলোড লিঙ্ক:**\n[Click here to Download]({web_link})\n\n"
        f"*(নোট: ২০ এমবির বেশি ফাইল ক্রোম লিঙ্কে কাজ নাও করতে পারে)*"
    )
    
    bot.reply_to(message, response_text, parse_mode="Markdown", disable_web_page_preview=True)

# ব্যাচ লিঙ্কের জন্য পুরাতন কমান্ড
@bot.message_handler(commands=['link'])
def link_batch(message):
    bot.reply_to(message, "ব্যাচ লিঙ্ক তৈরি করতে চাইলে প্রথমে প্রথম ফাইল এবং পরে শেষ ফাইলের লিঙ্ক দিন (এটি আগের কোডের মতই কাজ করবে)।")

if __name__ == "__main__":
    # ভার্সেলে চালানোর জন্য app.run দরকার নেই, তবে লোকাল টেস্টিং এর জন্য:
    app.run(host="0.0.0.0", port=5000)
