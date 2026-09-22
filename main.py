import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask
import threading
import requests
import time
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "यहाँ_अपना_टोकन_डालें")
APP_LINK = os.environ.get("APP_LINK", "https://post-bot-i3rk.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "रोबोट सही तरीके से काम कर रहा है!"

def ping_system():
    while True:
        time.sleep(300) 
        try:
            if APP_LINK:
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

    text = "नमस्ते! मैं आपका नया संदेश प्रकाशक रोबोट हूँ। अपना संदेश प्रकाशित करने के लिए '/post अपना संदेश' लिखकर भेजें।"
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(commands=['post'])
def send_post(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1

    btn1 = InlineKeyboardButton("चैनल से जुड़ें", url="https://t.me/novelxplin")
    btn2 = InlineKeyboardButton("मिनी ऐप खोलें", web_app=WebAppInfo(url="https://novelxplain.odoo.com"))
    
    markup.add(btn1, btn2)

    text_to_post = message.text.replace('/post', '').strip()
    
    if text_to_post == "":
        bot.reply_to(message, "कृपया आदेश के साथ कुछ संदेश भी लिखें। उदाहरण: /post यह मेरा नया संदेश है")
        return

    try:
        bot.send_message("@novelxplin", text_to_post, reply_markup=markup)
        bot.reply_to(message, "आपका संदेश सफलतापूर्वक प्रसारण मंच पर प्रकाशित कर दिया गया है।")
    except Exception as e:
        bot.reply_to(message, "संदेश भेजने में त्रुटि हुई। कृपया सुनिश्चित करें कि यह रोबोट आपके प्रसारण मंच में व्यवस्थापक है।")

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=ping_system)
    ping_thread.start()

    bot.infinity_polling()
