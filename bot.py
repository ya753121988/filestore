import os
import telebot
import uuid
import requests
import time
import re
import random
from flask import Flask, request
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন (Environment Variables) ---
API_TOKEN = os.getenv('API_TOKEN', '8501387772:AAH8dn31CMywDrF0nSjM7TMfB2uA8i-Nfzg')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://drama:drama@cluster0.sa4kvgu.mongodb.net/DramaStoreDB?retryWrites=true&w=majority&appName=Cluster0')
ADMIN_ID = int(os.getenv('ADMIN_ID', '8932594210'))
WEB_URL = os.getenv('WEB_URL', 'https://official-elene-akashvaikh-d4e6b245.koyeb.app') 

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
users_col = db['users']
chats_col = db['chats'] # চ্যানেল ব্রডকাস্টের জন্য নতুন কালেকশন

# ব্যাচ প্রসেস ট্র্যাক করার জন্য স্টেট
user_states = {}

# --- ডাটাবেস ফাংশন ---
def get_settings():
    settings = settings_col.find_one({"id": "bot_settings"})
    if not settings:
        default = {
            "id": "bot_settings", 
            "log_channel": None, 
            "send_channel": None, 
            "force_channels": [],
            "logo_url": "https://telegra.ph/file/default-logo.jpg",
            "fsub_active": True,
            "auto_react": True
        }
        settings_col.insert_one(default)
        return default
    return settings

# --- ইউজারের ফুল ইনফো সেভ করার ফাংশন ---
def save_user_data(user):
    full_name = f"{user.first_name} {user.last_name if user.last_name else ''}".strip()
    users_col.update_one(
        {"user_id": user.id},
        {"$set": {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": full_name
        }},
        upsert=True
    )

# --- অটো চ্যানেল মেম্বার একসেপ্ট ---
@bot.chat_join_request_handler()
def auto_approve_request(chat_join_request):
    try:
        bot.approve_chat_join_request(chat_join_request.chat.id, chat_join_request.from_user.id)
    except Exception as e:
        print(f"Error Approve: {e}")

# --- অটো রিয়েকশন ফাংশন ---
def send_auto_reaction(chat_id, message_id):
    settings = get_settings()
    if settings.get('auto_react', True):
        emojis = ["👍", "❤️", "🔥", "🥰", "👏", "⚡", "🎉", "🤩", "🆒"]
        try:
            bot.set_message_reaction(chat_id, message_id, [types.ReactionTypeEmoji(random.choice(emojis))])
        except:
            pass

# চ্যানেল এবং গ্রুপ পোস্ট ট্র্যাক ও অটো রিয়েক্ট
@bot.channel_post_handler(func=lambda message: True)
def on_channel_post(message):
    send_auto_reaction(message.chat.id, message.message_id)
    # ব্রডকাস্টের জন্য চ্যাট সেভ
    chats_col.update_one({"chat_id": message.chat.id}, {"$set": {"type": "channel", "title": message.chat.title}}, upsert=True)

@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def on_group_message(message):
    send_auto_reaction(message.chat.id, message.message_id)
    # ব্রডকাস্টের জন্য গ্রুপ সেভ
    chats_col.update_one({"chat_id": message.chat.id}, {"$set": {"type": "group", "title": message.chat.title}}, upsert=True)

# --- লিঙ্ক থেকে আইডি বের করার ফাংশন ---
def get_message_id(text):
    match = re.search(r"(\d+)$", text)
    return int(match.group(1)) if match else None

# --- ফোর্স সাবস্ক্রাইব চেক ---
def is_subscribed(user_id):
    if user_id == ADMIN_ID:
        return True
    settings = get_settings()
    if not settings.get('fsub_active', True):
        return True
    channels = settings.get('force_channels', [])
    if not channels:
        return True
    for cid in channels:
        try:
            status = bot.get_chat_member(cid, user_id).status
            if status in ['left', 'kicked']:
                return False
        except Exception:
            continue 
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
        except:
            continue
    if extra_buttons:
        for b in extra_buttons:
            markup.add(b)
    admin_btn = types.InlineKeyboardButton("👨‍💻 Admin Contact", url="https://t.me/AllDramaKingsAdminBot")
    markup.add(admin_btn)
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

