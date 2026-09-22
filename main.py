import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, request, jsonify, render_template_string
import threading
import requests
import time
import os
from supabase import create_client, Client

BOT_TOKEN = os.environ.get("BOT_TOKEN", "यहाँ_अपना_टोकन_डालें")
APP_LINK = os.environ.get("APP_LINK", "https://post-bot-i3rk.onrender.com")
DEFAULT_CHANNEL = "@novelxplin"
OWNER_ID = 6069200310

SUPABASE_URL = os.environ.get("SUPABASE_URL", "यहाँ_अपना_supabase_url_डालें")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "यहाँ_अपना_supabase_key_डालें")

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "यहाँ_अपना_supabase_url_डालें":
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

user_posts = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>आँकड़े</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: Arial, sans-serif; padding: 15px; background-color: var(--tg-theme-bg-color, #fff); color: var(--tg-theme-text-color, #000); }
        h2 { color: var(--tg-theme-button-color, #2481cc); font-size: 1.2em; border-bottom: 2px solid var(--tg-theme-button-color, #2481cc); padding-bottom: 5px; }
        .card { border: 1px solid var(--tg-theme-hint-color, #ccc); padding: 12px; margin-bottom: 12px; border-radius: 8px; background-color: var(--tg-theme-secondary-bg-color, #f4f4f5); }
        .leaderboard { background-color: var(--tg-theme-secondary-bg-color, #f4f4f5); padding: 12px; border-radius: 8px; margin-bottom: 20px;}
        .rank-item { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #ddd; }
        .rank-item:last-child { border-bottom: none; }
        .rank-name { font-weight: bold; }
        .link-box { margin-top: 8px; padding: 6px; background: #e0f7fa; border-radius: 5px; word-break: break-all; font-size: 0.9em; color: #006064;}
        .hidden-link { margin-top: 8px; padding: 6px; background: #ffebee; border-radius: 5px; font-size: 0.9em; color: #c62828;}
    </style>
</head>
<body>
    <h2>🏆 वैश्विक रैंक</h2>
    <div id="leaderboard" class="leaderboard">प्रतीक्षा करें...</div>

    <h2>📝 प्रकाशित संदेश</h2>
    <div id="all_posts">प्रतीक्षा करें...</div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 0;

        fetch(`/api/data?user_id=${userId}`)
        .then(res => res.json())
        .then(data => {
            let lbHtml = "";
            if (data.leaderboard && data.leaderboard.length > 0) {
                data.leaderboard.forEach((u, index) => {
                    let medal = index === 0 ? "🥇" : index === 1 ? "🥈" : index === 2 ? "🥉" : "🔹";
                    lbHtml += `<div class="rank-item"><span class="rank-name">${medal} ${u.username || 'उपयोगकर्ता'}</span> <span>${u.total_posts} संदेश</span></div>`;
                });
            } else {
                lbHtml = "कोई जानकारी उपलब्ध नहीं है।";
            }
            document.getElementById('leaderboard').innerHTML = lbHtml;

            let postsHtml = "";
            if (data.posts && data.posts.length > 0) {
                data.posts.forEach(p => {
                    let linkHtml = p.show_link 
                        ? `<div class="link-box">🔗 कड़ी: <a href="${p.btn_url}" target="_blank">${p.btn_url}</a></div>` 
                        : `<div class="hidden-link">🔒 कड़ी छिपी हुई है (केवल निर्माता और व्यवस्थापक के लिए)</div>`;
                    
                    postsHtml += `<div class="card">
                        <div><b>संदेश:</b> ${p.message_text}</div>
                        <div style="margin-top:5px;"><b>कुंजी:</b> ${p.btn_name}</div>
                        <div style="margin-top:5px; font-size:0.8em; color:gray;">👤 निर्माता क्रमांक: ${p.user_id}</div>
                        ${linkHtml}
                    </div>`;
                });
            } else {
                postsHtml = "कोई संदेश उपलब्ध नहीं है।";
            }
            document.getElementById('all_posts').innerHTML = postsHtml;
        })
        .catch(err => {
            document.getElementById('leaderboard').innerHTML = "त्रुटि।";
            document.getElementById('all_posts').innerHTML = "जानकारी प्राप्त करने में त्रुटि।";
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return "कार्यक्रम सही तरीके से काम कर रहा है!"

@app.route('/stats')
def stats_page():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def api_data():
    user_id = request.args.get('user_id', type=int, default=0)
    
    if not supabase:
        return jsonify({"leaderboard": [], "posts": []})

    try:
        lb_res = supabase.table('users').select('*').order('total_posts', desc=True).limit(10).execute()
        leaderboard = lb_res.data
    except:
        leaderboard = []

    try:
        posts_res = supabase.table('posts').select('*').order('created_at', desc=True).limit(50).execute()
        all_posts = posts_res.data
    except:
        all_posts = []

    for p in all_posts:
        if user_id == p['user_id'] or user_id == OWNER_ID:
            p['show_link'] = True
        else:
            p['show_link'] = False

    return jsonify({"leaderboard": leaderboard, "posts": all_posts})

def ping_system():
    while True:
        time.sleep(300)
        try:
            if APP_LINK:
                requests.get(APP_LINK)
        except:
            pass

def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add(KeyboardButton("📝 नया संदेश बनाएँ"))
    markup.add(KeyboardButton("📊 आँकड़े (मिनी ऐप)", web_app=WebAppInfo(url=APP_LINK + "/stats")))
    markup.add(KeyboardButton("❌ रद्द करें"))
    return markup

def get_cancel_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("❌ रद्द करें"))
    return markup

def get_publish_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton(f"📢 {DEFAULT_CHANNEL} पर भेजें"))
    markup.add(KeyboardButton("💬 किसी अन्य समूह में भेजें"))
    markup.add(KeyboardButton("❌ रद्द करें"))
    return markup

@bot.message_handler(commands=['start'])
def start_message(message):
    text = "नमस्ते! मैं आपका उन्नत संदेश प्रकाशक रोबोट हूँ।\nकृपया नीचे दिए गए कुंजीपटल का उपयोग करें।"
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "❌ रद्द करें")
def cancel_action(message):
    if message.chat.id in user_posts:
        del user_posts[message.chat.id]
    bot.send_message(message.chat.id, "प्रक्रिया रद्द कर दी गई है।", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "📝 नया संदेश बनाएँ")
def start_create_post(message):
    user_posts[message.chat.id] = {}
    msg = bot.send_message(message.chat.id, "कृपया अपने संदेश का मुख्य पाठ लिखकर भेजें (आप <b>मोटा</b> या <i>तिरछा</i> करने के लिए HTML का उपयोग कर सकते हैं):", reply_markup=get_cancel_menu(), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_post_text)

def process_post_text(message):
    if message.text == "❌ रद्द करें":
        return cancel_action(message)
    
    user_posts[message.chat.id]['text'] = message.text
    msg = bot.send_message(message.chat.id, "बहुत बढ़िया! अब वह नाम लिखकर भेजें जो आप कुंजी (बटन) पर दिखाना चाहते हैं:")
    bot.register_next_step_handler(msg, process_button_name)

def process_button_name(message):
    if message.text == "❌ रद्द करें":
        return cancel_action(message)
    
    user_posts[message.chat.id]['btn_name'] = message.text
    msg = bot.send_message(message.chat.id, "उत्कृष्ट! अब इस कुंजी के लिए कड़ी (लिंक) या @username लिखकर भेजें:")
    bot.register_next_step_handler(msg, process_button_url)

def process_button_url(message):
    if message.text == "❌ रद्द करें":
        return cancel_action(message)
    
    url = message.text.strip()
    
    if url.startswith("@"):
        url = f"https://t.me/{url[1:]}"
    elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        url = "https://" + url

    user_posts[message.chat.id]['btn_url'] = url
    
    text = user_posts[message.chat.id]['text']
    btn_name = user_posts[message.chat.id]['btn_name']
    btn_url = user_posts[message.chat.id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))
    
    bot.send_message(message.chat.id, "आपके संदेश का पूर्वावलोकन यहाँ है:")
    try:
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=inline_markup)
        msg = bot.send_message(message.chat.id, "क्या आप इस पूर्वावलोकन से संतुष्ट हैं? आप इसे कहाँ प्रकाशित करना चाहते हैं?", reply_markup=get_publish_menu())
        bot.register_next_step_handler(msg, process_publish_decision)
    except Exception as e:
        bot.send_message(message.chat.id, "त्रुटि! कृपया सुनिश्चित करें कि आपके HTML टैग सही हैं।", reply_markup=get_main_menu())
        del user_posts[message.chat.id]

def save_to_supabase(user_id, username, text, btn_name, btn_url):
    if not supabase:
        return
    try:
        user_check = supabase.table('users').select('*').eq('id', user_id).execute()
        if len(user_check.data) == 0:
            supabase.table('users').insert({'id': user_id, 'username': username, 'total_posts': 1}).execute()
        else:
            current_posts = user_check.data[0]['total_posts']
            supabase.table('users').update({'username': username, 'total_posts': current_posts + 1}).eq('id', user_id).execute()

        supabase.table('posts').insert({
            'user_id': user_id,
            'message_text': text,
            'btn_name': btn_name,
            'btn_url': btn_url
        }).execute()
    except Exception as e:
        pass

def process_publish_decision(message):
    if message.text == "❌ रद्द करें":
        return cancel_action(message)
        
    chat_id = message.chat.id
    if chat_id not in user_posts:
        bot.send_message(chat_id, "सत्र समाप्त हो गया है। कृपया पुनः प्रयास करें।", reply_markup=get_main_menu())
        return

    text = user_posts[chat_id]['text']
    btn_name = user_posts[chat_id]['btn_name']
    btn_url = user_posts[chat_id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))

    username = message.from_user.username or message.from_user.first_name
    user_id = message.from_user.id

    if message.text == f"📢 {DEFAULT_CHANNEL} पर भेजें":
        try:
            bot.send_message(DEFAULT_CHANNEL, text, parse_mode="HTML", reply_markup=inline_markup)
            save_to_supabase(user_id, username, text, btn_name, btn_url)
            bot.send_message(chat_id, f"संदेश सफलतापूर्वक {DEFAULT_CHANNEL} पर प्रकाशित कर दिया गया है!", reply_markup=get_main_menu())
            del user_posts[chat_id]
        except Exception as e:
            bot.send_message(chat_id, f"त्रुटि: कृपया सुनिश्चित करें कि मैं {DEFAULT_CHANNEL} में व्यवस्थापक हूँ।", reply_markup=get_main_menu())
            
    elif message.text == "💬 किसी अन्य समूह में भेजें":
        msg = bot.send_message(chat_id, "कृपया चैनल या समूह का नाम (जैसे @mychannel) लिखकर भेजें:", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, process_custom_publish)
    else:
        bot.send_message(chat_id, "अमान्य विकल्प।", reply_markup=get_main_menu())

def process_custom_publish(message):
    if message.text == "❌ रद्द करें":
        return cancel_action(message)
        
    chat_id = message.chat.id
    target_chat = message.text.strip()
    
    if chat_id not in user_posts:
        bot.send_message(chat_id, "सत्र समाप्त हो गया है।", reply_markup=get_main_menu())
        return
        
    text = user_posts[chat_id]['text']
    btn_name = user_posts[chat_id]['btn_name']
    btn_url = user_posts[chat_id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))
    
    username = message.from_user.username or message.from_user.first_name
    user_id = message.from_user.id

    try:
        bot.send_message(target_chat, text, parse_mode="HTML", reply_markup=inline_markup)
        save_to_supabase(user_id, username, text, btn_name, btn_url)
        bot.send_message(chat_id, f"संदेश सफलतापूर्वक {target_chat} पर प्रकाशित कर दिया गया है!", reply_markup=get_main_menu())
        del user_posts[chat_id]
    except Exception as e:
        bot.send_message(chat_id, "संदेश भेजने में विफलता। कृपया सुनिश्चित करें कि मैं वहाँ व्यवस्थापक हूँ।", reply_markup=get_main_menu())

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=ping_system)
    ping_thread.start()

    bot.infinity_polling()
