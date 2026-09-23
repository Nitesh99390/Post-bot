"""Telegram Post Studio. Image bytes stay on Telegram, never in Supabase."""
import hashlib
import hmac
import io
import json
import logging
import os
import re
import threading
import time
from functools import wraps
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlsplit

import requests
import telebot
from flask import Flask, Response, g, jsonify, render_template, request
from supabase import create_client
from telebot.types import (
    BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, MenuButtonWebApp, ReplyKeyboardMarkup, WebAppInfo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
APP_LINK = os.environ.get('APP_LINK', 'https://post-bot-i3rk.onrender.com').rstrip('/')
DEFAULT_CHANNEL = os.environ.get('DEFAULT_CHANNEL', '@novelxplin')
OWNER_ID = int(os.environ.get('OWNER_ID', '6069200310'))
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
DEMO_MODE = os.environ.get('DEMO_MODE', '0') == '1'
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
# A valid-looking inert token permits importing/testing without a production token.
bot = telebot.TeleBot(BOT_TOKEN or '0:offline', threaded=False)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
user_posts = {}
session_lock = threading.RLock()
SESSION_TTL = 3600
CREATE, CANCEL, DONE = 'Create post', 'Cancel', 'Preview post'
ADD, EDIT, PUBLISH, CUSTOM = 'Add a button', 'Edit content', 'Publish to channel', 'Choose another chat'


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def display_text(value):
    parser = PlainText()
    parser.feed(str(value or ''))
    # Mini app is a private content library, not a list of destination links.
    return re.sub(r'(?:https?://|tg://|www\.)[^\s<>]+', '[link hidden]', ''.join(parser.parts), flags=re.I)


def unpack_content(value):
    """Versioned metadata in the existing text column; old posts need no migration."""
    try:
        data = json.loads(value)
        if isinstance(data, dict) and data.get('_post_studio') == 1:
            return data
    except (TypeError, ValueError):
        pass
    return {'text': value or '', 'photo_file_id': None}


def serialize_post(row):
    content = unpack_content(row.get('message_text'))
    try:
        names = json.loads(row.get('btn_name') or '[]')
        if not isinstance(names, list):
            names = [str(names)]
    except (TypeError, ValueError):
        names = [row.get('btn_name', '')]
    # Deliberately whitelist fields: no btn_url, file IDs or other users' IDs.
    return {
        'id': str(row['id']), 'text': display_text(content.get('text')),
        'has_photo': bool(content.get('photo_file_id')),
        'button_names': [display_text(name) for name in names if name],
        'created_at': row.get('created_at'),
    }


def validate_init_data(raw):
    if not raw or not BOT_TOKEN:
        raise ValueError('Open your profile from the Telegram bot to continue.')
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    values = dict(pairs)
    if len(values) != len(pairs):
        raise ValueError('Invalid Telegram session.')
    supplied_hash = values.pop('hash', '')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(values.items()))
    secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash):
        raise ValueError('Invalid Telegram session.')
    age = time.time() - int(values.get('auth_date', '0'))
    if age < -30 or age > 86400:
        raise ValueError('Session expired. Please reopen the mini app in Telegram.')
    user = json.loads(values.get('user', '{}'))
    if not isinstance(user, dict) or not isinstance(user.get('id'), int) or user['id'] <= 0:
        raise ValueError('Invalid Telegram user.')
    return user


