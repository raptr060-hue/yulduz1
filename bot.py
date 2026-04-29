import telebot
import sqlite3
import logging
import os
import time
import requests
from telebot import types
from datetime import datetime
from threading import Lock, Thread
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "2010030869"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "stars_sovga_gifbot")

if not API_TOKEN:
    print("❌ TOKEN topilmadi!")
    exit(1)

# Kanal va guruh
REQUIRED_CHANNELS = [
    {"id": -1003737363661, "username": "@Tekin_stars_yulduz", "url": "https://t.me/Tekin_stars_yulduz", "name": "📢 KANAL"},
    {"id": -1002449896845, "username": "@Stars_2_odam_1stars", "url": "https://t.me/Stars_2_odam_1stars", "name": "👥 GURUH"}
]
GROUP_ID = -1002449896845  # Sovg'a e'loni shu guruhga yuboriladi

# ================= BOT =================
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML", threaded=False)

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
                is_banned INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS invite_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                invited_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            self.conn.commit()

    def create_user(self, uid, username, name):
        with lock:
            self.cur.execute("INSERT OR IGNORE INTO users(user_id, username, first_name) VALUES(?,?,?)", 
                           (uid, username, name))
            self.conn.commit()

    def get(self, uid):
        with lock:
            self.cur.execute("SELECT invites, stars, vip FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            if row:
                return row[0], row[1], row[2]
            return 0, 0, 0

    def add_invite(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET invites = invites + 1 WHERE user_id=?", (uid,))
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            invites = row[0] if row else 0
            stars = invites // 2
            self.cur.execute("UPDATE users SET stars=? WHERE user_id=?", (stars, uid))
            self.conn.commit()
            return invites, stars

    def add_history(self, inviter_id, invited_id, invited_name):
        with lock:
            self.cur.execute("INSERT INTO invite_history(inviter_id, invited_id, invited_name) VALUES(?,?,?)", 
                           (inviter_id, invited_id, invited_name))
            self.conn.commit()

    def check_duplicate(self, inviter_id, invited_id):
        with lock:
            self.cur.execute("SELECT COUNT(*) FROM invite_history WHERE inviter_id=? AND invited_id=?", 
                           (inviter_id, invited_id))
            return self.cur.fetchone()[0] > 0

    def sub_star(self, uid, amount):
        with lock:
            self.cur.execute("SELECT stars FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            current = row[0] if row else 0
            new_stars = max(0, current - amount)
            self.cur.execute("UPDATE users SET stars=? WHERE user_id=?", (new_stars, uid))
            self.conn.commit()
            return new_stars

    def add_stars_admin(self, uid, amount):
        """Admin tomonidan yulduz qo'shish"""
        with lock:
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            current_invites = row[0] if row else 0
            # Har 1 yulduz = 2 ta taklif
            new_invites = current_invites + (amount * 2)
            new_stars = new_invites // 2
            self.cur.execute("UPDATE users SET invites=?, stars=? WHERE user_id=?", 
                           (new_invites, new_stars, uid))
            self.conn.commit()
            return new_stars

    def grant_vip(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET vip=1 WHERE user_id=?", (uid,))
            self.conn.commit()

    def get_top(self, limit=10):
        with lock:
            self.cur.execute("SELECT username, first_name, invites, stars FROM users WHERE is_banned=0 ORDER BY invites DESC LIMIT ?", 
                           (limit,))
            return self.cur.fetchall()

    def get_history(self, uid):
        with lock:
            self.cur.execute("SELECT invited_id, invited_name, created_at FROM invite_history WHERE inviter_id=? ORDER BY created_at DESC LIMIT 20", 
                           (uid,))
            return self.cur.fetchall()

    def check_ban(self, uid):
        with lock:
            self.cur.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            return row and row[0] == 1

    def ban_user(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
            self.conn.commit()

    def unban_user(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
            self.conn.commit()

    def search_user(self, query):
        with lock:
            self.cur.execute("SELECT user_id, username, first_name, invites, stars FROM users WHERE user_id=? OR username LIKE ? OR first_name LIKE ?",
                           (query, f"%{query}%", f"%{query}%"))
            return self.cur.fetchall()

    def get_stats(self):
        with lock:
            stats = {}
            self.cur.execute("SELECT COUNT(*) FROM users")
            stats["users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(invites) FROM users")
            stats["invites"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT SUM(stars) FROM users")
            stats["stars"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT COUNT(*) FROM users WHERE vip=1")
            stats["vip"] = self.cur.fetchone()[0]
            return stats

db = DB()

# ================= SHOP =================
SHOP = {
    15: {"name": "❤️ Heart Gift", "emoji": "❤️", "photo": "https://i.imgur.com/8Yp9Z2M.jpg", "desc": "Chiroyli yurak sovg'asi"},
    25: {"name": "🎁 Gift Box", "emoji": "🎁", "photo": "https://i.imgur.com/3vX9pLm.jpg", "desc": "Sovg'a qutisi"},
    50: {"name": "🎂 Birthday Cake", "emoji": "🎂", "photo": "https://i.imgur.com/9pL2mNx.jpg", "desc": "Tort + VIP"},
    100: {"name": "🏆 Golden Trophy", "emoji": "🏆", "photo": "https://i.imgur.com/vL9pQmN.jpg", "desc": "Oltin kubok + VIP"},
    200: {"name": "💎 Diamond", "emoji": "💎", "photo": "https://i.imgur.com/kP8mNxZ.jpg", "desc": "Olmos + VIP"},
    500: {"name": "👑 Crown", "emoji": "👑", "photo": "https://i.imgur.com/XkP5vRt.jpg", "desc": "Toj + VIP"},
}

# ================= OBUNA =================
def check_sub(uid):
    not_sub = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(ch["id"], uid)
            if member.status not in ['member', 'administrator', 'creator']:
                not_sub.append(ch)
        except:
            pass
    return not_sub

# ================= START =================
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    
    if db.check_ban(uid):
        return bot.send_message(m.chat.id, "❌ Bloklangansiz!")
    
    not_sub = check_sub(uid)
    if not_sub:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_sub:
            markup.add(types.InlineKeyboardButton(f"{ch['name']} - OBUNA", url=ch['url']))
        markup.add(types.InlineKeyboardButton("✅ OBUNA BO'LDIM", callback_data="check_sub"))
        channels = "\n".join([f"• {ch['name']}: {ch['username']}" for ch in not_sub])
        return bot.send_message(m.chat.id, f"❌ Obuna bo'ling:\n\n{channels}", reply_markup=markup)
    
    db.create_user(uid, m.from_user.username, m.from_user.first_name)
    invites, stars, vip = db.get(uid)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🛒 Sovg'alar Do'koni", callback_data="shop"))
    markup.add(types.InlineKeyboardButton("🏆 Top", callback_data="top"))
    markup.add(types.InlineKeyboardButton("📊 Takliflarim", callback_data="history"))
    
    text = f"""
🌟 <b>REFERRAL SYSTEM</b>

👤 Holatingiz:
👥 Takliflar: <b>{invites}</b> ta
⭐ Yulduzlar: <b>{stars}</b>
👑 VIP: <b>{'✅ HA' if vip else '❌ YO\'Q'}</b>

🎯 <i>Guruhga 2 ta odam qo'shing = 1 yulduz</i>
"""
    bot.send_message(m.chat.id, text, reply_markup=markup)

# ================= GURUHGA QO'SHISH =================
@bot.message_handler(content_types=['new_chat_members'])
def new_members(message):
    if message.chat.id != GROUP_ID:
        return
    
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        
        inviter_id = message.from_user.id
        invited_id = member.id
        
        if inviter_id == invited_id:
            continue
        
        if db.check_duplicate(inviter_id, invited_id):
            continue
        
        db.create_user(inviter_id, message.from_user.username, message.from_user.first_name)
        db.create_user(invited_id, member.username, member.first_name)
        db.add_history(inviter_id, invited_id, member.first_name)
        invites, stars = db.add_invite(inviter_id)
        
        try:
            bot.send_message(
                message.chat.id,
                f"🎉 <b>{member.first_name}</b> guruhga qo'shildi!\n"
                f"👤 Taklif qilgan: {message.from_user.first_name}\n"
                f"⭐ +1 taklif (Jami: {invites} ta, {stars} yulduz)"
            )
        except:
            pass
        
        try:
            bot.send_message(inviter_id, f"✅ {member.first_name} qo'shildi!\n👥 Taklif: {invites}\n⭐ Yulduz: {stars}")
        except:
            pass

# ================= CALLBACK =================
@bot.callback_query_handler(func=lambda c: True)
def callback(call):
    uid = call.from_user.id
    data = call.data
    
    if data == "check_sub":
        not_sub = check_sub(uid)
        if not_sub:
            channels = "\n".join([f"• {ch['name']}" for ch in not_sub])
            bot.answer_callback_query(call.id, f"❌ Obuna bo'ling!\n{channels}", show_alert=True)
        else:
            db.create_user(uid, call.from_user.username, call.from_user.first_name)
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.answer_callback_query(call.id, "✅ Tasdiqlandi!", show_alert=False)
            start(call.message)
        return
    
    if data == "shop":
        invites, stars, vip = db.get(uid)
        markup = types.InlineKeyboardMarkup(row_width=2)
        for price, item in SHOP.items():
            markup.add(types.InlineKeyboardButton(f"{item['emoji']} {price}⭐", callback_data=f"buy_{price}"))
        text = f"🎁 <b>DO'KON</b>\n\n⭐ Balans: <b>{stars}</b>\n👥 Taklif: {invites}\n\nKerakli sovg'ani tanlang:"
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    
    elif data == "top":
        top = db.get_top(10)
        if top:
            text = "🏆 <b>TOP TAKLIFCHILAR</b>\n\n"
            for i, (u, n, inv, st) in enumerate(top, 1):
                user = f"@{u}" if u else n
                medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
                text += f"{medal} <b>{user}</b> — 👥{inv} ⭐{st}\n"
            bot.send_message(call.message.chat.id, text)
        else:
            bot.send_message(call.message.chat.id, "❌ Hali hech kim yo'q!")
    
    elif data == "history":
        history = db.get_history(uid)
        if history:
            text = "📊 <b>TAKLIFLAR TARIXI</b>\n\n"
            for i, (iid, name, dt) in enumerate(history, 1):
                text += f"{i}. {name}\n   📅 {dt}\n\n"
            bot.send_message(call.message.chat.id, text)
        else:
            bot.send_message(call.message.chat.id, "❌ Hali taklif yo'q!")
    
    elif data.startswith("buy_"):
        price = int(data.split("_")[1])
        invites, stars, vip = db.get(uid)
        
        if stars < price:
            bot.answer_callback_query(call.id, f"❌ Yetarli yulduz yo'q!\nSizda: {stars}⭐\nKerak: {price}⭐", show_alert=True)
        else:
            item = SHOP[price]
            new_stars = db.sub_star(uid, price)
            
            extra = ""
            if price >= 50:
                db.grant_vip(uid)
                extra = "\n\n👑 <b>VIP</b> statusi berildi!"
            
            caption = f"""
✅ <b>Sovg'a yetkazildi!</b>

{item['emoji']} <b>{item['name']}</b>
{item['desc']}

💰 Sarflandi: <b>{price}⭐</b>
⭐ Qoldi: <b>{new_stars}</b>{extra}
"""
            bot.send_photo(call.message.chat.id, item['photo'], caption=caption)
            bot.answer_callback_query(call.id, "✅ Yetkazildi!", show_alert=True)
            
            # ========== GURUHGA E'LON ==========
            user = call.from_user
            group_text = f"""
🛍 <b>YANGI SOVG'A!</b>

👤 <b>{user.first_name}</b> sovg'a oldi!
🎁 {item['emoji']} <b>{item['name']}</b>
💰 Narxi: <b>{price}⭐</b>

<i>@{BOT_USERNAME} orqali</i>
"""
            try:
                bot.send_message(GROUP_ID, group_text)
            except:
                pass
            
            # Admin xabari
            try:
                admin_text = f"""
🛍 <b>SOVG'A SOTILDI!</b>

👤 {user.first_name}
🆔 <code>{uid}</code>
📛 @{user.username if user.username else 'yo\'q'}
🎁 {item['name']} ({price}⭐)
⭐ Qoldi: {new_stars}
"""
                bot.send_message(ADMIN_ID, admin_text)
            except:
                pass
    
    bot.answer_callback_query(call.id)

# ================= ADMIN BUYRUQLARI =================
@bot.message_handler(commands=["admin"])
def admin_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Ruxsat yo'q!")
    
    stats = db.get_stats()
    text = f"""
🔐 <b>ADMIN PANEL</b>

📊 <b>Statistika:</b>
👥 Foydalanuvchilar: {stats['users']}
👥 Jami takliflar: {stats['invites']}
⭐ Jami yulduzlar: {stats['stars']}
👑 VIP: {stats['vip']}

⚙️ <b>Buyruqlar:</b>
/addstars [id] [miqdor] - Yulduz berish
/ban [id] - Ban qilish
/unban [id] - Bandan chiqarish
/search [id/username] - Qidirish
/stats - Statistika
"""
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=["addstars"])
def addstars_cmd(m):
    """Admin birovga yulduz berish"""
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Ruxsat yo'q!")
    
    try:
        parts = m.text.split()
        uid = int(parts[1])
        amount = int(parts[2])
        
        # Foydalanuvchini yaratish
        db.create_user(uid, None, "Foydalanuvchi")
        
        # Yulduz qo'shish
        new_stars = db.add_stars_admin(uid, amount)
        
        bot.reply_to(m, f"✅ Foydalanuvchi {uid} ga {amount}⭐ berildi!\nJami yulduzi: {new_stars}")
        
        # Foydalanuvchiga xabar
        try:
            bot.send_message(uid, f"🎉 Admin sizga {amount}⭐ berdi!\nJami: {new_stars}⭐")
        except:
            pass
            
    except Exception as e:
        bot.reply_to(m, f"❌ Format: /addstars [user_id] [miqdor]\nMasalan: /addstars 123456 100\n\nXato: {e}")

@bot.message_handler(commands=["ban"])
def ban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Ruxsat yo'q!")
    try:
        uid = int(m.text.split()[1])
        db.ban_user(uid)
        bot.reply_to(m, f"✅ {uid} ban qilindi!")
    except:
        bot.reply_to(m, "❌ /ban [user_id]")

@bot.message_handler(commands=["unban"])
def unban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Ruxsat yo'q!")
    try:
        uid = int(m.text.split()[1])
        db.unban_user(uid)
        bot.reply_to(m, f"✅ {uid} bandan chiqarildi!")
    except:
        bot.reply_to(m, "❌ /unban [user_id]")

@bot.message_handler(commands=["search"])
def search_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Ruxsat yo'q!")
    try:
        query = m.text.split(maxsplit=1)[1]
        results = db.search_user(query)
        if results:
            text = "🔍 <b>Qidiruv:</b>\n\n"
            for uid, uname, name, inv, st in results[:10]:
                user = f"@{uname}" if uname else name
                text += f"🆔 {uid} | {user}\n👥 {inv} taklif | ⭐ {st} yulduz\n\n"
            bot.reply_to(m, text)
        else:
            bot.reply_to(m, "❌ Topilmadi!")
    except:
        bot.reply_to(m, "❌ /search [id/username]")

@bot.message_handler(commands=["stats"])
def stats_cmd(m):
    uid = m.from_user.id
    invites, stars, vip = db.get(uid)
    bot.reply_to(m, f"📊 <b>Statistika</b>\n\n👥 Taklif: {invites}\n⭐ Yulduz: {stars}\n👑 VIP: {'✅' if vip else '❌'}")

@bot.message_handler(commands=["help"])
def help_cmd(m):
    bot.reply_to(m, f"""
🤖 <b>YORDAM</b>

📌 <b>Buyruqlar:</b>
/start - Boshlash
/stats - Statistika
/help - Yordam

👥 <b>Guruh:</b>
@Stars_2_odam_1stars ga odam qo'shing
Har 2 ta odam = 1⭐ yulduz

🛍 <b>Do'kon:</b>
Yulduzlar bilan sovg'a oling!
""")

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 BOT ISHGA TUSHIRILDI")
    print(f"👥 Guruh: {GROUP_ID}")
    print(f"🆔 Admin: {ADMIN_ID}")
    print("=" * 50)
    
    # Eski sessiyalarni tozalash
    try:
        requests.get(f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        time.sleep(1)
    except:
        pass
    
    while True:
        try:
            print("♻️ Bot ishlamoqda...")
            bot.infinity_polling(timeout=60, skip_pending=True)
        except KeyboardInterrupt:
            print("👋 To'xtadi")
            break
        except Exception as e:
            error = str(e)
            if "409" in error:
                print("⚠️ 409 - qayta urinish...")
                time.sleep(15)
            else:
                print(f"❌ Xato: {error[:80]}")
                time.sleep(5)
