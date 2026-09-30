import asyncio
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, BusinessMessagesDeletedHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

message_cache = {}
users_data = {}
business_connections = {}
cache_warnings_sent = set()

USERS_FILE = 'assets/users.json'
CONNECTIONS_FILE = 'assets/connections.json'

MAX_CACHE_SIZE = 10000
MAX_TEXT_LENGTH = 4000

DEFAULT_USER_SETTINGS = {
    'track_deletions': True,
    'track_edits': True,
    'track_streaks': True,
    'delete_commands': True,
    'notifications_enabled': True,
    'cache_auto_cleanup': True
}

def load_users():
    global users_data
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
            for user_id_str, user_info in data.items():
                user_id = int(user_id_str)
                users_data[user_id] = {
                    'settings': user_info.get('settings', DEFAULT_USER_SETTINGS.copy()),
                    'streaks': {}
                }
                for chat_id_str, streak_data in user_info.get('streaks', {}).items():
                    users_data[user_id]['streaks'][int(chat_id_str)] = {
                        'count': streak_data['count'],
                        'last_date': date.fromisoformat(streak_data['last_date'])
                    }
    except FileNotFoundError:
        save_users()

def save_users():
    data = {}
    for user_id, user_info in users_data.items():
        streaks_data = {}
        for chat_id, streak_data in user_info['streaks'].items():
            streaks_data[str(chat_id)] = {
                'count': streak_data['count'],
                'last_date': streak_data['last_date'].isoformat()
            }
        data[str(user_id)] = {
            'settings': user_info['settings'],
            'streaks': streaks_data
        }
    with open(USERS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user_data(user_id):
    if user_id not in users_data:
        users_data[user_id] = {
            'settings': DEFAULT_USER_SETTINGS.copy(),
            'streaks': {}
        }
        save_users()
    return users_data[user_id]

def get_user_settings(user_id):
    return get_user_data(user_id)['settings']

def get_user_streaks(user_id):
    return get_user_data(user_id)['streaks']

def load_connections():
    global business_connections
    try:
        with open(CONNECTIONS_FILE, 'r') as f:
            data = json.load(f)
            business_connections = {conn_id: int(user_id) for conn_id, user_id in data.items()}
    except FileNotFoundError:
        save_connections()

def save_connections():
    with open(CONNECTIONS_FILE, 'w') as f:
        json.dump(business_connections, f, indent=2)

def get_owner_by_connection(connection_id):
    owner = business_connections.get(connection_id)
    if owner:
        return owner
    
    if len(users_data) == 1:
        return list(users_data.keys())[0]
    
    return None

def escape_markdown(text):
    if not text:
        return text
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text

def cleanup_cache():
    if len(message_cache) > MAX_CACHE_SIZE:
        items = list(message_cache.items())
        items_to_remove = len(items) - (MAX_CACHE_SIZE // 2)
        for key, _ in items[:items_to_remove]:
            del message_cache[key]
        print(f"Cache cleanup: removed {items_to_remove} old messages")
        cache_warnings_sent.clear()

async def check_cache_and_warn(context: ContextTypes.DEFAULT_TYPE, owner_id: int):
    cache_size = len(message_cache)
    usage_percent = (cache_size / MAX_CACHE_SIZE) * 100
    
    settings = get_user_settings(owner_id)
    auto_cleanup = settings.get('cache_auto_cleanup', True)
    
    warning_levels = {
        50: ("50% cache filled", "Cache is half full. Consider using /clearcache if needed."),
        75: ("75% cache filled", f"Cache usage is high. {'Old messages will be auto-deleted at 100%' if auto_cleanup else 'New messages will not be cached at 100%'}."),
        90: ("90% cache filled - Critical", f"Cache almost full! {'Auto-cleanup will trigger soon' if auto_cleanup else 'Caching will stop soon'}."),
        100: ("Cache full", f"{'Removed ' + str(MAX_CACHE_SIZE // 2) + ' old messages automatically' if auto_cleanup else 'New messages are not being cached. Use /clearcache to resume'}.")
    }
    
    for threshold, (title, message) in warning_levels.items():
        if usage_percent >= threshold and threshold not in cache_warnings_sent:
            cache_warnings_sent.add(threshold)
            
            if settings['notifications_enabled']:
                try:
                    await context.bot.send_message(
                        chat_id=owner_id,
                        text=f"*{title}*\n\n{message}\n\n*Current:* {cache_size:,}/{MAX_CACHE_SIZE:,} ({usage_percent:.1f}%)",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass

milestones = [
    (3000000, datetime(2013, 8, 1)),
    (50000000, datetime(2014, 1, 1)),
    (100000000, datetime(2015, 1, 1)),
    (200000000, datetime(2016, 2, 1)),
    (350000000, datetime(2017, 3, 1)),
    (500000000, datetime(2018, 3, 1)),
    (750000000, datetime(2019, 1, 1)),
    (1000000000, datetime(2020, 1, 1)),
    (1250000000, datetime(2021, 1, 1)),
    (1750000000, datetime(2021, 6, 1)),
    (2100000000, datetime(2022, 1, 1)),
    (5200000000, datetime(2022, 6, 1)),
    (5900000000, datetime(2023, 1, 1)),
    (6400000000, datetime(2023, 10, 1)),
    (6800000000, datetime(2024, 3, 1)),
    (7200000000, datetime(2025, 1, 1)),
    (7500000000, datetime(2026, 1, 1)),
]

def get_registration_date(user_id):
    for i, (milestone_id, milestone_date) in enumerate(milestones):
        if user_id < milestone_id:
            if i == 0:
                return f"before {milestone_date.strftime('%B %Y')}"
            prev_date = milestones[i-1][1]
            days_diff = (milestone_date - prev_date).days
            id_diff = milestone_id - milestones[i-1][0]
            user_offset = user_id - milestones[i-1][0]
            estimated_days = int((user_offset / id_diff) * days_diff)
            estimated_date = prev_date + timedelta(days=estimated_days)
            return estimated_date.strftime('%d.%m.%Y')
    return "after January 2026"

def update_streak(user_id, chat_id):
    today = date.today()
    
    if chat_id in users_data:
        shared_streaks = users_data[chat_id]['streaks']
        user_streaks = users_data[user_id]['streaks']
        
        if user_id in shared_streaks:
            streak_data = shared_streaks[user_id]
        elif chat_id in user_streaks:
            streak_data = user_streaks[chat_id]
            shared_streaks[user_id] = streak_data
            user_streaks[chat_id] = streak_data
        else:
            streak_data = {'count': 1, 'last_date': today}
            shared_streaks[user_id] = streak_data
            user_streaks[chat_id] = streak_data
            save_users()
            return 1
        
        if streak_data['last_date'] == today:
            return streak_data['count']
        
        if streak_data['last_date'] == today - timedelta(days=1):
            streak_data['count'] += 1
            streak_data['last_date'] = today
            save_users()
            return streak_data['count']
        
        streak_data['count'] = 1
        streak_data['last_date'] = today
        save_users()
        return 1
    
    user_streaks = get_user_streaks(user_id)
    
    if chat_id not in user_streaks:
        user_streaks[chat_id] = {'count': 1, 'last_date': today}
        save_users()
        return 1
    
    last_date = user_streaks[chat_id]['last_date']
    
    if last_date == today:
        return user_streaks[chat_id]['count']
    
    if last_date == today - timedelta(days=1):
        user_streaks[chat_id]['count'] += 1
        user_streaks[chat_id]['last_date'] = today
        save_users()
        return user_streaks[chat_id]['count']
    
    user_streaks[chat_id] = {'count': 1, 'last_date': today}
    save_users()
    return 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user_data(user_id)
    
    cache_stats = f"\n\n*Cache:* {len(message_cache)}/{MAX_CACHE_SIZE} messages"
    
    await update.message.reply_text(
        "*Bot started*\n\nConnect me via Telegram Business in settings.\n\n"
        "Available commands:\n"
        "/settings - Configure bot features\n"
        "/info - Get user info (in business chat)\n"
        "/streak - Check streak (in business chat)\n"
        "/flood <text> <count> - Send messages (in business chat)\n"
        "/cache - View cache statistics\n"
        "/clearcache - Clear message cache" + cache_stats,
        parse_mode=ParseMode.MARKDOWN
    )

async def cache_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    cache_size = len(message_cache)
    usage_percent = (cache_size / MAX_CACHE_SIZE) * 100
    
    status = "🟢 Normal" if usage_percent < 70 else "🟡 High" if usage_percent < 90 else "🔴 Critical"
    
    await update.message.reply_text(
        f"*Cache Statistics*\n\n"
        f"*Status:* {status}\n"
        f"*Cached messages:* {cache_size:,}/{MAX_CACHE_SIZE:,}\n"
        f"*Usage:* {usage_percent:.1f}%\n"
        f"*Max text length:* {MAX_TEXT_LENGTH:,} chars\n\n"
        f"Use /clearcache to clear cache",
        parse_mode=ParseMode.MARKDOWN
    )

async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    old_size = len(message_cache)
    message_cache.clear()
    cache_warnings_sent.clear()
    
    await update.message.reply_text(
        f"*Cache cleared*\n\n"
        f"Removed {old_size:,} messages from cache",
        parse_mode=ParseMode.MARKDOWN
    )

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅' if settings['track_deletions'] else '❌'} Track Deletions",
                callback_data='toggle_deletions'
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings['track_edits'] else '❌'} Track Edits",
                callback_data='toggle_edits'
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings['track_streaks'] else '❌'} Track Streaks",
                callback_data='toggle_streaks'
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings['delete_commands'] else '❌'} Delete Commands",
                callback_data='toggle_delete_commands'
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings['notifications_enabled'] else '❌'} Notifications",
                callback_data='toggle_notifications'
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings.get('cache_auto_cleanup', True) else '❌'} Cache Auto-cleanup",
                callback_data='toggle_cache_cleanup'
            )
        ],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cache_mode = "Auto-delete old messages" if settings.get('cache_auto_cleanup', True) else "Stop caching when full"
    
    text = (
        "*Bot Settings*\n\n"
        f"*Track Deletions:* {'Enabled' if settings['track_deletions'] else 'Disabled'}\n"
        f"*Track Edits:* {'Enabled' if settings['track_edits'] else 'Disabled'}\n"
        f"*Track Streaks:* {'Enabled' if settings['track_streaks'] else 'Disabled'}\n"
        f"*Delete Commands:* {'Enabled' if settings['delete_commands'] else 'Disabled'}\n"
        f"*Notifications:* {'Enabled' if settings['notifications_enabled'] else 'Disabled'}\n"
        f"*Cache Mode:* {cache_mode}\n\n"
        "Click buttons to toggle features"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    settings = get_user_settings(user_id)
    
    setting_map = {
        'toggle_deletions': 'track_deletions',
        'toggle_edits': 'track_edits',
        'toggle_streaks': 'track_streaks',
        'toggle_delete_commands': 'delete_commands',
        'toggle_notifications': 'notifications_enabled',
        'toggle_cache_cleanup': 'cache_auto_cleanup'
    }
    
    if query.data in setting_map:
        setting_key = setting_map[query.data]
        settings[setting_key] = not settings[setting_key]
        save_users()
        await settings_menu(update, context)

async def flood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if len(context.args) < 2:
        return
    
    try:
        count = int(context.args[-1])
        message = " ".join(context.args[:-1])
        
        if count > 100:
            return
        
        chat_id = update.effective_chat.id
        business_connection_id = None
        
        if update.business_message:
            business_connection_id = update.business_message.business_connection_id
        
        for _ in range(count):
            if business_connection_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    business_connection_id=business_connection_id
                )
            else:
                await context.bot.send_message(chat_id=chat_id, text=message)
            await asyncio.sleep(0.05)
    except ValueError:
        pass