# --- সাধারণ কমান্ড হ্যান্ডলার ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    save_user_data(message.from_user) # ইউজার ইনফো সেভ

    settings = get_settings()
    args = message.text.split()
    
    # ডিপ লিঙ্ক প্রসেসিং
    if len(args) > 1:
        key = args[1]
        if not is_subscribed(user_id):
            btn = types.InlineKeyboardButton("Try Again 🔄", url=f"https://t.me/{bot.get_me().username}?start={key}")
            return bot.send_message(
                message.chat.id, 
                "❌ **ফাইলটি পেতে আপনাকে আমাদের নিচের চ্যানেলে জয়েন করতে হবে।**", 
                reply_markup=get_channel_buttons([btn]),
                parse_mode="Markdown"
            )

        data = links_col.find_one({"key": key})
        if data:
            # ব্যাচ রেঞ্জ নির্ধারণ
            if "start_id" in data and "end_id" in data:
                msg_ids = list(range(int(data['start_id']), int(data['end_id']) + 1))
            else:
                msg_ids = [data['msg_id']]

            last_sent_to_channel_id = None
            for m_id in msg_ids:
                try:
                    if settings.get('send_channel'):
                        sent = bot.copy_message(settings['send_channel'], data['log_channel'], m_id)
                        last_sent_to_channel_id = sent.message_id
                    else:
                        bot.copy_message(message.chat.id, data['log_channel'], m_id)
                    time.sleep(0.5)
                except: continue

            if settings.get('send_channel') and last_sent_to_channel_id:
                try:
                    chat_info = bot.get_chat(settings['send_channel'])
                    if chat_info.username:
                        main_channel_link = f"https://t.me/{chat_info.username}"
                        post_link = f"https://t.me/{chat_info.username}/{last_sent_to_channel_id}"
                        channel_display = f"@{chat_info.username}"
                    else:
                        main_channel_link = bot.export_chat_invite_link(settings['send_channel'])
                        clean_id = str(settings['send_channel']).replace("-100", "")
                        post_link = f"https://t.me/c/{clean_id}/{last_sent_to_channel_id}"
                        channel_display = "আমাদের চ্যানেল"

                    response_text = (
                        "✅ **ফাইলটি সফলভাবে চ্যানেলে পাঠানো হয়েছে!**\n\n"
                        f"📢 **চ্যানেল লিঙ্ক:** [এখানে ক্লিক করুন]({main_channel_link})\n"
                        f"🚀 **ফাইলের পোস্ট লিঙ্ক:** [এখানে ক্লিক করুন]({post_link})\n\n"
                        "👆 ওপরের লিঙ্কে ক্লিক করলে সরাসরি ফাইলে নিয়ে যাবে।"
                    )
                    action_btns = types.InlineKeyboardMarkup(row_width=1)
                    action_btns.add(
                        types.InlineKeyboardButton("📢 Join Main Channel", url=main_channel_link),
                        types.InlineKeyboardButton("📂 View File Post", url=post_link)
                    )
                    bot.send_message(message.chat.id, response_text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=action_btns)
                except Exception as e:
                    bot.send_message(message.chat.id, f"✅ ফাইলগুলো চ্যানেলে পাঠানো হয়েছে।")
        else:
            bot.send_message(message.chat.id, "❌ দুঃখিত, ফাইলটি খুঁজে পাওয়া যায়নি।")
        return

    # সাধারণ স্টার্ট মেসেজ
    user = message.from_user
    full_name = f"{user.first_name} {user.last_name if user.last_name else ''}".strip()
    start_text = (
        f"👋 হ্যালো, **{full_name}**\n\n"
        f"🆔 ইউজার আইডি: `{user.id}`\n"
        f"👤 নাম: `{user.first_name}`\n"
        f"📛 ফুল নাম: `{full_name}`\n"
        f"🔗 ইউজারনেম: @{user.username if user.username else 'None'}\n\n"
        "আমাদের বট থেকে ফাইল পেতে চ্যানেলে জয়েন থাকা বাধ্যতামূলক।"
    )
    
    try:
        bot.send_photo(message.chat.id, settings.get('logo_url'), caption=start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, start_text, reply_markup=get_channel_buttons(), parse_mode="Markdown")

