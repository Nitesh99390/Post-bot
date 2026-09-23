import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, MenuButtonWebApp
from flask import Flask, request, jsonify, render_template_string
import threading
import requests
import time
import os
import json
from supabase import create_client, Client

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
APP_LINK = os.environ.get("APP_LINK", "https://post-bot-i3rk.onrender.com")
DEFAULT_CHANNEL = "@novelxplin"
OWNER_ID = 6069200310

SUPABASE_URL = os.environ.get("SUPABASE_URL", "PUT_YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "PUT_YOUR_SUPABASE_KEY_HERE")

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "PUT_YOUR_SUPABASE_URL_HERE":
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

user_posts = {}

# Ultra-Modern & Smooth UI Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Bot Statistics</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --primary: var(--tg-theme-button-color, #2481cc);
            --bg: var(--tg-theme-bg-color, #ffffff);
            --text: var(--tg-theme-text-color, #000000);
            --hint: var(--tg-theme-hint-color, #999999);
            --sec-bg: var(--tg-theme-secondary-bg-color, #f4f4f5);
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 16px;
            -webkit-font-smoothing: antialiased;
        }
        h2 {
            color: var(--primary);
            font-size: 1.3em;
            margin-top: 24px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
        }
        .card {
            background-color: var(--sec-bg);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            animation: fadeIn 0.5s ease forwards;
            opacity: 0;
        }
        .leaderboard {
            background-color: var(--sec-bg);
            border-radius: 16px;
            padding: 8px 16px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            animation: fadeIn 0.4s ease forwards;
        }
        .rank-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 0;
            border-bottom: 1px solid rgba(153, 153, 153, 0.2);
        }
        .rank-item:last-child { border-bottom: none; }
        .rank-name { font-weight: 600; font-size: 1.05em; display: flex; align-items: center; gap: 8px;}
        .rank-score { 
            font-weight: bold; 
            color: var(--primary); 
            background: rgba(36, 129, 204, 0.1); 
            padding: 4px 12px; 
            border-radius: 20px; 
            font-size: 0.85em; 
        }
        .link-box { 
            margin-top: 12px; padding: 12px; 
            background: rgba(0, 150, 136, 0.1); 
            border-radius: 10px; word-break: break-all; 
            font-size: 0.9em; border-left: 4px solid #009688; 
            color: var(--text);
            line-height: 1.4;
        }
        .link-box a { color: var(--primary); text-decoration: none; font-weight: 600; }
        .hidden-link { 
            margin-top: 12px; padding: 12px; 
            background: rgba(244, 67, 54, 0.1); 
            border-radius: 10px; font-size: 0.9em; 
            border-left: 4px solid #f44336; 
            color: var(--text);
        }
        .post-text { margin-bottom: 12px; white-space: pre-wrap; font-size: 1.05em; line-height: 1.4;}
        .post-meta { margin-top: 12px; font-size: 0.8em; color: var(--hint); display: flex; align-items: center; gap: 5px; font-weight: 500;}
        
        .loader {
            border: 3px solid rgba(0,0,0,0.1);
            border-top: 3px solid var(--primary);
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
            margin: 30px auto;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <h2>🏆 Global Leaderboard</h2>
    <div id="leaderboard" class="leaderboard"><div class="loader"></div></div>

    <h2>📝 Created Posts</h2>
    <div id="all_posts"><div class="loader"></div></div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();
        
        const userId = tg.initDataUnsafe?.user?.id || 0;

        fetch(`/api/data?user_id=${userId}`)
        .then(res => res.json())
        .then(data => {
            let lbHtml = "";
            if (data.leaderboard && data.leaderboard.length > 0) {
                data.leaderboard.forEach((u, index) => {
                    let medal = index === 0 ? "🥇" : index === 1 ? "🥈" : index === 2 ? "🥉" : "👤";
                    lbHtml += `<div class="rank-item"><span class="rank-name">${medal} ${u.username || 'Unknown'}</span> <span class="rank-score">${u.total_posts} Posts</span></div>`;
                });
            } else {
                lbHtml = "<div style='padding: 10px 0; text-align: center; color: var(--hint);'>No data available yet.</div>";
            }
            document.getElementById('leaderboard').innerHTML = lbHtml;

            let postsHtml = "";
            if (data.posts && data.posts.length > 0) {
                data.posts.forEach((p, index) => {
                    let btnNamesStr = p.btn_name;
                    let btnUrlsStr = p.btn_url;
                    let linksHtml = "";
                    let displayedNames = btnNamesStr;
                    
                    try {
                        let names = JSON.parse(btnNamesStr);
                        let urls = JSON.parse(btnUrlsStr);
                        displayedNames = names.join(' • ');
                        
                        if (p.show_link) {
                            urls.forEach((u, i) => {
                                linksHtml += `<div class="link-box">🔗 <b>Button ${i+1}:</b> <br><a href="${u}" target="_blank">${u}</a></div>`;
                            });
                        } else {
                            linksHtml = `<div class="hidden-link">🔒 <b>${names.length} Link(s) hidden</b> <br><span style="font-size:0.9em; opacity:0.8;">(Visible only to creator & Admin)</span></div>`;
                        }
                    } catch(e) {
                        if (p.show_link) {
                            linksHtml = `<div class="link-box">🔗 <b>Link:</b> <br><a href="${btnUrlsStr}" target="_blank">${btnUrlsStr}</a></div>`;
                        } else {
                            linksHtml = `<div class="hidden-link">🔒 <b>Link hidden</b> <br><span style="font-size:0.9em; opacity:0.8;">(Visible only to creator & Admin)</span></div>`;
                        }
                    }
                    
                    let animDelay = index * 0.1;
                    postsHtml += `<div class="card" style="animation-delay: ${animDelay}s;">
                        <div class="post-text">${p.message_text}</div>
                        <div style="font-weight:600; margin-bottom: 8px;">🔘 ${displayedNames}</div>
                        ${linksHtml}
                        <div class="post-meta">🆔 Creator ID: ${p.user_id}</div>
                    </div>`;
                });
            } else {
                postsHtml = "<div style='text-align: center; color: var(--hint); padding: 20px 0;'>No posts available yet.</div>";
            }
            document.getElementById('all_posts').innerHTML = postsHtml;
        })
        .catch(err => {
            document.getElementById('leaderboard').innerHTML = "<div style='color: #f44336; text-align:center; padding: 10px;'>Failed to load data.</div>";
            document.getElementById('all_posts').innerHTML = "";
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return "Bot is running perfectly!"

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
    markup.add(KeyboardButton("📝 Create Post"))
    return markup

def get_cancel_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

def get_add_more_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("✅ Done Adding Buttons"))
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

def get_publish_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton(f"📢 Send to {DEFAULT_CHANNEL}"))
    markup.add(KeyboardButton("💬 Send to Custom Chat"))
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

@bot.message_handler(commands=['start'])
def start_message(message):
    try:
        bot.set_chat_menu_button(message.chat.id, MenuButtonWebApp(type="web_app", text="📊 Stats", web_app=WebAppInfo(url=APP_LINK + "/stats")))
    except:
        pass
    text = "Hello! I am your professional post bot.\nClick '📝 Create Post' to get started."
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "❌ Cancel")
def cancel_action(message):
    if message.chat.id in user_posts:
        del user_posts[message.chat.id]
    bot.send_message(message.chat.id, "Action canceled.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "📝 Create Post")
def start_create_post(message):
    user_posts[message.chat.id] = {'buttons': []}
    msg = bot.send_message(message.chat.id, "Please send the message text for your post\n(You can use HTML tags like <b>bold</b> or <i>italic</i>):", reply_markup=get_cancel_menu(), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_post_text)

def process_post_text(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    user_posts[message.chat.id]['text'] = message.text
    msg = bot.send_message(message.chat.id, "Great! Send the text for **Button 1**:", reply_markup=get_cancel_menu(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_button_name)

def process_button_name(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    if message.text == "✅ Done Adding Buttons":
        if len(user_posts[message.chat.id]['buttons']) > 0:
            finish_post_creation(message)
        else:
            msg = bot.send_message(message.chat.id, "You need to add at least 1 button. Send the text for Button 1:", reply_markup=get_cancel_menu())
            bot.register_next_step_handler(msg, process_button_name)
        return
        
    user_posts[message.chat.id]['current_btn_name'] = message.text
    msg = bot.send_message(message.chat.id, "Awesome! Now send the URL (Link) or @username for this button:", reply_markup=get_cancel_menu())
    bot.register_next_step_handler(msg, process_button_url)

def process_button_url(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    url = message.text.strip()
    
    if url.startswith("@"):
        url = f"https://t.me/{url[1:]}"
    elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        url = "https://" + url

    btn_name = user_posts[message.chat.id]['current_btn_name']
    user_posts[message.chat.id]['buttons'].append({'name': btn_name, 'url': url})
    
    btn_count = len(user_posts[message.chat.id]['buttons'])
    
    if btn_count >= 10:
        bot.send_message(message.chat.id, "Maximum limit of 10 buttons reached!")
        finish_post_creation(message)
    else:
        msg = bot.send_message(message.chat.id, f"Button {btn_count} added successfully! ✅\n\nSend the text for **Button {btn_count + 1}**, or click **'Done Adding Buttons'** to proceed.", reply_markup=get_add_more_menu(), parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_button_name)

def finish_post_creation(message):
    chat_id = message.chat.id
    buttons = user_posts[chat_id]['buttons']
    text = user_posts[chat_id]['text']
    
    inline_markup = InlineKeyboardMarkup()
    for btn in buttons:
        inline_markup.add(InlineKeyboardButton(btn['name'], url=btn['url']))
        
    names_json = json.dumps([b['name'] for b in buttons])
    urls_json = json.dumps([b['url'] for b in buttons])
    
    username = message.from_user.username or message.from_user.first_name
    user_id = message.from_user.id
    save_to_supabase(user_id, username, text, names_json, urls_json)
    
    bot.send_message(chat_id, "Here is a preview of your post:")
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=inline_markup)
        msg = bot.send_message(chat_id, "Post created and saved! Where do you want to publish it?", reply_markup=get_publish_menu())
        bot.register_next_step_handler(msg, process_publish_decision)
    except Exception as e:
        bot.send_message(chat_id, "Error! Please make sure your HTML tags are correct.", reply_markup=get_main_menu())
        del user_posts[chat_id]

def save_to_supabase(user_id, username, text, btn_name_json, btn_url_json):
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
            'btn_name': btn_name_json,
            'btn_url': btn_url_json
        }).execute()
    except Exception as e:
        pass

def process_publish_decision(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
        
    chat_id = message.chat.id
    if chat_id not in user_posts:
        bot.send_message(chat_id, "Session expired. Please try again.", reply_markup=get_main_menu())
        return

    text = user_posts[chat_id]['text']
    buttons = user_posts[chat_id]['buttons']
    
    inline_markup = InlineKeyboardMarkup()
    for btn in buttons:
        inline_markup.add(InlineKeyboardButton(btn['name'], url=btn['url']))

    if message.text == f"📢 Send to {DEFAULT_CHANNEL}":
        try:
            bot.send_message(DEFAULT_CHANNEL, text, parse_mode="HTML", reply_markup=inline_markup)
            bot.send_message(chat_id, f"Successfully published to {DEFAULT_CHANNEL}!", reply_markup=get_main_menu())
            del user_posts[chat_id]
        except Exception as e:
            bot.send_message(chat_id, f"Error: Make sure I am an admin in {DEFAULT_CHANNEL}.", reply_markup=get_main_menu())
            
    elif message.text == "💬 Send to Custom Chat":
        msg = bot.send_message(chat_id, "Please send the Username (e.g., @mychannel) or ID of the channel/group:", reply_markup=get_cancel_menu())
        bot.register_next_step_handler(msg, process_custom_publish)
    else:
        bot.send_message(chat_id, "Invalid option.", reply_markup=get_main_menu())

def process_custom_publish(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
        
    chat_id = message.chat.id
    target_chat = message.text.strip()
    
    if chat_id not in user_posts:
        bot.send_message(chat_id, "Session expired.", reply_markup=get_main_menu())
        return
        
    text = user_posts[chat_id]['text']
    buttons = user_posts[chat_id]['buttons']
    
    inline_markup = InlineKeyboardMarkup()
    for btn in buttons:
        inline_markup.add(InlineKeyboardButton(btn['name'], url=btn['url']))

    try:
        bot.send_message(target_chat, text, parse_mode="HTML", reply_markup=inline_markup)
        bot.send_message(chat_id, f"Successfully published to {target_chat}!", reply_markup=get_main_menu())
        del user_posts[chat_id]
    except Exception as e:
        bot.send_message(chat_id, "Failed to send. Please ensure the channel name is correct and I have admin rights.", reply_markup=get_main_menu())

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=ping_system)
    ping_thread.start()

    bot.infinity_polling()
