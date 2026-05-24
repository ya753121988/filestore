import os
import telebot
import uuid
import requests
from flask import Flask, request
from pymongo import MongoClient
from telebot import types

# --- কনফিগারেশন ---
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

# --- বাটন জেনারেটর ফাংশন (ইউজারদের জন্য) ---
def get_channel_buttons(extra_button=None):
    settings = get_settings()
    channels = settings.get('force_channels', [])
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    for i, channel_id in enumerate(channels, 1):
        try:
            chat = bot.get_chat(channel_id)
            link = f"https://t.me/{chat.username}" if chat.username else bot.export_chat_invite_link(channel_id)
            buttons.append(types.InlineKeyboardButton(f"Channel {i} 📢", url=link))
        except:
            continue
    
    markup.add(*buttons)
    if extra_button:
        markup.add(extra_button)
        
    return markup

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

# --- ফ্লাস্ক রুটস ---
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
    
    if len(args) > 1:
        key = args[1]
        data = links_col.find_one({"key": key})
        settings = get_settings()
        
        if data and settings.get('send_channel'):
            try:
                sent_msg = bot.copy_message(
                    chat_id=settings['send_channel'],
                    from_chat_id=data['log_channel'],
                    message_id=data['msg_id']
                )
                
                channel_info = bot.get_chat(settings['send_channel'])
                msg_id = sent_msg.message_id
                msg_link = f"https://t.me/{channel_info.username}/{msg_id}" if channel_info.username else f"https://t.me/c/{str(settings['send_channel']).replace('-100', '')}/{msg_id}"

                btn = types.InlineKeyboardButton("🚀 ফাইলটি দেখুন (Watch Now)", url=msg_link)
                markup = get_channel_buttons(extra_button=btn)
                
                bot.send_message(message.chat.id, "✅ **আপনার ফাইলটি রেডি! নিচের বাটনে ক্লিক করুন।**", reply_markup=markup, parse_mode="Markdown")
            except Exception as e:
                bot.reply_to(message, f"❌ ত্রুটি: {str(e)}")
        return

    markup = get_channel_buttons()
    bot.send_message(message.chat.id, "👋 **স্বাগতম! আমাদের চ্যানেল লিস্ট:**", reply_markup=markup, parse_mode="Markdown")

# --- এডমিন কমান্ডস: চ্যানেল ম্যানেজমেন্ট ---

@bot.message_handler(commands=['set_force'])
def set_force_channels(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        input_text = message.text.replace('/set_force', '').strip()
        if not input_text:
            bot.reply_to(message, "ব্যবহার: `/set_force -100123, -100456`")
            return
        
        new_channels = [int(i.strip()) for i in input_text.split(',')]
        settings = get_settings()
        current_channels = settings.get('force_channels', [])
        
        # ডুপ্লিকেট বাদ দিয়ে আপডেট করা
        updated_list = list(set(current_channels + new_channels))
        
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": updated_list}}, upsert=True)
        bot.reply_to(message, f"✅ নতুন {len(new_channels)}টি চ্যানেল যোগ করা হয়েছে।\nএখন মোট চ্যানেল: {len(updated_list)}টি।")
    except:
        bot.reply_to(message, "ভুল আইডি দিয়েছেন।")

@bot.message_handler(commands=['manage_channels'])
def manage_channels(message):
    if message.from_user.id != ADMIN_ID: return
    
    settings = get_settings()
    channels = settings.get('force_channels', [])
    
    if not channels:
        bot.reply_to(message, "কোনো চ্যানেল সেট করা নেই।")
        return

    markup = types.InlineKeyboardMarkup()
    for cid in channels:
        try:
            chat = bot.get_chat(cid)
            title = chat.title if chat.title else cid
        except:
            title = f"Unknown ({cid})"
            
        markup.add(
            types.InlineKeyboardButton(f"Channel: {title}", url="https://t.me/example"), # জাস্ট নাম দেখানোর জন্য
            types.InlineKeyboardButton(f"❌ Delete", callback_query_data=f"del_{cid}")
        )
    
    bot.send_message(message.chat.id, "⚙️ **চ্যানেল ম্যানেজমেন্ট:**\nনিচের লিস্ট থেকে চ্যানেল ডিলিট করতে পারবেন।", reply_markup=markup, parse_mode="Markdown")

# --- বাটন ক্লিক হ্যান্ডলার (ডিলিট করার জন্য) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def handle_delete_channel(call):
    if call.from_user.id != ADMIN_ID: return
    
    channel_id = int(call.data.replace('del_', ''))
    settings = get_settings()
    channels = settings.get('force_channels', [])
    
    if channel_id in channels:
        channels.remove(channel_id)
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"force_channels": channels}})
        
        # মেসেজ আপডেট করা
        bot.answer_callback_query(call.id, "✅ চ্যানেলটি ডিলিট করা হয়েছে।")
        
        # নতুন লিস্ট দেখানো
        if not channels:
            bot.edit_message_text("কোনো চ্যানেল নেই।", call.message.chat.id, call.message.message_id)
        else:
            new_markup = types.InlineKeyboardMarkup()
            for cid in channels:
                try:
                    chat = bot.get_chat(cid)
                    title = chat.title
                except:
                    title = cid
                new_markup.add(
                    types.InlineKeyboardButton(f"Channel: {title}", url="https://t.me/example"),
                    types.InlineKeyboardButton(f"❌ Delete", callback_query_data=f"del_{cid}")
                )
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=new_markup)
    else:
        bot.answer_callback_query(call.id, "চ্যানেলটি পাওয়া যায়নি।", show_alert=True)

# --- অন্যান্য সেটিংস কমান্ডস ---
@bot.message_handler(commands=['log_cnl'])
def set_log_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"log_channel": cid}}, upsert=True)
        bot.reply_to(message, f"✅ লগ চ্যানেল সেট হয়েছে: `{cid}`")
    except: bot.reply_to(message, "ব্যবহার: `/log_cnl -100xxxxxx`")

@bot.message_handler(commands=['send_cnl'])
def set_send_channel(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cid = int(message.text.split()[1])
        settings_col.update_one({"id": "bot_settings"}, {"$set": {"send_channel": cid}}, upsert=True)
        bot.reply_to(message, f"✅ সেন্ড চ্যানেল সেট হয়েছে: `{cid}`")
    except: bot.reply_to(message, "ব্যবহার: `/send_cnl -100xxxxxx`")

# --- ফাইল হ্যান্ডলিং ---
@bot.message_handler(content_types=['document', 'video', 'audio', 'photo'])
def handle_admin_files(message):
    if message.from_user.id != ADMIN_ID: return
    settings = get_settings()
    if not settings.get('log_channel'):
        bot.reply_to(message, "আগে `/log_cnl` সেট করুন।")
        return

    sent_msg = bot.copy_message(settings['log_channel'], message.chat.id, message.message_id)
    key = str(uuid.uuid4())[:8]
    raw_link = f"https://t.me/{bot.get_me().username}?start={key}"
    short_link = get_short_link(raw_link)

    links_col.insert_one({"key": key, "msg_id": sent_msg.message_id, "log_channel": settings['log_channel']})

    response_text = f"✅ **ফাইল সেভ হয়েছে!**\n\n🔗 **বট লিঙ্ক:** `{raw_link}`\n🌐 **শর্ট লিঙ্ক:** `{short_link}`"
    btn = types.InlineKeyboardButton("📥 Download Link", url=short_link)
    markup = get_channel_buttons(extra_button=btn)
    bot.reply_to(message, response_text, reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
