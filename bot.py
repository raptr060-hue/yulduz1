import telebot
import sqlite3
import logging
import os
import time
import signal
import sys
import requests
from telebot import types
from datetime import datetime
from threading import Lock, Thread
from dotenv import load_dotenv
from functools import wraps

# ================= XAVFSIZLIK KONFIG =================
load_dotenv()

class SecurityConfig:
    def __init__(self):
        self.API_TOKEN = os.getenv("BOT_TOKEN")
        self.ADMIN_ID = int(os.getenv("ADMIN_ID", "2010030869"))
        self.BOT_USERNAME = os.getenv("BOT_USERNAME", "stars_sovga_gifbot")
        self.RATE_LIMIT = 5
        self.ADMINS = [2010030869]
        
        if not self.API_TOKEN:
            raise ValueError("❌ TOKEN topilmadi!")

try:
    config = SecurityConfig()
except ValueError as e:
    print(e)
    exit(1)

# ================= 409 XATO UCHUN TOZALASH =================
def clear_bot_sessions():
    """Eski bot sessiyalarini tozalash"""
    try:
        # Webhook o'chirish
        r = requests.get(f"https://api.telegram.org/bot{config.API_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        print(f"✅ Webhook: {r.json()}")
        time.sleep(2)
        
        # Eski xabarlarni olish (offset=-1 eng oxirgisini oladi)
        r = requests.get(f"https://api.telegram.org/bot{config.API_TOKEN}/getUpdates?offset=-1&timeout=1", timeout=10)
        print(f"✅ Updates tozalandi")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"⚠️ Tozalash: {e}")
        return False

# ================= OBUNA TEKSHIRISH KONFIG =================
REQUIRED_CHANNELS = [
    {
        "id": -1003737363661,
        "username": "@Tekin_stars_yulduz",
        "url": "https://t.me/Tekin_stars_yulduz",
        "name": "📢 KANAL"
    },
    {
        "id": -1002449896845,
        "username": "@Stars_2_odam_1stars",
        "url": "https://t.me/Stars_2_odam_1stars",
        "name": "👥 GURUH"
    }
]

GROUP_ID = -1002449896845

# ================= RATE LIMITING =================
class RateLimiter:
    def __init__(self):
        self.user_requests = {}
        self.lock = Lock()
    
    def is_rate_limited(self, user_id, limit=5, window=5):
        now = time.time()
        with self.lock:
            if user_id not in self.user_requests:
                self.user_requests[user_id] = []
            self.user_requests[user_id] = [
                req for req in self.user_requests[user_id] 
                if now - req < window
            ]
            if len(self.user_requests[user_id]) >= limit:
                return True
            self.user_requests[user_id].append(now)
            return False

rate_limiter = RateLimiter()

# ================= DECORATORLAR =================
def require_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if len(args) > 0:
            message = args[0]
            user_id = message.from_user.id
            if user_id != config.ADMIN_ID and user_id not in config.ADMINS:
                bot.reply_to(message, "❌ Bu buyruq faqat admin uchun!")
                return
        return func(*args, **kwargs)
    return wrapper

