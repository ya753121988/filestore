import os
import telebot
import uuid
import requests
from flask import Flask, request
from pymongo import MongoClient

# আপনার দেওয়া তথ্যাদি
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
SHORTENER_URL = 'https://urlbotsot.vercel.app'
SHORTENER_API = 'akashdeveloper'

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# MongoDB Setup
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
settings_col = db['settings']
links_col = db['links']

# Helper to get current settings
def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {"id": "bot_settings", "channel_id": None}
        settings_col.insert_one(default)
        return default
    return settings

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    # এখানে আপনার ভার্সেল ইউআরএলটি অটোমেটিক সেট হবে যখন আপনি ব্রাউজারে এটি রান করবেন
    return "Bot is Running!", 200

# /start logic
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        link_data = links_col.find_one({"key": key})
        
        if link_data:
            settings = get_settings()
            channel_id = link_data['channel_id']
            start_id = int(link_data['start_id'])
            last_id = int(link_data['last_id'])
            
            bot.send_message(message.chat.id, "⌛ আপনার ফাইলগুলো পাঠানো হচ্ছে, অপেক্ষা করুন...")
            
            count = 0
            for msg_id in range(start_id, last_id + 1):
                try:
                    bot.copy_message(message.chat.id, channel_id, msg_id)
                    count += 1
                except Exception:
                    continue
            
            if count == 0:
                bot.send_message(message.chat.id, "❌ কোনো ফাইল পাওয়া যায়নি। চ্যানেল চেক করুন।")
            else:
                bot.send_message(message.chat.id, f"✅ মোট {count}টি ফাইল পাঠানো হয়েছে।")
        else:
            bot.reply_to(message, "❌ লিঙ্কটি ভুল বা ডিলিট করা হয়েছে।")
    else:
        bot.reply_to(message, "স্বাগতম! আমি আপনার পার্সোনাল ফাইল স্টোর বট।")

# /cnl - Set Storage Channel
@bot.message_handler(commands=['cnl'])
def set_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        channel_id = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"channel_id": int(channel_id)}}, upsert=True)
        bot.reply_to(message, f"✅ সোর্স চ্যানেল সেট হয়েছে: `{channel_id}`\n(নিশ্চিত করুন বটটি ওই চ্যানেলে এডমিন আছে)", parse_mode="Markdown")
    except:
        bot.reply_to(message, "ব্যবহার: `/cnl -100xxxxxxxxxx`")

# /link - Batch Link generation
admin_step = {}

@bot.message_handler(commands=['link'])
def generate_link(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('channel_id'):
        bot.reply_to(message, "আগে `/cnl` দিয়ে চ্যানেল আইডি সেট করুন।")
        return
    
    bot.reply_to(message, "১. প্রথম মেসেজের লিঙ্ক দিন:")
    admin_step[message.from_user.id] = {'step': 1}

@bot.message_handler(func=lambda m: admin_step.get(m.from_user.id, {}).get('step') == 1)
def get_first_id(message):
    try:
        first_id = message.text.split('/')[-1]
        admin_step[message.from_user.id]['first_id'] = int(first_id)
        admin_step[message.from_user.id]['step'] = 2
        bot.reply_to(message, "২. শেষ মেসেজের লিঙ্ক দিন:")
    except:
        bot.reply_to(message, "ভুল লিঙ্ক! আবার `/link` দিন।")

@bot.message_handler(func=lambda m: admin_step.get(m.from_user.id, {}).get('step') == 2)
def get_last_id(message):
    try:
        last_id = message.text.split('/')[-1]
        user_data = admin_step[message.from_user.id]
        first_id = user_data['first_id']
        settings = get_settings()
        
        key = str(uuid.uuid4())[:8]
        links_col.insert_one({
            "key": key,
            "start_id": first_id,
            "last_id": int(last_id),
            "channel_id": settings['channel_id']
        })
        
        bot_info = bot.get_me()
        raw_link = f"https://t.me/{bot_info.username}?start={key}"
        
        # URL Shortener integration
        try:
            # এখানে আপনার শর্টনারের এপিআই ফরম্যাট অনুযায়ী লিঙ্ক তৈরি হচ্ছে
            api_endpoint = f"{SHORTENER_URL}/api?api={SHORTENER_API}&url={raw_link}"
            res = requests.get(api_endpoint)
            short_link = res.json().get('shortenedUrl', raw_link) if res.status_code == 200 else raw_link
        except:
            short_link = raw_link

        bot.send_message(message.chat.id, f"✅ ব্যাচ লিঙ্ক তৈরি হয়েছে!\n\n🔗 লিঙ্ক: {short_link}")
        del admin_step[message.from_user.id]
    except:
        bot.reply_to(message, "ভুল হয়েছে! আবার চেষ্টা করুন।")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
