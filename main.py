import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import requests
import time
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "यहाँ_अपना_टोकन_डालें")
APP_LINK = os.environ.get("APP_LINK", "https://post-bot-i3rk.onrender.com")
DEFAULT_CHANNEL = "@novelxplin"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

user_posts = {}

@app.route('/')
def home():
    return "Bot is running perfectly!"

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
    markup.add(KeyboardButton("ℹ️ Help"))
    return markup

def get_cancel_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
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
    text = "Welcome to the Professional Post Bot!\nUse the keyboard below to navigate."
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "❌ Cancel")
def cancel_action(message):
    if message.chat.id in user_posts:
        del user_posts[message.chat.id]
    bot.send_message(message.chat.id, "Action canceled. Returning to main menu.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "ℹ️ Help")
def help_action(message):
    help_text = "I can help you create professional posts with inline buttons.\n\nClick on '📝 Create Post' to start building a post. You can send it directly to your channel from here."
    bot.send_message(message.chat.id, help_text, reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "📝 Create Post")
def start_create_post(message):
    user_posts[message.chat.id] = {}
    msg = bot.send_message(message.chat.id, "Please send the message text for your post:", reply_markup=get_cancel_menu())
    bot.register_next_step_handler(msg, process_post_text)

def process_post_text(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    user_posts[message.chat.id]['text'] = message.text
    msg = bot.send_message(message.chat.id, "Great! Now send the text you want to show on the button:")
    bot.register_next_step_handler(msg, process_button_name)

def process_button_name(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    user_posts[message.chat.id]['btn_name'] = message.text
    msg = bot.send_message(message.chat.id, "Awesome! Now send the URL (Link) for this button:\n(Make sure it starts with http:// or https://)")
    bot.register_next_step_handler(msg, process_button_url)

def process_button_url(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
    
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        msg = bot.send_message(message.chat.id, "Invalid URL. Please send a valid link starting with http:// or https://")
        bot.register_next_step_handler(msg, process_button_url)
        return

    user_posts[message.chat.id]['btn_url'] = url
    
    text = user_posts[message.chat.id]['text']
    btn_name = user_posts[message.chat.id]['btn_name']
    btn_url = user_posts[message.chat.id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))
    
    bot.send_message(message.chat.id, "Here is a preview of your post:")
    bot.send_message(message.chat.id, text, reply_markup=inline_markup)
    
    msg = bot.send_message(message.chat.id, "Are you satisfied with this preview? Where do you want to publish it?", reply_markup=get_publish_menu())
    bot.register_next_step_handler(msg, process_publish_decision)

def process_publish_decision(message):
    if message.text == "❌ Cancel":
        return cancel_action(message)
        
    chat_id = message.chat.id
    if chat_id not in user_posts:
        bot.send_message(chat_id, "Session expired. Please start again.", reply_markup=get_main_menu())
        return

    text = user_posts[chat_id]['text']
    btn_name = user_posts[chat_id]['btn_name']
    btn_url = user_posts[chat_id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))

    if message.text == f"📢 Send to {DEFAULT_CHANNEL}":
        try:
            bot.send_message(DEFAULT_CHANNEL, text, reply_markup=inline_markup)
            bot.send_message(chat_id, f"Successfully published to {DEFAULT_CHANNEL}!", reply_markup=get_main_menu())
            del user_posts[chat_id]
        except Exception as e:
            bot.send_message(chat_id, f"Error: Make sure I am an admin in {DEFAULT_CHANNEL}.", reply_markup=get_main_menu())
            
    elif message.text == "💬 Send to Custom Chat":
        msg = bot.send_message(chat_id, "Please send the Username (e.g., @mychannel) or ID of the channel/group.\nMake sure I am an admin there!", reply_markup=get_cancel_menu())
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
    btn_name = user_posts[chat_id]['btn_name']
    btn_url = user_posts[chat_id]['btn_url']
    
    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton(btn_name, url=btn_url))
    
    try:
        bot.send_message(target_chat, text, reply_markup=inline_markup)
        bot.send_message(chat_id, f"Successfully published to {target_chat}!", reply_markup=get_main_menu())
        del user_posts[chat_id]
    except Exception as e:
        bot.send_message(chat_id, "Failed to send. Please verify the channel name and ensure I have admin rights.", reply_markup=get_main_menu())

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=ping_system)
    ping_thread.start()

    bot.infinity_polling()
