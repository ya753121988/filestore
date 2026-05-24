import os
import telebot
import uuid
import requests
from flask import Flask, request
from pymongo import MongoClient

# আপনার দেওয়া ডিফল্ট তথ্য (এগুলো কমান্ড দিয়েও পাল্টানো যাবে)
API_TOKEN = '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg'
MONGO_URI = 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0'
ADMIN_ID = 8932594210

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# MongoDB Setup
client = MongoClient(MONGO_URI)
db = client['DramaStoreDB']
settings_col = db['settings']
links_col = db['links']
state_col = db['user_state'] # স্টেট সেভ করার জন্য

# সেটিংস ডাটাবেস থেকে আনার ফাংশন
def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {
            "id": "bot_settings", 
            "channel_id": None, 
            "shortener_url": "urlbotsot.vercel.app", 
            "shortener_api": "akashdeveloper"
        }
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
            
            for msg_id in range(start_id, last_id + 1):
                try:
                    bot.copy_message(message.chat.id, channel_id, msg_id)
                except:
                    continue
            bot.send_message(message.chat.id, "✅ ফাইল পাঠানো শেষ!")
        else:
            bot.reply_to(message, "❌ লিঙ্কটি ভুল।")
    else:
        bot.reply_to(message, "স্বাগতম! আমি ফাইল স্টোর বট।")

# /cnl Command
@bot.message_handler(commands=['cnl'])
def set_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        channel_id = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"channel_id": int(channel_id)}}, upsert=True)
        bot.reply_to(message, f"✅ সোর্স চ্যানেল সেট হয়েছে: `{channel_id}`")
    except:
        bot.reply_to(message, "ব্যবহার: `/cnl -100xxxxxxxxxx`")

# /setshort Command (শর্টনার চেঞ্জ করা)
@bot.message_handler(commands=['setshort'])
def set_shortener(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        # ইনপুট ফরম্যাট: /setshort url api
        args = message.text.split()
        url = args[1].replace("https://", "").replace("http://", "").rstrip("/")
        api = args[2]
        
        settings_col.update_one({"id": "bot_settings"}, 
            {"$set": {"shortener_url": url, "shortener_api": api}}, upsert=True)
        
        bot.reply_to(message, f"✅ শর্টনার সেট হয়েছে!\nURL: `{url}`\nAPI: `{api}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "ব্যবহার: `/setshort urlbotsot.vercel.app akashdeveloper`")

# /link Command (স্টেট সিস্টেম ব্যবহার করে)
@bot.message_handler(commands=['link'])
def link_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('channel_id'):
        bot.reply_to(message, "আগে `/cnl` দিয়ে চ্যানেল সেট করুন।")
        return
    
    state_col.update_one({"user_id": ADMIN_ID}, {"$set": {"step": "await_first"}}, upsert=True)
    bot.reply_to(message, "১. প্রথম মেসেজের লিঙ্ক দিন:")

# মেসেজ হ্যান্ডলার (লিঙ্ক প্রসেস করার জন্য)
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    if message.from_user.id != ADMIN_ID: return
    
    user_state = state_col.find_one({"user_id": ADMIN_ID})
    if not user_state: return

    # প্রথম লিঙ্ক গ্রহণ
    if user_state.get('step') == "await_first":
        try:
            first_id = int(message.text.split('/')[-1])
            state_col.update_one({"user_id": ADMIN_ID}, {"$set": {"step": "await_last", "first_id": first_id}})
            bot.reply_to(message, "২. শেষ মেসেজের লিঙ্ক দিন:")
        except:
            bot.reply_to(message, "❌ ভুল লিঙ্ক! আবার প্রথম লিঙ্ক দিন।")

    # শেষ লিঙ্ক গ্রহণ এবং ফাইনাল কাজ
    elif user_state.get('step') == "await_last":
        try:
            last_id = int(message.text.split('/')[-1])
            first_id = user_state['first_id']
            settings = get_settings()
            
            key = str(uuid.uuid4())[:8]
            links_col.insert_one({
                "key": key,
                "start_id": first_id,
                "last_id": last_id,
                "channel_id": settings['channel_id']
            })
            
            bot_username = bot.get_me().username
            raw_link = f"https://t.me/{bot_username}?start={key}"
            
            # শর্টনার প্রসেস
            s_url = settings.get('shortener_url')
            s_api = settings.get('shortener_api')
            
            try:
                final_api_url = f"https://{s_url}/api?api={s_api}&url={raw_link}"
                res = requests.get(final_api_url)
                # আপনার শর্টনার সাইট যদি json রিটার্ন করে তবে res.json() ব্যবহার হবে
                # যদি সরাসরি টেক্সট দেয় তবে res.text
                short_link = res.json().get('shortenedUrl', raw_link) if res.status_code == 200 else raw_link
            except:
                short_link = raw_link

            bot.send_message(message.chat.id, f"✅ আপনার লিঙ্ক তৈরি:\n\n`{short_link}`", parse_mode="Markdown")
            state_col.delete_one({"user_id": ADMIN_ID}) # স্টেট ক্লিয়ার
        except:
            bot.reply_to(message, "❌ ভুল লিঙ্ক! আবার চেষ্টা করুন।")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