async def handle_deleted_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.deleted_business_messages:
        business_connection_id = update.deleted_business_messages.business_connection_id
        
        owner_id = get_owner_by_connection(business_connection_id)
        
        if not owner_id:
            return
        
        settings = get_user_settings(owner_id)
        
        if not settings['track_deletions'] or not settings['notifications_enabled']:
            return
        
        for msg_id in update.deleted_business_messages.message_ids:
            chat_id = update.deleted_business_messages.chat.id
            chat_title = update.deleted_business_messages.chat.title or update.deleted_business_messages.chat.first_name or "Unknown"
            
            cached_msg = message_cache.get((chat_id, msg_id))
            if cached_msg:
                username_text = f"@{escape_markdown(cached_msg['username'])}" if cached_msg.get('username') else "no username"
                media_text = f"\n*Media:* {escape_markdown(cached_msg['media'])}" if cached_msg.get('media') else ""
                safe_text = escape_markdown(cached_msg['text']) if cached_msg['text'] else "_(empty)_"
                safe_user = escape_markdown(cached_msg['user'])
                safe_chat = escape_markdown(chat_title)
                
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=f"*Message Deleted*\n\n*Chat:* {safe_chat}\n*Chat ID:* `{chat_id}`\n*From:* {safe_user} ({username_text})\n*Text:* {safe_text}{media_text}",
                    parse_mode=ParseMode.MARKDOWN
                )
                del message_cache[(chat_id, msg_id)]
            else:
                safe_chat = escape_markdown(chat_title)
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=f"*Message Deleted*\n\n*Chat:* {safe_chat}\n*Chat ID:* `{chat_id}`\n*ID:* {msg_id}\n_(text not cached)_",
                    parse_mode=ParseMode.MARKDOWN
                )