def authenticated(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            g.user = validate_init_data(request.headers.get('X-Telegram-Init-Data', ''))
        except (ValueError, TypeError, KeyError):
            return jsonify(error='Open the mini app in Telegram, or reopen it if your session expired.'), 401
        return func(*args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error='Your photo is too large. Choose a photo under 9 MB.'), 413


@app.route('/')
@app.route('/stats')
def stats_page():
    if os.path.exists(os.path.join(app.root_path, 'templates', 'studio.html')):
        return render_template('studio.html', demo_mode=DEMO_MODE)
    return 'Post Studio is ready. Open your profile in Telegram.'


@app.get('/health')
def health():
    return jsonify(status='ok')


@app.get('/api/data')
@authenticated
def api_data():
    if not supabase:
        return jsonify(error='Your post library is not connected yet. Please try again later.'), 503
    try:
        page = max(0, min(int(request.args.get('page', 0)), 10000))
    except ValueError:
        return jsonify(error='Invalid page.'), 400
    try:
        uid = g.user['id']
        posts = supabase.table('posts').select('id,message_text,btn_name,created_at', count='exact').eq('user_id', uid).order('created_at', desc=True).range(page * 12, page * 12 + 11).execute()
        leaders = supabase.table('users').select('username,total_posts').order('total_posts', desc=True).limit(10).execute()
        profile = {key: g.user.get(key) for key in ('id', 'first_name', 'last_name', 'username')}
        profile['total_posts'] = posts.count or 0
        return jsonify(profile=profile, posts=[serialize_post(p) for p in posts.data],
                       leaderboard=[{'name': display_text(u.get('username') or 'Creator'), 'total_posts': u.get('total_posts') or 0} for u in leaders.data],
                       has_more=(page + 1) * 12 < (posts.count or 0), page=page)
    except Exception:
        logger.warning('Post library query failed', exc_info=False)
        return jsonify(error='We could not load your library. Please try again.'), 503


def telegram_image(file_id):
    """Proxy Telegram media without exposing the bot token or a download URL."""
    try:
        file = bot.get_file(file_id)
        remote = requests.get(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}', timeout=20, stream=True)
        try:
            remote.raise_for_status()
            buffer = bytearray()
            for chunk in remote.iter_content(65536):
                buffer.extend(chunk)
                if len(buffer) > 10 * 1024 * 1024:
                    return jsonify(error='Photo exceeds the preview limit.'), 413
            # Telegram bot photos/profile avatars are JPEG files.
            return Response(bytes(buffer), mimetype='image/jpeg')
        finally:
            remote.close()
    except Exception:
        logger.warning('Telegram photo unavailable', exc_info=False)
        return jsonify(error='Photo unavailable. Your original is still in Telegram.'), 502


@app.get('/api/posts/<post_id>/photo')
@authenticated
def post_photo(post_id):
    if not supabase:
        return jsonify(error='Library unavailable.'), 503
    try:
        rows = supabase.table('posts').select('message_text').eq('id', post_id).eq('user_id', g.user['id']).limit(1).execute().data
        file_id = unpack_content(rows[0]['message_text']).get('photo_file_id') if rows else None
        if not file_id:
            return jsonify(error='Photo not found.'), 404
        return telegram_image(file_id)
    except Exception:
        return jsonify(error='Photo unavailable.'), 503


@app.get('/api/profile/photo')
@authenticated
def profile_photo():
    try:
        photos = bot.get_user_profile_photos(g.user['id'], limit=1)
        if not photos.photos:
            return '', 204
        return telegram_image(photos.photos[0][-1].file_id)
    except Exception:
        return '', 204


def normalize_url(value):
    value = value.strip()
    if value.startswith('@'):
        if not re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{3,31}', value):
            raise ValueError('Enter a valid Telegram username.')
        value = 'https://t.me/' + value[1:]
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', value):
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http', 'tg') or not parsed.netloc or parsed.username or re.search(r'\s', value) or len(value) > 2048:
        raise ValueError('Use a valid https:// link or @username.')
    return value


def validate_content(text, has_photo):
    limit = 1024 if has_photo else 4096
    if not text.strip() and not has_photo:
        raise ValueError('Write something or add a photo first.')
    if len(text) > limit:
        raise ValueError(f'Keep your {"caption" if has_photo else "post"} under {limit} characters.')


def save_to_supabase(user, draft):
    if not supabase:
        return False
    try:
        # Only a reusable Telegram file reference is persisted. No image/base64/blob.
        content = json.dumps({'_post_studio': 1, 'text': draft['text'], 'photo_file_id': draft.get('photo_file_id')})
        supabase.table('posts').insert({
            'user_id': user.id, 'message_text': content,
            'btn_name': json.dumps([b['name'] for b in draft['buttons']]),
            'btn_url': json.dumps([b['url'] for b in draft['buttons']]),
        }).execute()
    except Exception:
        logger.warning('Post metadata save failed', exc_info=False)
        return False
    try:
        total = supabase.table('posts').select('id', count='exact').eq('user_id', user.id).limit(1).execute().count or 0
        supabase.table('users').upsert({'id': user.id, 'username': user.username or user.first_name, 'total_posts': total}).execute()
    except Exception:
        # A leaderboard failure must not report an already-saved post as unsaved.
        logger.warning('Leaderboard update failed', exc_info=False)
    return True


def keyboard(*labels, profile=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder='One step at a time…')
    for label in labels:
        markup.add(KeyboardButton(label))
    if profile:
        markup.add(KeyboardButton('My profile', web_app=WebAppInfo(url=APP_LINK + '/stats')))
    return markup


def main_menu():
    return keyboard(CREATE, profile=True)


def set_commands(chat_id, active):
    try:
        commands = [BotCommand('cancel', 'Discard current draft')] if active else [BotCommand('start', 'Open Post Studio')]
        bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id))
    except Exception:
        logger.warning('Could not update contextual command menu', exc_info=False)