def rate_limit_check(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if len(args) > 0 and hasattr(args[0], 'from_user'):
            user_id = args[0].from_user.id
            if rate_limiter.is_rate_limited(user_id):
                bot.reply_to(args[0], "⚠️ Juda ko'p so'rov! Biroz kuting.")
                return
        return func(*args, **kwargs)
    return wrapper

# ================= BOT INIT =================
bot = telebot.TeleBot(
    config.API_TOKEN, 
    parse_mode="HTML", 
    threaded=False  # RENDER UCHUN THREADED=FALSE
)

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("BOT")

# ================= DATABASE =================
lock = Lock()

class DB:
    def __init__(self):
        self.conn = sqlite3.connect("bot.db", check_same_thread=False)
        self.cur = self.conn.cursor()
        self.init()

    def init(self):
        with lock:
            self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                invites INTEGER DEFAULT 0,
                stars INTEGER DEFAULT 0,
                vip INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS invite_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                invited_username TEXT,
                invited_name TEXT,
                group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            self.conn.commit()

    def create_user(self, uid, username, name):
        with lock:
            self.cur.execute(
                "INSERT OR IGNORE INTO users(user_id, username, first_name) VALUES(?,?,?)",
                (uid, username, name)
            )
            self.conn.commit()

    def get(self, uid):
        with lock:
            self.cur.execute(
                "SELECT invites, stars, vip FROM users WHERE user_id=?", 
                (uid,)
            )
            row = self.cur.fetchone()
            return (row[0], row[1], row[2]) if row else (0, 0, 0)

    def add_invite(self, uid, count=1):
        with lock:
            self.cur.execute(
                "UPDATE users SET invites = invites + ? WHERE user_id=?", 
                (count, uid)
            )
            self.conn.commit()
            self.recalc_stars(uid)

    def recalc_stars(self, uid):
        with lock:
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            invites = row[0] if row else 0
            stars = invites // 2
            self.cur.execute(
                "UPDATE users SET stars=? WHERE user_id=?", 
                (stars, uid)
            )
            self.conn.commit()
            return invites, stars

    def add_invite_history(self, inviter_id, invited_id, invited_username, invited_name, group_id):
        with lock:
            self.cur.execute("""
                INSERT INTO invite_history(inviter_id, invited_id, invited_username, invited_name, group_id)
                VALUES(?,?,?,?,?)
            """, (inviter_id, invited_id, invited_username, invited_name, group_id))
            self.conn.commit()

    def check_duplicate_invite(self, inviter_id, invited_id, group_id):
        with lock:
            self.cur.execute("""
                SELECT COUNT(*) FROM invite_history 
                WHERE inviter_id=? AND invited_id=? AND group_id=?
            """, (inviter_id, invited_id, group_id))
            return self.cur.fetchone()[0] > 0

    def sub_star(self, uid, amount):
        with lock:
            self.cur.execute(
                "UPDATE users SET stars = MAX(0, stars - ?) WHERE user_id=?", 
                (amount, uid)
            )
            self.conn.commit()

    def grant_vip(self, uid):
        with lock:
            self.cur.execute(
                "UPDATE users SET vip = 1 WHERE user_id=?", 
                (uid,)
            )
            self.conn.commit()

    def check_ban(self, uid):
        with lock:
            self.cur.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            return row and row[0] == 1

    def ban_user(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET is_banned = 1 WHERE user_id=?", (uid,))
            self.conn.commit()

    def unban_user(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET is_banned = 0 WHERE user_id=?", (uid,))
            self.conn.commit()

    def get_stats(self):
        with lock:
            stats = {}
            self.cur.execute("SELECT COUNT(*) FROM users")
            stats["total_users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(invites) FROM users")
            stats["total_invites"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT SUM(stars) FROM users")
            stats["total_stars"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT COUNT(*) FROM users WHERE vip = 1")
            stats["vip_users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
            stats["banned_users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT COUNT(*) FROM invite_history")
            stats["total_invites_history"] = self.cur.fetchone()[0]
            return stats

    def get_top(self, limit=10):
        with lock:
            self.cur.execute("""
                SELECT username, first_name, invites, stars
                FROM users WHERE is_banned = 0 ORDER BY invites DESC LIMIT ?
            """, (limit,))
            return self.cur.fetchall()

    def search_user(self, query):
        with lock:
            self.cur.execute("""
                SELECT user_id, username, first_name, invites, stars
                FROM users WHERE user_id = ? OR username LIKE ? OR first_name LIKE ?
            """, (query, f"%{query}%", f"%{query}%"))
            return self.cur.fetchall()

    def get_user_invites_detail(self, uid):
        with lock:
            self.cur.execute("""
                SELECT invited_id, invited_username, invited_name, group_id, created_at
                FROM invite_history WHERE inviter_id=? ORDER BY created_at DESC LIMIT 20
            """, (uid,))
            return self.cur.fetchall()

db = DB()

# ================= OBUNA TEKSHIRISH =================
def check_sub(uid):
    not_subscribed = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel["id"], uid)
            if member.status not in ['member', 'administrator', 'creator']:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    return not_subscribed

def check_all_subs(uid):
    return len(check_sub(uid)) == 0

# ================= SHOP =================
SHOP_ITEMS = [
    {"price": 15, "name": "❤️ Heart Gift", "emoji": "❤️", "photo": "https://i.imgur.com/8Yp9Z2M.jpg", "desc": "Chiroyli yurak sovg'asi"},
    {"price": 25, "name": "🎁 Gift Box", "emoji": "🎁", "photo": "https://i.imgur.com/3vX9pLm.jpg", "desc": "Qizil lenta bilan sovg'a"},
    {"price": 50, "name": "🎂 Birthday Cake", "emoji": "🎂", "photo": "https://i.imgur.com/9pL2mNx.jpg", "desc": "Shamli tort + VIP"},
    {"price": 100, "name": "🏆 Golden Trophy", "emoji": "🏆", "photo": "https://i.imgur.com/vL9pQmN.jpg", "desc": "Oltin kubok + VIP"},
]

def get_shop_items():
    seen = {}
    for item in SHOP_ITEMS:
        if item["price"] not in seen:
            seen[item["price"]] = item
    return seen

# ================= MENU =================
def menu(uid, chat_id):
    invites, stars, vip = db.get(uid)
    not_subscribed = check_sub(uid)
    sub_status = ""
    if not_subscribed:
        channels_list = "\n".join([f"• {ch['name']} - {ch['username']}" for ch in not_subscribed])
        sub_status = f"\n\n⚠️ <b>Obuna bo'lmagan:</b>\n{channels_list}"
    
    text = f"""
🌟 <b>REFERRAL SYSTEM</b>

👤 Holatingiz:
👥 Guruhga taklif: <b>{invites}</b> ta
⭐ Yulduzlar: <b>{stars}</b>
👑 VIP: <b>{"✅ HA" if vip else "❌ YO'Q"}</b>{sub_status}

🎯 <i>Har 2 ta odam = 1 yulduz</i>
"""
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🛒 Sovg'alar Do'koni", callback_data="shop"))
    m.add(types.InlineKeyboardButton("🏆 Top", callback_data="top"))
    m.add(types.InlineKeyboardButton("📊 Tarix", callback_data="invite_history"))
    bot.send_message(chat_id, text, reply_markup=m)

def shop_menu(chat_id, uid):
    _, stars, _ = db.get(uid)
    markup = types.InlineKeyboardMarkup(row_width=2)
    shop_data = get_shop_items()
    for price, item in sorted(shop_data.items()):
        markup.add(types.InlineKeyboardButton(f"{item['emoji']} {price}⭐", callback_data=f"buy_{price}"))
    text = f"""
🎁 <b>DO'KON</b>
⭐ Balans: <b>{stars}</b> yulduz
"""
    bot.send_message(chat_id, text, reply_markup=markup)

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    uid = call.from_user.id
    data = call.data
    if data == "shop": shop_menu(call.message.chat.id, uid)
    elif data == "top": send_top(call.message.chat.id)
    elif data == "invite_history": show_invite_history(call.message.chat.id, uid)
    elif data.startswith("buy_"):
        try:
            price = int(data.split("_")[1])
            buy_item(call, uid, price)
        except:
            bot.answer_callback_query(call.id, "❌ Xatolik!", show_alert=True)
    elif data == "check_sub": check_subscription(call)
    bot.answer_callback_query(call.id)

def check_subscription(call):
    uid = call.from_user.id
    if check_all_subs(uid):
        db.create_user(uid, call.from_user.username, call.from_user.first_name)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        bot.answer_callback_query(call.id, "✅ Tasdiqlandi!", show_alert=False)
        menu(uid, call.message.chat.id)
    else:
        not_subscribed = check_sub(uid)
        channels_list = "\n".join([f"• {ch['name']}" for ch in not_subscribed])
        bot.answer_callback_query(call.id, f"❌ Obuna bo'ling!\n{channels_list}", show_alert=True)

def show_invite_history(chat_id, uid):
    history = db.get_user_invites_detail(uid)
    if not history: return bot.send_message(chat_id, "❌ Hali taklif yo'q!")
    text = "📊 <b>TAKLIFLAR</b>\n\n"
    for i, (invited_id, username, name, group_id, date) in enumerate(history, 1):
        user_display = f"@{username}" if username else name
        text += f"{i}. 👤 {user_display} - 📅 {date}\n"
    bot.send_message(chat_id, text)

def buy_item(call, uid, price):
    _, stars, _ = db.get(uid)
    if stars < price: return bot.answer_callback_query(call.id, "❌ Yetarli yulduz yo'q!", show_alert=True)
    shop_data = get_shop_items()
    if price not in shop_data: return bot.answer_callback_query(call.id, "❌ Topilmadi!", show_alert=True)
    item = shop_data[price]
    db.sub_star(uid, price)
    extra = ""
    if price >= 50:
        db.grant_vip(uid)
        extra = "\n\n👑 <b>VIP</b> berildi!"
    _, new_stars, _ = db.get(uid)
    caption = f"🎉 <b>{item['name']}</b>\n💰 Sarflandi: {price}⭐\n⭐ Qoldi: {new_stars}{extra}"
    bot.send_photo(call.message.chat.id, item['photo'], caption=caption)
    bot.answer_callback_query(call.id, "✅ Yetkazildi!", show_alert=True)
    # Admin
    try:
        bot.send_message(config.ADMIN_ID, f"🛍 {call.from_user.first_name} - {item['name']} {price}⭐")
    except: pass

def send_top(chat_id):
    top = db.get_top(10)
    if not top: return bot.send_message(chat_id, "❌ Hali hech kim yo'q!")
    text = "🏆 <b>TOP TAKLIFCHILAR</b>\n\n"
    for i, (username, name, invites, stars) in enumerate(top, 1):
        user = f"@{username}" if username else name
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
        text += f"{medal} <b>{user}</b> — 👥 {invites} | ⭐ {stars}\n"
    bot.send_message(chat_id, text)

# ================= GURUHGA QO'SHISH HANDLER =================
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    """Guruhga odam qo'shilganda - LINK, TUGMA, barcha usullar"""
    
    if message.chat.id != GROUP_ID:
        return
    
    new_members = message.new_chat_members
    
    for new_member in new_members:
        if new_member.is_bot:
            continue
        
        invited_id = new_member.id
        inviter_id = message.from_user.id
        
        if inviter_id == invited_id:
            continue
        
        if db.check_duplicate_invite(inviter_id, invited_id, message.chat.id):
            continue
        
        # Foydalanuvchilarni yaratish
        db.create_user(inviter_id, message.from_user.username, message.from_user.first_name)
        db.create_user(invited_id, new_member.username, new_member.first_name)
        
        # Tarixga yozish
        db.add_invite_history(inviter_id, invited_id, new_member.username, new_member.first_name, message.chat.id)
        
        # +1 taklif
        db.add_invite(inviter_id, 1)
        
        # Xabar
        try:
            bot.send_message(
                message.chat.id,
                f"🎉 <a href='tg://user?id={invited_id}'>{new_member.first_name}</a> guruhga qo'shildi!\n"
                f"👥 Taklif: <a href='tg://user?id={inviter_id}'>{message.from_user.first_name}</a>\n"
                f"⭐ +1 taklif",
                parse_mode="HTML"
            )
        except: pass

# ================= START =================
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    if db.check_ban(uid):
        return bot.send_message(m.chat.id, "❌ Ban!")
    if not check_all_subs(uid):
        not_subscribed = check_sub(uid)
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_subscribed:
            markup.add(types.InlineKeyboardButton(f"{ch['name']} - OBUNA", url=ch['url']))
        markup.add(types.InlineKeyboardButton("✅ OBUNA BO'LDIM", callback_data="check_sub"))
        channels_list = "\n".join([f"• {ch['name']}: {ch['username']}" for ch in not_subscribed])
        return bot.send_message(m.chat.id, f"❌ Obuna bo'ling:\n{channels_list}", reply_markup=markup)
    
    db.create_user(uid, m.from_user.username, m.from_user.first_name)
    menu(uid, m.chat.id)

# ================= ADMIN =================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != config.ADMIN_ID and message.from_user.id not in config.ADMINS:
        return bot.reply_to(message, "❌ Ruxsat yo'q!")
    stats = db.get_stats()
    text = f"""
🔐 <b>ADMIN</b>
👥 Users: {stats['total_users']}
👥 Invites: {stats['total_invites']}
⭐ Stars: {stats['total_stars']}
👑 VIP: {stats['vip_users']}
🚫 Ban: {stats['banned_users']}
"""
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['ban'])
@require_admin
def ban_cmd(message):
    try:
        uid = int(message.text.split()[1])
        db.ban_user(uid)
        bot.reply_to(message, f"✅ {uid} ban!")
    except: bot.reply_to(message, "❌ /ban [id]")

@bot.message_handler(commands=['unban'])
@require_admin
def unban_cmd(message):
    try:
        uid = int(message.text.split()[1])
        db.unban_user(uid)
        bot.reply_to(message, f"✅ {uid} unban!")
    except: bot.reply_to(message, "❌ /unban [id]")

@bot.message_handler(commands=['addstars'])
@require_admin
def addstars_cmd(message):
    try:
        parts = message.text.split()
        uid, amount = int(parts[1]), int(parts[2])
        db.add_invite(uid, amount*2)
        bot.reply_to(message, f"✅ +{amount}⭐")
    except: bot.reply_to(message, "❌ /addstars [id] [miqdor]")

@bot.message_handler(commands=['top'])
def top_cmd(message):
    send_top(message.chat.id)

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    uid = message.from_user.id
    if db.check_ban(uid): return bot.reply_to(message, "❌ Ban!")
    invites, stars, vip = db.get(uid)
    bot.reply_to(message, f"👥 Taklif: {invites}\n⭐ Yulduz: {stars}\n👑 VIP: {'✅' if vip else '❌'}")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.reply_to(message, """
🤖 <b>YORDAM</b>
/start - Boshlash
/stats - Statistika
/top - Top
<b>Guruhga odam qo'shing = +1 taklif!</b>
📢 @Stars_2_odam_1stars
""")

# ================= LEADERBOARD =================
def send_leaderboard():
    try:
        top = db.get_top(10)
        if not top: return
        text = "🏆 <b>TOP</b>\n\n"
        for i, (username, name, invites, stars) in enumerate(top, 1):
            user = f"@{username}" if username else name
            medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
            text += f"{medal} <b>{user}</b> — 👥 {invites} | ⭐ {stars}\n"
        for ch in REQUIRED_CHANNELS:
            try: bot.send_message(ch["id"], text)
            except: pass
    except Exception as e:
        logger.error(f"Leaderboard: {e}")

def leaderboard_scheduler():
    while True:
        send_leaderboard()
        time.sleep(300)

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 TOZALANMOQDA...")
    
    # 409 xatolik uchun tozalash
    clear_bot_sessions()
    
    print(f"👥 Guruh: {GROUP_ID}")
    print(f"🆔 Admin: {config.ADMIN_ID}")
    print("=" * 50)
    
    # Leaderboard thread
    Thread(target=leaderboard_scheduler, daemon=True).start()
    
    # Bot polling - oddiy usul
    while True:
        try:
            print("♻️ Bot ishga tushdi...")
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=90, skip_pending=True)
        except KeyboardInterrupt:
            print("👋 To'xtadi")
            break
        except Exception as e:
            error = str(e)
            if "409" in error:
                print("⚠️ 409 - Tozalash...")
                clear_bot_sessions()
                time.sleep(10)
            else:
                print(f"❌ Xato: {error[:80]}")
                time.sleep(5)
