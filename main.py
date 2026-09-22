import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask
import threading
import requests
import time
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "यहाँ_अपना_टोकन_डालें")
APP_LINK = os.environ.get("APP_LINK", "https://आपका-रेंडर-लिंक.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "बॉट सही तरीके से काम कर रहा है!"

def ping_system():
    while True:
        time.sleep(300) 
        try:
            if APP_LINK != "https://आपका-रेंडर-लिंक.onrender.com":
                requests.get(APP_LINK)
        except:
            pass

@bot.message_handler(commands=['start'])
def start_message(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1

    btn1 = InlineKeyboardButton("चैनल से जुड़ें", url="https://t.me/novelxplin")
    btn2 = InlineKeyboardButton("मिनी ऐप खोलें", web_app=WebAppInfo(url="https://novelxplain.odoo.com"))
    
    markup.add(btn1, btn2)

    text = "नमस्ते! मैं आपका नया पोस्ट बॉट हूँ। कृपया नीचे दिए गए बटन का उपयोग करें।"
    bot.send_message(message.chat.id, text, reply_markup=markup)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=ping_system)
    ping_thread.start()

    bot.infinity_polling()