def current_draft(chat_id):
    draft = user_posts.get(chat_id)
    if draft and time.time() - draft['updated'] > SESSION_TTL:
        user_posts.pop(chat_id, None)
        return None
    return draft


def new_draft(chat_id):
    # Bound abandoned in-memory sessions; production should use one polling worker.
    now = time.time()
    for key, draft in list(user_posts.items()):
        if now - draft['updated'] > SESSION_TTL:
            user_posts.pop(key, None)
    user_posts[chat_id] = {'text': '', 'buttons': [], 'photo_file_id': None, 'stage': 'content', 'updated': now}
    set_commands(chat_id, True)
    return user_posts[chat_id]


def send_post(chat_id, draft):
    markup = InlineKeyboardMarkup()
    for button in draft['buttons']:
        markup.add(InlineKeyboardButton(button['name'], url=button['url']))
    markup = markup if draft['buttons'] else None
    if draft.get('photo_file_id'):
        return bot.send_photo(chat_id, draft['photo_file_id'], caption=draft['text'] or None, parse_mode='HTML', reply_markup=markup)
    return bot.send_message(chat_id, draft['text'], parse_mode='HTML', reply_markup=markup)


def stage_menu(draft):
    stage = draft['stage']
    if stage == 'buttons':
        return keyboard(ADD, DONE, CANCEL) if len(draft['buttons']) < 10 else keyboard(DONE, CANCEL)
    if stage == 'publish':
        return keyboard(PUBLISH, CUSTOM, CANCEL)
    return keyboard(CANCEL)


def ask_content(chat_id):
    bot.send_message(chat_id, '1 / 3 · Your content\n\nSend a message, or send a photo with an optional caption. Simple HTML formatting is supported.\n\nPhoto captions: 1,024 characters · Text: 4,096 characters.', reply_markup=keyboard(CANCEL))


def finish_preview(chat_id, user, draft):
    try:
        send_post(chat_id, draft)
    except Exception:
        bot.send_message(chat_id, 'The preview could not be created. Check your HTML formatting or try a different photo. Your draft is safe.', reply_markup=keyboard(EDIT, CANCEL))
        draft['stage'] = 'preview_error'
        return
    if not draft.get('saved'):
        draft['saved'] = save_to_supabase(user, draft)
    draft['stage'] = 'publish'
    note = 'Saved to your private library.' if draft.get('saved') else 'Library is unavailable; this draft is not saved, but you can still publish it.'
    bot.send_message(chat_id, f'3 / 3 · Ready to publish\n\n{note}\nChoose a destination. Only chats you manage are allowed.', reply_markup=stage_menu(draft))


def can_publish(user_id, target):
    chat = bot.get_chat(target)
    if chat.type == 'private':
        if chat.id != user_id:
            raise ValueError('You can only publish to your own private chat.')
    else:
        member = bot.get_chat_member(chat.id, user_id)
        if member.status not in ('creator', 'administrator'):
            raise ValueError('You must be an administrator of this destination.')
        if chat.type == 'channel' and member.status == 'administrator' and not getattr(member, 'can_post_messages', False):
            raise ValueError('You need permission to post in this channel.')
    return chat.id