# --- এডমিন কমান্ডস ---

@bot.message_handler(commands=['add'])
def add_batch(message):
    if message.from_user.id != ADMIN_ID: return
    user_states[message.from_user.id] = {'step': 1}
    bot.send_message(message.chat.id, "📂 **ব্যাচ সিস্টেম চালু হয়েছে।**\n\nপ্রথমে আপনার স্টোরেজ চ্যানেলের **প্রথম ফাইলটির লিঙ্ক** দিন:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('step') == 1)
def process_batch_step1(message):
    m_id = get_message_id(message.text)
    if m_id:
        user_states[message.from_user.id]['start_id'] = m_id
        user_states[message.from_user.id]['step'] = 2
        bot.send_message(message.chat.id, "✅ প্রথম আইডি পাওয়া গেছে।\n\nএখন ওই রেঞ্জের **শেষ ফাইলটির লিঙ্ক** দিন:")
    else:
        bot.send_message(message.chat.id, "❌ ভুল লিঙ্ক! সঠিক মেসেজ লিঙ্ক দিন।")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('step') == 2)
def process_batch_step2(message):
    m_id = get_message_id(message.text)
    if m_id:
        data = user_states[message.from_user.id]
        settings = get_settings()
        if not settings.get('log_channel'):
            return bot.reply_to(message, "❌ আগে `/log_cnl` সেট করুন।")

        key = str(uuid.uuid4())[:8]
        raw_link = f"https://t.me/{bot.get_me().username}?start={key}"
        short_link = get_short_link(raw_link)

        links_col.insert_one({
            "key": key,
            "start_id": data['start_id'],
            "end_id": m_id,
            "log_channel": settings['log_channel']
        })
        del user_states[message.from_user.id]
        bot.send_message(message.chat.id, f"✅ **ব্যাচ লিঙ্ক তৈরি হয়েছে!**\n\n🔗 সর্ট: `{short_link}`\n🔗 ডিরেক্ট: `{raw_link}`", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ ভুল লিঙ্ক!")

@bot.message_handler(commands=['del_all'])
def delete_all_links(message):
    if message.from_user.id != ADMIN_ID: return
    links_col.delete_many({})
    bot.reply_to(message, "🗑️ **ডাটাবেসের সকল লিঙ্ক ডিলিট করা হয়েছে!**")

@bot.message_handler(commands=['broadcast'])
def broadcast_users(message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message:
        return bot.reply_to(message, "মেসেজটি রিপ্লাই দিন এবং লিখুন `/broadcast`")
    users = users_col.find({})
    success = 0
    for u in users:
        try:
            bot.copy_message(u['user_id'], message.chat.id, message.reply_to_message.message_id)
            success += 1
            time.sleep(0.05)
        except: continue
    bot.send_message(message.chat.id, f"✅ ইউজার ব্রডকাস্ট শেষ! {success} জনকে পাঠানো হয়েছে।")

@bot.message_handler(commands=['c_broadcast'])
def broadcast_channels(message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message:
        return bot.reply_to(message, "মেসেজটি রিপ্লাই দিয়ে লিখুন `/c_broadcast`")
    chats = chats_col.find({})
    success = 0
    for c in chats:
        try:
            bot.copy_message(c['chat_id'], message.chat.id, message.reply_to_message.message_id)
            success += 1
            time.sleep(0.1)
        except: continue
    bot.send_message(message.chat.id, f"📢 মোট {success}টি চ্যানেল/গ্রুপে ব্রডকাস্ট করা হয়েছে।")

@bot.message_handler(commands=['fsub_on'])
def fsub_on(message):
    if message.from_user.id != ADMIN_ID: return
    settings_col.update_one({"id": "bot_settings"}, {"$set": {"fsub_active": True}}, upsert=True)
    bot.reply_to(message, "✅ **ফোর্স সাবস্ক্রাইব অন করা হয়েছে।**")

@bot.message_handler(commands=['fsub_off'])
def fsub_off(message):
    if message.from_user.id != ADMIN_ID: return
    settings_col.update_one({"id": "bot_settings"}, {"$set": {"fsub_active": False}}, upsert=True)
    bot.reply_to(message, "⚠️ **ফোর্স সাবস্ক্রাইব অফ করা হয়েছে।**")

@bot.message_handler(commands=['set_logo'])
def set_logo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        url = message.text.split()[1]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"logo_url": url}}, upsert=True)
        bot.reply_to(message, "✅ লগো আপডেট হয়েছে।")
    except:
        bot.reply_to(message, "ব্যবহার: `/set_logo URL`")

