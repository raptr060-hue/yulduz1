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

# ================= CONFIG =================
load_dotenv()

class SecurityConfig:
    def __init__(self):
        self.API_TOKEN = os.getenv("BOT_TOKEN")
        self.ADMIN_ID = int(os.getenv("ADMIN_ID", "2010030869"))
        self.BOT_USERNAME = os.getenv("BOT_USERNAME", "stars_sovga_gifbot")
        
        if not self.API_TOKEN:
            raise ValueError("❌ TOKEN topilmadi!")

try:
    config = SecurityConfig()
except ValueError as e:
    print(e)
    exit(1)

# ================= OBUNA TEKSHIRISH =================
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

GROUP_ID = -1002449896845  # Guruh ID

# ================= BOT INIT (THREADED=FALSE) =================
bot = telebot.TeleBot(
    config.API_TOKEN, 
    parse_mode="HTML", 
    threaded=False  # MUHIM: False bo'lishi kerak
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

    def user_exists(self, uid):
        with lock:
            self.cur.execute("SELECT COUNT(*) FROM users WHERE user_id=?", (uid,))
            return self.cur.fetchone()[0] > 0

    def get(self, uid):
        with lock:
            self.cur.execute(
                "SELECT invites, stars, vip FROM users WHERE user_id=?", 
                (uid,)
            )
            row = self.cur.fetchone()
            return (row[0], row[1], row[2]) if row else (0, 0, 0)

    def add_invite(self, uid):
        with lock:
            self.cur.execute(
                "UPDATE users SET invites = invites + 1 WHERE user_id=?", 
                (uid,)
            )
            self.conn.commit()
            # Yulduzlarni qayta hisoblash
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            invites = row[0] if row else 0
            stars = invites // 2
            self.cur.execute("UPDATE users SET stars=? WHERE user_id=?", (stars, uid))
            self.conn.commit()
            return invites, stars

    def add_invite_history(self, inviter_id, invited_id, invited_username, invited_name, group_id):
        with lock:
            self.cur.execute("""
                INSERT INTO invite_history(inviter_id, invited_id, invited_username, invited_name, group_id)
                VALUES(?,?,?,?,?)
            """, (inviter_id, invited_id, invited_username, invited_name, group_id))
            self.conn.commit()

    def check_duplicate(self, inviter_id, invited_id, group_id):
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
            self.cur.execute("UPDATE users SET vip = 1 WHERE user_id=?", (uid,))
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
            return stats

    def get_top(self, limit=10):
        with lock:
            self.cur.execute("""
                SELECT username, first_name, invites, stars
                FROM users WHERE is_banned = 0 
                ORDER BY invites DESC LIMIT ?
            """, (limit,))
            return self.cur.fetchall()

    def get_user_invites(self, uid):
        with lock:
            self.cur.execute("""
                SELECT invited_id, invited_username, invited_name, created_at
                FROM invite_history WHERE inviter_id=?
                ORDER BY created_at DESC LIMIT 20
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
SHOP_ITEMS = {
    15: {"name": "❤️ Heart Gift", "emoji": "❤️", "photo": "https://i.imgur.com/8Yp9Z2M.jpg", "desc": "Yurak sovg'a"},
    25: {"name": "🎁 Gift Box", "emoji": "🎁", "photo": "https://i.imgur.com/3vX9pLm.jpg", "desc": "Sovg'a qutisi"},
    50: {"name": "🎂 Birthday Cake", "emoji": "🎂", "photo": "https://i.imgur.com/9pL2mNx.jpg", "desc": "Tort + VIP"},
    100: {"name": "🏆 Golden Trophy", "emoji": "🏆", "photo": "https://i.imgur.com/vL9pQmN.jpg", "desc": "Kubok + VIP"},
}

# ================= MENU =================
def menu(uid, chat_id):
    invites, stars, vip = db.get(uid)
    
    text = f"""
🌟 <b>REFERRAL SYSTEM</b>

👤 Holatingiz:
👥 Takliflar: <b>{invites}</b> ta
⭐ Yulduzlar: <b>{stars}</b>
👑 VIP: <b>{"✅ HA" if vip else "❌ YO'Q"}</b>

🎯 <i>Guruhga 2 ta odam qo'shing = 1 yulduz</i>
"""
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🛒 Sovg'alar Do'koni", callback_data="shop"))
    m.add(types.InlineKeyboardButton("🏆 Top", callback_data="top"))
    m.add(types.InlineKeyboardButton("📊 Takliflarim", callback_data="history"))
    bot.send_message(chat_id, text, reply_markup=m)

def shop_menu(chat_id, uid):
    _, stars, _ = db.get(uid)
    markup = types.InlineKeyboardMarkup(row_width=2)
    for price, item in sorted(SHOP_ITEMS.items()):
        markup.add(types.InlineKeyboardButton(f"{item['emoji']} {price}⭐", callback_data=f"buy_{price}"))
    text = f"🎁 <b>DO'KON</b>\n⭐ Balans: <b>{stars}</b>"
    bot.send_message(chat_id, text, reply_markup=markup)

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    uid = call.from_user.id
    data = call.data
    
    try:
        if data == "shop":
            shop_menu(call.message.chat.id, uid)
        elif data == "top":
            top = db.get_top(10)
            if top:
                text = "🏆 <b>TOP</b>\n\n"
                for i, (u, n, inv, st) in enumerate(top, 1):
                    user = f"@{u}" if u else n
                    text += f"{i}. <b>{user}</b> — 👥{inv} ⭐{st}\n"
                bot.send_message(call.message.chat.id, text)
            else:
                bot.send_message(call.message.chat.id, "❌ Hali hech kim yo'q!")
        elif data == "history":
            history = db.get_user_invites(uid)
            if history:
                text = "📊 <b>TAKLIFLAR</b>\n\n"
                for i, (iid, un, nm, dt) in enumerate(history, 1):
                    user = f"@{un}" if un else nm
                    text += f"{i}. {user} - {dt}\n"
                bot.send_message(call.message.chat.id, text)
            else:
                bot.send_message(call.message.chat.id, "❌ Hali taklif yo'q!")
        elif data.startswith("buy_"):
            price = int(data.split("_")[1])
            _, stars, _ = db.get(uid)
            if stars >= price:
                db.sub_star(uid, price)
                if price >= 50:
                    db.grant_vip(uid)
                item = SHOP_ITEMS[price]
                _, new_stars, _ = db.get(uid)
                bot.send_photo(call.message.chat.id, item['photo'], 
                    caption=f"🎉 <b>{item['name']}</b>\n💰 Sarflandi: {price}⭐\n⭐ Qoldi: {new_stars}")
            else:
                bot.answer_callback_query(call.id, "❌ Yulduz yetarli emas!", show_alert=True)
        elif data == "check_sub":
            if check_all_subs(uid):
                db.create_user(uid, call.from_user.username, call.from_user.first_name)
                bot.delete_message(call.message.chat.id, call.message.message_id)
                menu(uid, call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "❌ Obuna bo'ling!", show_alert=True)
    except Exception as e:
        logger.error(f"Callback xato: {e}")
    
    bot.answer_callback_query(call.id)

# ================= GURUHGA QO'SHISH =================
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    """Guruhga odam qo'shilganda - BARCHA USULLAR"""
    
    # FAQAT BELGILANGAN GURUHDA ISHLASH
    if message.chat.id != GROUP_ID:
        return
    
    new_members = message.new_chat_members
    inviter_id = message.from_user.id
    
    for new_member in new_members:
        # Botlarni hisoblamaslik
        if new_member.is_bot:
            continue
        
        invited_id = new_member.id
        
        # O'zini qo'shsa hisoblanmaydi
        if inviter_id == invited_id:
            continue
        
        # Takroriy tekshirish
        if db.check_duplicate(inviter_id, invited_id, message.chat.id):
            continue
        
        try:
            # Foydalanuvchilarni yaratish
            db.create_user(inviter_id, message.from_user.username, message.from_user.first_name)
            db.create_user(invited_id, new_member.username, new_member.first_name)
            
            # Tarixga yozish
            db.add_invite_history(inviter_id, invited_id, new_member.username, new_member.first_name, message.chat.id)
            
            # +1 taklif
            invites, stars = db.add_invite(inviter_id)
            
            # Guruhga xabar
            try:
                bot.send_message(
                    message.chat.id,
                    f"🎉 <b>{new_member.first_name}</b> guruhga qo'shildi!\n"
                    f"👥 Taklif qilgan: <b>{message.from_user.first_name}</b>\n"
                    f"⭐ +1 taklif (Jami: {invites} ta, {stars} yulduz)",
                    parse_mode="HTML"
                )
            except:
                pass
            
            # Taklif qiluvchiga xabar
            try:
                bot.send_message(
                    inviter_id,
                    f"🎉 <b>{new_member.first_name}</b> ni guruhga qo'shdingiz!\n"
                    f"👥 Jami takliflar: {invites}\n"
                    f"⭐ Yulduzlar: {stars}"
                )
            except:
                pass
                
        except Exception as e:
            logger.error(f"Taklif hisoblash xatosi: {e}")

# ================= START =================
@bot.message_handler(commands=["start"])
def start(m):
    try:
        uid = m.from_user.id
        
        # Obuna tekshirish
        if not check_all_subs(uid):
            not_subscribed = check_sub(uid)
            markup = types.InlineKeyboardMarkup(row_width=1)
            for ch in not_subscribed:
                markup.add(types.InlineKeyboardButton(f"{ch['name']} - OBUNA", url=ch['url']))
            markup.add(types.InlineKeyboardButton("✅ OBUNA BO'LDIM", callback_data="check_sub"))
            
            channels_list = "\n".join([f"• {ch['name']}: {ch['username']}" for ch in not_subscribed])
            return bot.send_message(m.chat.id, f"❌ Obuna bo'ling:\n\n{channels_list}", reply_markup=markup)
        
        # Foydalanuvchini yaratish
        db.create_user(uid, m.from_user.username, m.from_user.first_name)
        
        # Menu
        menu(uid, m.chat.id)
        
    except Exception as e:
        logger.error(f"Start xatosi: {e}")
        bot.send_message(m.chat.id, "❌ Xatolik! Qayta urinib ko'ring.")

# ================= ADMIN =================
@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    stats = db.get_stats()
    text = f"""
🔐 <b>ADMIN</b>
👥 Users: {stats['total_users']}
👥 Invites: {stats['total_invites']}
⭐ Stars: {stats['total_stars']}
👑 VIP: {stats['vip_users']}
"""
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        db.ban_user(uid)
        bot.reply_to(message, f"✅ {uid} ban!")
    except:
        bot.reply_to(message, "❌ /ban [id]")

@bot.message_handler(commands=['unban'])
def unban_cmd(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        db.unban_user(uid)
        bot.reply_to(message, f"✅ {uid} unban!")
    except:
        bot.reply_to(message, "❌ /unban [id]")

@bot.message_handler(commands=['addstars'])
def addstars_cmd(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        parts = message.text.split()
        uid, amount = int(parts[1]), int(parts[2])
        for _ in range(amount * 2):
            db.add_invite(uid)
        bot.reply_to(message, f"✅ +{amount}⭐")
    except:
        bot.reply_to(message, "❌ /addstars [id] [miqdor]")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    uid = message.from_user.id
    invites, stars, vip = db.get(uid)
    bot.reply_to(message, f"👥 Taklif: {invites}\n⭐ Yulduz: {stars}\n👑 VIP: {'✅' if vip else '❌'}")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.reply_to(message, """
🤖 <b>YORDAM</b>
/start - Boshlash
/stats - Statistika
/help - Yordam
📢 @Stars_2_odam_1stars guruhga odam qo'shing!
""")

# ================= LEADERBOARD =================
def leaderboard():
    while True:
        try:
            top = db.get_top(10)
            if top:
                text = "🏆 <b>TOP TAKLIFCHILAR</b>\n\n"
                for i, (u, n, inv, st) in enumerate(top, 1):
                    user = f"@{u}" if u else n
                    text += f"{i}. <b>{user}</b> — 👥{inv} ⭐{st}\n"
                for ch in REQUIRED_CHANNELS:
                    try:
                        bot.send_message(ch["id"], text)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Leaderboard: {e}")
        time.sleep(300)

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 BOT ISHGA TUSHIRILDI")
    print(f"👥 Guruh ID: {GROUP_ID}")
    print("=" * 50)
    
    # Eski sessiyalarni tozalash
    try:
        requests.get(f"https://api.telegram.org/bot{config.API_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        time.sleep(2)
        requests.get(f"https://api.telegram.org/bot{config.API_TOKEN}/getUpdates?offset=-1", timeout=5)
        print("✅ Tozalandi")
    except:
        pass
    
    # Leaderboard thread
    Thread(target=leaderboard, daemon=True).start()
    
    # Bot polling
    while True:
        try:
            print("♻️ Bot ishlamoqda...")
            bot.infinity_polling(timeout=60, skip_pending=True)
        except KeyboardInterrupt:
            print("👋 To'xtadi")
            break
        except Exception as e:
            error = str(e)
            print(f"❌ Xato: {error[:80]}")
            if "409" in error:
                time.sleep(15)
            else:
                time.sleep(5)