def publish(chat_id, user_id, target, draft):
    try:
        target_id = can_publish(user_id, target)
        send_post(target_id, draft)
    except ValueError as error:
        bot.send_message(chat_id, str(error), reply_markup=stage_menu(draft))
        return
    except Exception:
        bot.send_message(chat_id, 'Could not publish. Check the chat name, your admin permissions, and the bot’s posting permissions. Your draft is safe; try again.', reply_markup=stage_menu(draft))
        return
    user_posts.pop(chat_id, None)
    set_commands(chat_id, False)
    bot.send_message(chat_id, 'Published successfully. Your next idea starts here.', reply_markup=main_menu())


@bot.message_handler(commands=['start', 'cancel'])
def commands(message):
    if message.chat.type != 'private':
        bot.send_message(message.chat.id, 'Please open a private chat with me to create posts and see your profile.')
        return
    with session_lock:
        user_posts.pop(message.chat.id, None)
        set_commands(message.chat.id, False)
        try:
            bot.set_chat_menu_button(message.chat.id, MenuButtonWebApp(type='web_app', text='My profile', web_app=WebAppInfo(url=APP_LINK + '/stats')))
        except Exception:
            logger.warning('Could not set profile menu', exc_info=False)
        text = 'Draft closed. Ready for a fresh start?' if message.text.startswith('/cancel') else f'Welcome to Post Studio, {message.from_user.first_name}.\n\nCreate text or photo posts in three simple steps. Your profile and private library are one tap away.'
        bot.send_message(message.chat.id, text, reply_markup=main_menu())


@bot.message_handler(content_types=['text', 'photo', 'document', 'video', 'sticker', 'audio', 'voice'])
def conversation(message):
    if message.chat.type != 'private':
        return
    with session_lock:
        chat_id, text = message.chat.id, message.text or ''
        if text == CANCEL:
            user_posts.pop(chat_id, None)
            set_commands(chat_id, False)
            bot.send_message(chat_id, 'Draft closed. Saved library posts are kept.', reply_markup=main_menu())
            return
        draft = current_draft(chat_id)
        if text == CREATE and not draft:
            new_draft(chat_id)
            ask_content(chat_id)
            return
        if not draft:
            bot.send_message(chat_id, 'Ready when you are. Create a post or open your profile.', reply_markup=main_menu())
            return
        draft['updated'] = time.time()
        stage = draft['stage']
        if stage == 'preview_error' and text == EDIT:
            draft['stage'] = 'content'
            ask_content(chat_id)
        elif stage == 'content':
            photos = getattr(message, 'photo', None)
            if not text and not photos:
                bot.send_message(chat_id, 'Please send text or a photo, not a file or sticker.', reply_markup=keyboard(CANCEL))
                return
            content = text if not photos else message.caption or ''
            try:
                validate_content(content, bool(photos))
            except ValueError as error:
                bot.send_message(chat_id, str(error), reply_markup=keyboard(CANCEL))
                return
            draft.update(text=content, photo_file_id=photos[-1].file_id if photos else None, stage='buttons')
            bot.send_message(chat_id, '2 / 3 · Optional buttons\n\nAdd a call-to-action button, or go straight to the preview. Up to 10 buttons.', reply_markup=stage_menu(draft))
        elif stage == 'buttons' and text == ADD and len(draft['buttons']) < 10:
            draft['stage'] = 'button_name'
            bot.send_message(chat_id, 'What should the button say? Keep it under 64 characters.', reply_markup=keyboard(CANCEL))
        elif stage == 'buttons' and text == DONE:
            finish_preview(chat_id, message.from_user, draft)
        elif stage == 'button_name':
            if not text.strip() or len(text) > 64:
                bot.send_message(chat_id, 'Send a button label between 1 and 64 characters.', reply_markup=keyboard(CANCEL))
                return
            draft.update(current_btn_name=text.strip(), stage='button_url')
            bot.send_message(chat_id, 'Send its destination: an https:// link or @username. It will not appear in your mini app library.', reply_markup=keyboard(CANCEL))
        elif stage == 'button_url':
            try:
                url = normalize_url(text)
            except ValueError as error:
                bot.send_message(chat_id, str(error), reply_markup=keyboard(CANCEL))
                return
            draft['buttons'].append({'name': draft.pop('current_btn_name'), 'url': url})
            draft['stage'] = 'buttons'
            bot.send_message(chat_id, f'{len(draft["buttons"])} button(s) added. Preview when you’re ready.', reply_markup=stage_menu(draft))
        elif stage == 'publish' and text == PUBLISH:
            publish(chat_id, message.from_user.id, DEFAULT_CHANNEL, draft)
        elif stage == 'publish' and text == CUSTOM:
            draft['stage'] = 'target'
            bot.send_message(chat_id, 'Send the @username or numeric ID of a channel/group you manage, or your own chat ID.', reply_markup=keyboard(CANCEL))
        elif stage == 'target':
            if not re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{3,31}|-?\d+', text.strip()):
                bot.send_message(chat_id, 'Please send a valid @username or numeric chat ID.', reply_markup=keyboard(CANCEL))
                return
            target = int(text) if text.lstrip('-').isdigit() else text
            publish(chat_id, message.from_user.id, target, draft)
        else:
            bot.send_message(chat_id, 'Choose an option below to continue this step.', reply_markup=stage_menu(draft))