async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.edited_business_message:
        message = update.edited_business_message
        business_connection_id = message.business_connection_id
        
        owner_id = get_owner_by_connection(business_connection_id)
        
        if not owner_id and message.chat.type == "private":
            for uid in users_data.keys():
                if uid != message.chat.id:
                    owner_id = uid
                    business_connections[business_connection_id] = owner_id
                    save_connections()
                    break
        
        if not owner_id:
            return
        
        settings = get_user_settings(owner_id)
        
        if settings['track_edits'] and settings['notifications_enabled']:
            chat_title = message.chat.title or message.chat.first_name or "Unknown"
            user_name = message.from_user.first_name or "Unknown"
            username = message.from_user.username
            username_text = f"@{escape_markdown(username)}" if username else "no username"
            
            cached_msg = message_cache.get((message.chat.id, message.message_id))
            old_text = escape_markdown(cached_msg['text']) if cached_msg else "_(not saved)_"
            new_text = escape_markdown(message.text) if message.text else "_(no text)_"
            safe_chat = escape_markdown(chat_title)
            safe_user = escape_markdown(user_name)
            
            media_info = ""
            if message.photo:
                media_info = "\n*Media:* Photo"
            elif message.video:
                media_info = "\n*Media:* Video"
            elif message.document:
                media_info = f"\n*Media:* Document: {escape_markdown(message.document.file_name or 'file')}"
            elif message.animation:
                media_info = "\n*Media:* GIF"
            
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"*Message Edited*\n\n*Chat:* {safe_chat}\n*Chat ID:* `{message.chat.id}`\n*From:* {safe_user} ({username_text})\n*Was:* {old_text}\n*Now:* {new_text}{media_info}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            message_cache[(message.chat.id, message.message_id)] = {
                'text': message.text or '(no text)',
                'user': user_name,
                'username': username,
                'media': media_info
            }
        return
    
    if update.business_connection:
        connection = update.business_connection
        business_connections[connection.id] = connection.user_chat_id
        save_connections()
        
        status = "connected" if connection.is_enabled else "disconnected"
        await context.bot.send_message(
            chat_id=connection.user_chat_id,
            text=f"*Business connection {status}*",
            business_connection_id=connection.id,
            parse_mode=ParseMode.MARKDOWN
        )
    
    if update.business_message:
        message = update.business_message
        business_connection_id = message.business_connection_id
        
        owner_id = get_owner_by_connection(business_connection_id)
        
        if not owner_id and message.chat.type == "private":
            for uid in users_data.keys():
                if uid != message.chat.id:
                    owner_id = uid
                    business_connections[business_connection_id] = owner_id
                    save_connections()
                    break
        
        if not owner_id:
            return
        
        settings = get_user_settings(owner_id)
        
        if message.from_user.id != owner_id and settings['track_streaks']:
            streak_count = update_streak(owner_id, message.chat.id)
        
        text_content = message.text or message.caption or ""
        media_info = ""
        
        if message.photo:
            media_info = "Photo"
        elif message.video:
            media_info = "Video"
        elif message.document:
            media_info = f"Document: {message.document.file_name or 'file'}"
        elif message.voice:
            media_info = "Voice message"
        elif message.video_note:
            media_info = "Video note"
        elif message.audio:
            media_info = f"Audio: {message.audio.title or 'audio'}"
        elif message.sticker:
            media_info = f"Sticker: {message.sticker.emoji or ''}"
        elif message.animation:
            media_info = "GIF"
        
        if text_content or media_info:
            if len(text_content) > MAX_TEXT_LENGTH:
                text_content = text_content[:MAX_TEXT_LENGTH] + "... (truncated)"
            
            cache_size = len(message_cache)
            
            if cache_size >= MAX_CACHE_SIZE and not settings.get('cache_auto_cleanup', True):
                pass
            else:
                message_cache[(message.chat.id, message.message_id)] = {
                    'text': text_content,
                    'user': message.from_user.first_name or "Unknown",
                    'username': message.from_user.username,
                    'media': media_info
                }
                
                await check_cache_and_warn(context, owner_id)
                
                if settings.get('cache_auto_cleanup', True):
                    cleanup_cache()
        
        if message.text and message.text.startswith('/streak'):
            if message.from_user.id != owner_id:
                return
            
            if settings['delete_commands']:
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=message.message_id
                    )
                except:
                    pass
            
            if not settings['track_streaks']:
                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text="*Streak tracking is disabled*\n\nEnable it in /settings",
                    business_connection_id=message.business_connection_id,
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            chat_id = message.chat.id
            user_streaks = get_user_streaks(owner_id)
            
            if message.chat.id in users_data:
                other_user_streaks = users_data[message.chat.id]['streaks']
                streak_data = other_user_streaks.get(owner_id) or user_streaks.get(chat_id)
            else:
                streak_data = user_streaks.get(chat_id)
            
            if streak_data:
                today = date.today()
                if streak_data['last_date'] < today - timedelta(days=1):
                    streak_text = "*Streak reset*"
                    await context.bot.send_message(
                        chat_id=message.chat.id,
                        text=streak_text,
                        business_connection_id=message.business_connection_id,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    streak_text = f"*Streak:* {streak_data['count']} days"
                    with open('assets/fire.gif', 'rb') as gif:
                        await context.bot.send_animation(
                            chat_id=message.chat.id,
                            animation=gif,
                            caption=streak_text,
                            business_connection_id=message.business_connection_id,
                            parse_mode=ParseMode.MARKDOWN
                        )
            else:
                streak_text = "*No streak yet*\n\nStart chatting daily to build a streak!"
                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=streak_text,
                    business_connection_id=message.business_connection_id,
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        if message.text and message.text.startswith('/info'):
            if message.from_user.id != owner_id:
                return
            
            if settings['delete_commands']:
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=message.message_id
                    )
                except:
                    pass
            
            user_id = message.chat.id
            if message.chat.type == "private":
                user_id = message.chat.id
            
            registration_date = get_registration_date(user_id)
            
            await context.bot.send_message(
                chat_id=message.chat.id,
                text=f"*User Info*\n\n*ID:* `{user_id}`\n*Estimated registration:* {registration_date}",
                business_connection_id=message.business_connection_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if message.text and message.text.startswith('/flood'):
            if message.from_user.id != owner_id:
                return
            
            parts = message.text.split()
            if len(parts) < 3:
                return
            
            try:
                count = int(parts[-1])
                text = " ".join(parts[1:-1])
                
                if count > 100:
                    return
                
                if settings['delete_commands']:
                    try:
                        await context.bot.delete_message(
                            chat_id=message.chat.id,
                            message_id=message.message_id
                        )
                    except:
                        pass
                
                for _ in range(count):
                    await context.bot.send_message(
                        chat_id=message.chat.id,
                        text=text,
                        business_connection_id=message.business_connection_id
                    )
                    await asyncio.sleep(0.05)
            except ValueError:
                pass

async def main():
    load_users()
    load_connections()
    
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30.0, read_timeout=30.0)
    application = Application.builder().token(BOT_TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings_menu))
    application.add_handler(CommandHandler("cache", cache_stats))
    application.add_handler(CommandHandler("clearcache", clear_cache))
    application.add_handler(CallbackQueryHandler(handle_settings_callback))
    application.add_handler(CommandHandler("flood", flood))
    application.add_handler(BusinessMessagesDeletedHandler(handle_deleted_messages))
    application.add_handler(MessageHandler(filters.ALL, handle_business_message))
    
    print("Bot started...")
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