@bot.message_handler(commands=['status'])
def status(message):
    if message.from_user.id != ADMIN_ID: return
    u_count = users_col.count_documents({})
    f_count = links_col.count_documents({})
    c_count = chats_col.count_documents({})
    settings = get_settings()
    fsub_status = "✅ चालू" if settings.get('fsub_active', True) else "❌ বন্ধ"
    bot.reply_to(message, f"📊 **স্ট্যাটাস**\n\n👥 মোট ইউজার: {u_count}\n📁 ফাইল লিঙ্ক: {f_count}\n📢 কানেক্টেড চ্যাট: {c_count}\n📢 ফোর্স সাবস্ক্রাইব: {fsub_status}", parse_mode="Markdown")

@bot.message_handler(commands=['log_cnl', 'send_cnl'])
def set_channels(message):
    if message.from_user.id != ADMIN_ID: return
    key = "log_channel" if "log" in message.text else "send_channel"
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {key: cid}}, upsert=True)
        bot.reply_to(message, f"✅ {key} আপডেট: `{cid}`")
    except:
        bot.reply_to(message, "আইডি দিন। উদাহরণ: `/log_cnl -100xxx`")

@bot.message_handler(commands=['set_force'])
def set_force(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        ids_text = message.text.replace('/set_force', '').strip()
        if not ids_text:
            settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": []}})
            return bot.reply_to(message, "✅ রিমুভ করা হয়েছে।")
        ids = [int(i.strip()) for i in ids_text.split(',') if i.strip()]
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": ids}}, upsert=True)
        bot.reply_to(message, f"✅ মোট {len(ids)}টি চ্যানেল সেট হয়েছে।")
    except:
        bot.reply_to(message, "ভুল ফরম্যাট।")

# --- সিঙ্গেল ফাইল হ্যান্ডলিং (আপনার মেইন কোড অনুযায়ী) ---

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo', 'voice', 'animation'])
def handle_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'):
        return bot.reply_to(message, "❌ আগে `/log_cnl` সেট করুন।")

    key = str(uuid.uuid4())[:8]
    raw_link = f"https://t.me/{bot.get_me().username}?start={key}"
    short_link = get_short_link(raw_link)

    try:
        sent_log = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id)
        links_col.insert_one({"key": key, "msg_id": sent_log.message_id, "log_channel": settings['log_channel']})
        btn = types.InlineKeyboardButton("🔗 Short Link", url=short_link)
        bot.reply_to(message, f"✅ **ফাইল সেভ হয়েছে!**\n\n🔗 সর্ট লিঙ্ক: `{short_link}`\n🔗 ডিরেক্ট লিঙ্ক: `{raw_link}`", parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(btn))
    except Exception as e:
        bot.reply_to(message, f"❌ ভুল: {str(e)}")

# --- সার্ভার ও ওয়েবহুক ---

@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def index():
    return "Bot Running!", 200

@app.route("/set_webhook")
def set_webhook():
    s = bot.set_webhook(url=f"{WEB_URL}/{API_TOKEN}")
    return "Webhook Success!" if s else "Webhook Failed."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