@app.post('/api/compose')
@authenticated
def compose():
    """Create a real Telegram preview, then let the bot handle destination selection."""
    from types import SimpleNamespace
    if DEMO_MODE:
        return jsonify(error='This is a design preview. Open the live bot to create a real post.'), 403
    text = request.form.get('text', '').strip()
    photo = request.files.get('photo')
    try:
        validate_content(text, bool(photo))
        buttons = json.loads(request.form.get('buttons', '[]'))
        if not isinstance(buttons, list) or len(buttons) > 10:
            raise ValueError('A post can have up to 10 buttons.')
        cleaned = []
        for button in buttons:
            if not isinstance(button, dict) or not isinstance(button.get('name'), str) or not 1 <= len(button['name'].strip()) <= 64:
                raise ValueError('Each button needs a label of 1–64 characters.')
            cleaned.append({'name': button['name'].strip(), 'url': normalize_url(button.get('url', ''))})
        photo_buffer = None
        if photo:
            data = photo.read(9 * 1024 * 1024 + 1)
            if len(data) > 9 * 1024 * 1024:
                raise ValueError('Choose a photo under 9 MB.')
            if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n') or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')):
                raise ValueError('Choose a JPEG, PNG or WebP photo.')
            photo_buffer = io.BytesIO(data)
            photo_buffer.name = 'photo.jpg'
    except (ValueError, TypeError, AttributeError):
        return jsonify(error='Check your content, photo size/type, and button labels/URLs. Text limit: 4,096; photo captions: 1,024.'), 400
    with session_lock:
        uid = g.user['id']
        if current_draft(uid):
            return jsonify(error='You already have a draft in Telegram. Finish or cancel it before creating another.'), 409
        draft = {'text': text, 'buttons': cleaned, 'photo_file_id': photo_buffer, 'stage': 'publish', 'updated': time.time()}
        try:
            sent = send_post(uid, draft)
            draft['photo_file_id'] = sent.photo[-1].file_id if photo_buffer else None
        except Exception:
            return jsonify(error='Could not create your Telegram preview. Start the bot first, check HTML formatting, then try again.'), 502
        user = SimpleNamespace(id=uid, username=g.user.get('username'), first_name=g.user.get('first_name', 'Creator'))
        draft['saved'] = save_to_supabase(user, draft)
        user_posts[uid] = draft
        set_commands(uid, True)
        warning = None if draft['saved'] else 'Library is unavailable. Your preview is in Telegram but was not saved to your library.'
        try:
            bot.send_message(uid, 'Your preview is ready. Choose where to publish it. Only destinations you manage are allowed.' + ('\n' + warning if warning else ''), reply_markup=stage_menu(draft))
        except Exception:
            warning = 'Preview created. Reopen the bot and send any message to see publishing options.'
        return jsonify(ok=True, saved=draft['saved'], warning=warning)


def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False)


if __name__ == '__main__':
    if BOT_TOKEN and not DEMO_MODE:
        threading.Thread(target=run_flask, daemon=True).start()
        bot.infinity_polling(allowed_updates=['message'])
    else:
        logger.info('Starting web preview only; Telegram polling is disabled.')
        run_flask()
