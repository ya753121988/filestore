import os
import telebot
import uuid
import requests
from flask import Flask, request
from pymongo import MongoClient

# আপনার তথ্য
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210
# আপনার ভার্সেল ইউআরএল (যেমন: https://your-app.vercel.app)
URL = "https://filestore-jet.vercel.app" 

bot = telebot.TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)

client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
settings_col = db['settings']
links_col = db['links']
state_col = db['user_state']

def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {"id": "bot_settings", "channel_id": None, "shortener_url": "urlbotsot.vercel.app", "shortener_api": "akashdeveloper"}
        settings_col.insert_one(default)
        return default
    return settings

# ওয়েবহুক রুট
@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Invalid Request", 403

@app.route("/")
def webhook_setup():
    bot.remove_webhook()
    # এখানে URL অবশ্যই https হতে হবে
    bot.set_webhook(url=f"{URL}/{API_TOKEN}")
    return "Bot Webhook Set Successfully!", 200

# /start logic
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        link_data = links_col.find_one({"key": key})
        if link_data:
            bot.send_message(message.chat.id, "⌛ ফাইল পাঠানো হচ্ছে...")
            for msg_id in range(int(link_data['start_id']), int(link_data['last_id']) + 1):
                try: bot.copy_message(message.chat.id, link_data['channel_id'], msg_id)
                except: continue
        else: bot.reply_to(message, "❌ লিঙ্কটি ভুল।")
    else: bot.reply_to(message, "স্বাগতম!")

# /cnl logic
@bot.message_handler(commands=['cnl'])
def set_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"channel_id": int(cid)}}, upsert=True)
        bot.reply_to(message, f"✅ সোর্স চ্যানেল সেট হয়েছে: `{cid}`")
    except: bot.reply_to(message, "ব্যবহার: `/cnl -100xxxxxx`")

# /link logic
@bot.message_handler(commands=['link'])
def link_command(message):
    if message.from_user.id != ADMIN_ID: return
    state_col.update_one({"user_id": ADMIN_ID}, {"$set": {"step": "await_first"}}, upsert=True)
    bot.reply_to(message, "১. প্রথম মেসেজের লিঙ্ক দিন:")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if message.from_user.id != ADMIN_ID: return
    state = state_col.find_one({"user_id": ADMIN_ID})
    if not state: return

    if state['step'] == "await_first":
        try:
            fid = int(message.text.split('/')[-1])
            state_col.update_one({"user_id": ADMIN_ID}, {"$set": {"step": "await_last", "fid": fid}})
            bot.reply_to(message, "২. শেষ মেসেজের লিঙ্ক দিন:")
        except: bot.reply_to(message, "❌ ভুল লিঙ্ক!")
    
    elif state['step'] == "await_last":
        try:
            lid = int(message.text.split('/')[-1])
            fid = state['fid']
            setts = get_settings()
            key = str(uuid.uuid4())[:8]
            links_col.insert_one({"key": key, "start_id": fid, "last_id": lid, "channel_id": setts['channel_id']})
            raw_link = f"https://t.me/{bot.get_me().username}?start={key}"
            bot.reply_to(message, f"✅ লিঙ্ক তৈরি:\n`{raw_link}`")
            state_col.delete_one({"user_id": ADMIN_ID})
        except: bot.reply_to(message, "❌ ভুল লিঙ্ক!")

# Vercel এর জন্য app.run() বাদ দেওয়া হয়েছে।
