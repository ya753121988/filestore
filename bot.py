import os
import telebot
import uuid
import requests
from flask import Flask, request
from pymongo import MongoClient

# --- কনফিগারেশন ---
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
API_ID = 29904834
API_HASH = '8b4fd9ef578af114502feeafa2d31938'
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
        default = {"id": "bot_settings", "log_channel": None, "send_channel": None}
        settings_col.insert_one(default)
        return default
    return settings

# --- লিঙ্ক শর্টনার ফাংশন ---
def get_short_link(long_url):
    try:
        # আপনার সাইটের API ফরম্যাট অনুযায়ী: ?api=KEY&url=URL
        params = {'api': SHORTENER_API, 'url': long_url}
        res = requests.get(SHORTENER_URL, params=params)
        # যদি JSON রিটার্ন করে তবে res.json() ব্যবহার করুন, নতুবা সরাসরি টেক্সট
        data = res.json()
        if data.get('status') == 'success' or 'shortenedUrl' in data:
            return data.get('shortenedUrl')
        return long_url
    except:
        return long_url

# --- ফ্লাস্ক রুটস (Webhook) ---
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
    return "<h1>Bot is Active!</h1>", 200

# --- কমান্ড হ্যান্ডলারস ---

@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    settings = get_settings()
    
    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        
        if data and settings.get('send_channel'):
            try:
                # ফাইলটি সোর্স চ্যানেল থেকে 'ফাইল সেন্ড চ্যানেলে' কপি করা হবে
                sent_msg = bot.copy_message(
                    chat_id=settings['send_channel'],
                    from_chat_id=data['log_channel'],
                    message_id=data['msg_id']
                )
                
                # চ্যানেলের ইউজারনেম পাওয়া (লিঙ্ক তৈরির জন্য)
                channel_info = bot.get_chat(settings['send_channel'])
                if channel_info.username:
                    msg_link = f"https://t.me/{channel_info.username}/{sent_msg.message_id}"
                else:
                    # প্রাইভেট চ্যানেল হলে আইডি ফরম্যাটে লিঙ্ক
                    cid_str = str(settings['send_channel']).replace("-100", "")
                    msg_link = f"https://t.me/c/{cid_str}/{sent_msg.message_id}"
                
                bot.send_message(
                    message.chat.id, 
                    f"✅ আপনার ফাইলটি নিচের চ্যানেলে পাঠানো হয়েছে:\n\n🔗 [এখানে ক্লিক করুন]({msg_link})",
                    parse_mode="Markdown"
                )
            except Exception as e:
                bot.reply_to(message, f"❌ ত্রুটি: {str(e)}")
        else:
            bot.reply_to(message, "❌ লিঙ্কটি ভুল অথবা সেন্ড চ্যানেল সেট করা নেই।")
    else:
        bot.reply_to(message, "স্বাগতম! ফাইল স্টোর করতে সেটি আমাকে ফরোয়ার্ড করুন।")

# --- এডমিন কমান্ডস (চ্যানেল সেট করা) ---

@bot.message_handler(commands=['log_cnl'])
def set_log_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"log_channel": cid}}, upsert=True)
        bot.reply_to(message, f"✅ লগ চ্যানেল (Storage) সেট হয়েছে: `{cid}`")
    except:
        bot.reply_to(message, "ব্যবহার: `/log_cnl -100xxxxxx`")

@bot.message_handler(commands=['send_cnl'])
def set_send_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"send_channel": cid}}, upsert=True)
        bot.reply_to(message, f"✅ ফাইল সেন্ড চ্যানেল সেট হয়েছে: `{cid}`")
    except:
        bot.reply_to(message, "ব্যবহার: `/send_cnl -100xxxxxx`")

# --- ফাইল হ্যান্ডলিং (এডমিন ফাইল দিলে) ---

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    
    settings = get_settings()
    if not settings.get('log_channel'):
        bot.reply_to(message, "আগে `/log_cnl` দিয়ে লগ চ্যানেল সেট করুন।")
        return

    # ফাইল লগ চ্যানেলে কপি করা
    sent_msg = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id)
    
    key = str(uuid.uuid4())[:8]
    bot_user = bot.get_me().username
    raw_link = f"https://t.me/{bot_user}?start={key}"
    
    # লিঙ্ক শর্ট করা
    short_link = get_short_link(raw_link)

    links_col.insert_one({
        "key": key,
        "msg_id": sent_msg.message_id,
        "log_channel": settings['log_channel']
    })

    response_text = (
        f"✅ **ফাইল সাকসেসফুলি সেভ হয়েছে!**\n\n"
        f"🔗 **অরিজিনাল লিঙ্ক:**\n`{raw_link}`\n\n"
        f"🌐 **শর্ট লিঙ্ক:**\n`{short_link}`"
    )
    bot.reply_to(message, response_text, parse_mode="Markdown")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
