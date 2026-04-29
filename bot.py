import telebot
import sqlite3
import logging
import os
import time
import random
import requests
from telebot import types
from datetime import datetime, timedelta
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

# ================= SOZLAMALAR =================
REQUIRED_CHANNELS = [
    {"id": -1003737363661, "username": "@Tekin_stars_yulduz", "url": "https://t.me/Tekin_stars_yulduz", "name": "📢 KANAL"},
    {"id": -1002449896845, "username": "@Stars_2_odam_1stars", "url": "https://t.me/Stars_2_odam_1stars", "name": "👥 GURUH"}
]
GROUP_ID = -1002449896845
GROUP_LINK = "https://t.me/Stars_2_odam_1stars"
DAILY_BONUS = 0.25  # Har kuni 0.25 yulduz

# ================= REKLAMA =================
ADS_BOT = "@zurnavolarbot"
ADS_MESSAGES = [
    f"🎵 {ADS_BOT} - Eng zo'r musiqa boti!",
    f"🔥 {ADS_BOT} - Sevimli qo'shiqlaringiz!",
    f"🎶 {ADS_BOT} - Musiqa dunyosi!",
    f"💃 {ADS_BOT} - Raqsga tushing!",
    f"🎧 {ADS_BOT} - Hit qo'shiqlar!"
]

# ================= MOTIVATSIYA =================
MOTIVATIONS = [
    "🔥 Siz zo'rsiz! Davom eting!",
    "💪 Har bir taklif - yulduz sari qadam!",
    "⭐ Yulduzlar sizni kutmoqda!",
    "🚀 Oldinga, lider bo'ling!",
    "👑 Siz eng yaxshisisiz!",
    "🎯 Maqsad sari intiling!",
    "💎 Katta sovg'alar kutyapti!",
    "🌟 Yulduzlar soni oshmoqda!",
    "🏆 Chempion bo'ling!",
    "⚡ Kuch sizda!"
]

# Sovg'a reklamalari (48 soatda yuboriladi)
GIFT_ADS = [
    {"emoji": "🧸", "name": "Ayiqcha", "desc": "Do'stingizga yoqimli sovg'a!", "photo": "https://i.imgur.com/5f2vL8K.jpg"},
    {"emoji": "🌹", "name": "Atirgul", "desc": "Romantik sovg'a!", "photo": "https://i.imgur.com/7zK9pQm.jpg"},
    {"emoji": "🎁", "name": "Sovg'a qutisi", "desc": "Sirli sovg'a!", "photo": "https://i.imgur.com/3vX9pLm.jpg"},
    {"emoji": "🎂", "name": "Tort", "desc": "Shirin sovg'a!", "photo": "https://i.imgur.com/9pL2mNx.jpg"},
]

# ================= BOT INIT =================
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
                stars REAL DEFAULT 0,
                vip INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                last_daily TIMESTAMP,
                last_ad TIMESTAMP,
                daily_streak INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS invite_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                invited_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS purchase_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_name TEXT,
                price REAL,
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
                "SELECT invites, stars, vip, total_spent, last_daily, last_ad, daily_streak FROM users WHERE user_id=?", 
                (uid,)
            )
            row = self.cur.fetchone()
            if row:
                return {
                    "invites": row[0] or 0,
                    "stars": float(row[1] if row[1] else 0),
                    "vip": row[2] or 0,
                    "spent": float(row[3] if row[3] else 0),
                    "last_daily": row[4],
                    "last_ad": row[5],
                    "streak": row[6] or 0
                }
            return {"invites": 0, "stars": 0.0, "vip": 0, "spent": 0.0, "last_daily": None, "last_ad": None, "streak": 0}

    def add_invite(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET invites = invites + 1 WHERE user_id=?", (uid,))
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            invites = row[0] if row else 0
            stars = invites / 2.0
            self.cur.execute("UPDATE users SET stars=? WHERE user_id=?", (stars, uid))
            self.conn.commit()
            return invites, stars

    def add_history(self, inviter_id, invited_id, invited_name):
        with lock:
            self.cur.execute(
                "INSERT INTO invite_history(inviter_id, invited_id, invited_name) VALUES(?,?,?)", 
                (inviter_id, invited_id, invited_name)
            )
            self.conn.commit()

    def add_purchase_history(self, uid, item_name, price):
        with lock:
            self.cur.execute(
                "INSERT INTO purchase_history(user_id, item_name, price) VALUES(?,?,?)",
                (uid, item_name, price)
            )
            self.conn.commit()

    def check_duplicate(self, inviter_id, invited_id):
        with lock:
            self.cur.execute(
                "SELECT COUNT(*) FROM invite_history WHERE inviter_id=? AND invited_id=?", 
                (inviter_id, invited_id)
            )
            return self.cur.fetchone()[0] > 0

    def sub_star(self, uid, amount):
        with lock:
            self.cur.execute("SELECT stars FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            current = float(row[0] if row[0] else 0)
            new_stars = max(0.0, current - amount)
            self.cur.execute(
                "UPDATE users SET stars=?, total_spent=total_spent+? WHERE user_id=?", 
                (new_stars, amount, uid)
            )
            self.conn.commit()
            return new_stars

    def add_stars_admin(self, uid, amount):
        with lock:
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            current_invites = row[0] if row else 0
            new_invites = current_invites + int(amount * 2)
            new_stars = new_invites / 2.0
            self.cur.execute(
                "UPDATE users SET invites=?, stars=? WHERE user_id=?", 
                (new_invites, new_stars, uid)
            )
            self.conn.commit()
            return new_stars

    def give_daily_bonus(self, uid):
        with lock:
            self.cur.execute("SELECT last_daily, stars, daily_streak FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            if row:
                last_daily = row[0]
                current_stars = float(row[1] if row[1] else 0)
                streak = row[2] or 0
                now = datetime.now()
                
                if last_daily:
                    try:
                        last = datetime.fromisoformat(last_daily)
                        if now.date() == last.date():
                            return False, current_stars, 0, streak
                        
                        # Ketma-ket kunlarni hisoblash
                        if (now.date() - last.date()).days == 1:
                            streak += 1
                        else:
                            streak = 1
                    except:
                        streak = 1
                else:
                    streak = 1
                
                # Bonus: 0.25 + streak bonus (har 7 kunda qo'shimcha 0.5)
                bonus = DAILY_BONUS
                if streak > 0 and streak % 7 == 0:
                    bonus += 0.5  # Haftalik bonus
                
                new_stars = current_stars + bonus
                self.cur.execute(
                    "UPDATE users SET stars=?, last_daily=?, daily_streak=? WHERE user_id=?", 
                    (new_stars, now.isoformat(), streak, uid)
                )
                self.conn.commit()
                return True, new_stars, bonus, streak
            return False, 0.0, 0, 0

    def can_send_ad(self, uid, hours=48):
        with lock:
            self.cur.execute("SELECT last_ad FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            if row and row[0]:
                try:
                    last = datetime.fromisoformat(row[0])
                    if datetime.now() < last + timedelta(hours=hours):
                        return False
                except:
                    pass
            return True

    def update_last_ad(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET last_ad=? WHERE user_id=?", (datetime.now().isoformat(), uid))
            self.conn.commit()

    def grant_vip(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET vip=1 WHERE user_id=?", (uid,))
            self.conn.commit()

    def get_top(self, limit=10):
        with lock:
            self.cur.execute(
                "SELECT username, first_name, invites, stars, vip FROM users WHERE is_banned=0 ORDER BY invites DESC LIMIT ?", 
                (limit,)
            )
            return self.cur.fetchall()

    def get_history(self, uid):
        with lock:
            self.cur.execute(
                "SELECT invited_id, invited_name, created_at FROM invite_history WHERE inviter_id=? ORDER BY created_at DESC LIMIT 20", 
                (uid,)
            )
            return self.cur.fetchall()

    def get_purchase_history(self, uid):
        with lock:
            self.cur.execute(
                "SELECT item_name, price, created_at FROM purchase_history WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
                (uid,)
            )
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
            self.cur.execute(
                "SELECT user_id, username, first_name, invites, stars, vip FROM users WHERE user_id=? OR username LIKE ? OR first_name LIKE ?",
                (query, f"%{query}%", f"%{query}%")
            )
            return self.cur.fetchall()

    def get_stats(self):
        with lock:
            stats = {}
            self.cur.execute("SELECT COUNT(*) FROM users")
            stats["users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(invites) FROM users")
            stats["invites"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT SUM(stars) FROM users")
            stats["stars"] = float(self.cur.fetchone()[0] if self.cur.fetchone() else 0)
            self.cur.execute("SELECT COUNT(*) FROM users WHERE vip=1")
            stats["vip"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(total_spent) FROM users")
            stats["spent"] = float(self.cur.fetchone()[0] if self.cur.fetchone() else 0)
            return stats

    def get_all_users_for_ad(self):
        with lock:
            self.cur.execute("SELECT user_id FROM users WHERE is_banned=0")
            return [row[0] for row in self.cur.fetchall()]

db = DB()

# ================= SHOP =================
SHOP = {
    15: {"name": "❤️ Heart Gift", "emoji": "❤️", "photo": "https://i.imgur.com/8Yp9Z2M.jpg", "desc": "Chiroyli yurak sovg'asi"},
    25: {"name": "🎁 Gift Box", "emoji": "🎁", "photo": "https://i.imgur.com/3vX9pLm.jpg", "desc": "Sirli sovg'a qutisi"},
    50: {"name": "🎂 Birthday Cake", "emoji": "🎂", "photo": "https://i.imgur.com/9pL2mNx.jpg", "desc": "Tug'ilgan kun torti + VIP"},
    100: {"name": "🏆 Golden Trophy", "emoji": "🏆", "photo": "https://i.imgur.com/vL9pQmN.jpg", "desc": "Oltin kubok + VIP"},
    200: {"name": "💎 Diamond", "emoji": "💎", "photo": "https://i.imgur.com/kP8mNxZ.jpg", "desc": "Olmos + VIP"},
    500: {"name": "👑 Crown", "emoji": "👑", "photo": "https://i.imgur.com/XkP5vRt.jpg", "desc": "Qirol toji + VIP"},
}

# ================= OBUNA TEKSHIRISH =================
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

# ================= YORDAMCHI FUNKSIYALAR =================
def add_footer(text):
    """Har bir xabarga reklama va motivatsiya qo'shish"""
    ad = random.choice(ADS_MESSAGES)
    mot = random.choice(MOTIVATIONS)
    return f"{text}\n\n{'─' * 20}\n💡 <i>{mot}</i>\n{ad}"

def format_stars(stars):
    """Yulduzlarni chiroyli ko'rsatish"""
    if stars == int(stars):
        return str(int(stars))
    return f"{stars:.2f}"

def get_invite_link(uid):
    return f"https://t.me/{BOT_USERNAME}?start={uid}"

# ================= START =================
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    
    if db.check_ban(uid):
        return bot.send_message(m.chat.id, "❌ Siz bloklangansiz!")
    
    # Referrer
    if m.text and len(m.text.split()) > 1:
        try:
            referrer_id = int(m.text.split()[1])
            if referrer_id != uid and not db.check_duplicate(referrer_id, uid):
                db.create_user(referrer_id, None, "Foydalanuvchi")
                db.add_history(referrer_id, uid, m.from_user.first_name)
                inv, st = db.add_invite(referrer_id)
                try:
                    bot.send_message(referrer_id, add_footer(f"🎉 {m.from_user.first_name} linkingiz orqali qo'shildi!\n👥 Taklif: {inv}\n⭐ Yulduz: {format_stars(st)}"))
                except:
                    pass
        except:
            pass
    
    not_sub = check_sub(uid)
    if not_sub:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_sub:
            markup.add(types.InlineKeyboardButton(f"{ch['name']} - OBUNA BO'LISH", url=ch['url']))
        markup.add(types.InlineKeyboardButton("✅ OBUNA BO'LDIM", callback_data="check_sub"))
        channels = "\n".join([f"• {ch['name']}: {ch['username']}" for ch in not_sub])
        return bot.send_message(m.chat.id, f"❌ <b>OBUNA TEKSHIRUVI</b>\n\n{channels}\n\nObuna bo'lib, tugmani bosing!", reply_markup=markup)
    
    db.create_user(uid, m.from_user.username, m.from_user.first_name)
    user = db.get(uid)
    
    vip_status = "✅ HA" if user["vip"] else "❌ YO'Q"
    streak_bonus = "🔥" * min(user["streak"], 10) if user["streak"] > 0 else ""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 DO'KON", callback_data="shop"),
        types.InlineKeyboardButton(f"🎁 BONUS (+{DAILY_BONUS}⭐)", callback_data="daily")
    )
    markup.add(
        types.InlineKeyboardButton("🏆 TOP", callback_data="top"),
        types.InlineKeyboardButton("📊 PROFIL", callback_data="profile")
    )
    markup.add(types.InlineKeyboardButton("🔗 TAKLIF LINKI", callback_data="link"))
    markup.add(types.InlineKeyboardButton("📜 XARIDLAR", callback_data="purchases"))
    
    text = f"""
╔══════════════════════╗
║   🌟 <b>STARS BOT</b> 🌟   ║
╚══════════════════════╝

👤 <b>{m.from_user.first_name}</b>
{'👑 VIP FOYDALANUVCHI' if user['vip'] else ''}

━━━━━━━━━━━━━━━━━━━━
📊 <b>STATISTIKA</b>
━━━━━━━━━━━━━━━━━━━━
👥 Takliflar: <b>{user['invites']}</b> ta
⭐ Yulduzlar: <b>{format_stars(user['stars'])}</b>
👑 VIP: <b>{vip_status}</b>
💰 Sarflangan: {format_stars(user['spent'])}⭐
🔥 Ketma-ket: {user['streak']} kun {streak_bonus}

━━━━━━━━━━━━━━━━━━━━
🎯 <i>2 ta taklif = 1⭐ yulduz</i>
📢 Har kuni +{DAILY_BONUS}⭐ bonus!
🎁 Sovg'alar do'konida xarid qiling!
━━━━━━━━━━━━━━━━━━━━
"""
    text = add_footer(text)
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
        inv, st = db.add_invite(inviter_id)
        
        text = f"""
🎉 <b>YANGI ISHTIROKCHI!</b>

👤 <b>{member.first_name}</b> guruhga qo'shildi!
👥 Taklif qilgan: <b>{message.from_user.first_name}</b>
⭐ +1 taklif (Jami: {inv} ta, {format_stars(st)} yulduz)

💡 <i>{random.choice(MOTIVATIONS)}</i>

🔗 @{BOT_USERNAME}
"""
        try:
            bot.send_message(message.chat.id, text)
        except:
            pass
        
        try:
            bot.send_message(inviter_id, add_footer(f"✅ {member.first_name} qo'shildi!\n👥 Taklif: {inv}\n⭐ Yulduz: {format_stars(st)}"))
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
            bot.answer_callback_query(call.id, "✅ Xush kelibsiz!", show_alert=False)
            start(call.message)
        return
    
    if data == "daily":
        success, new_stars, bonus, streak = db.give_daily_bonus(uid)
        if success:
            extra = ""
            if streak > 0 and streak % 7 == 0:
                extra = "\n\n🎉 <b>HAFTALIK BONUS!</b> +0.5⭐ qo'shimcha!"
            
            text = f"""
🎁 <b>KUNLIK BONUS</b>

✨ Sizga <b>+{bonus}⭐</b> berildi!
💰 Jami yulduz: <b>{format_stars(new_stars)}</b>
🔥 Ketma-ket: <b>{streak}</b> kun{extra}

🗓 Ertaga yana keling!
Har kuni bonus oling!
"""
            text = add_footer(text)
            bot.send_message(call.message.chat.id, text)
            bot.answer_callback_query(call.id, f"✅ +{bonus}⭐", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Bugun bonus olgansiz!\nErtaga keling! 🗓", show_alert=True)
        return
    
    if data == "shop":
        user = db.get(uid)
        markup = types.InlineKeyboardMarkup(row_width=2)
        for price, item in SHOP.items():
            can_buy = "✅" if user["stars"] >= price else "🔒"
            markup.add(types.InlineKeyboardButton(f"{can_buy} {item['emoji']} {price}⭐", callback_data=f"buy_{price}"))
        
        text = f"""
🛒 <b>SOVG'ALAR DO'KONI</b>

⭐ Balans: <b>{format_stars(user['stars'])}</b>
👥 Taklif: {user['invites']} ta

✅ - Siz uchun mavjud
🔒 - Yulduz yetarli emas

Kerakli sovg'ani tanlang:
"""
        text = add_footer(text)
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    
    elif data == "top":
        top = db.get_top(10)
        if top:
            text = "🏆 <b>TOP 10 TAKLIFCHILAR</b>\n\n"
            for i, (u, n, inv, st, v) in enumerate(top, 1):
                user = f"@{u}" if u else n
                medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
                vip_mark = " 👑" if v else ""
                text += f"{medal} <b>{user}</b>{vip_mark}\n   👥 {inv} ta | ⭐ {format_stars(st)}\n\n"
            bot.send_message(call.message.chat.id, add_footer(text))
        else:
            bot.send_message(call.message.chat.id, "❌ Hali top yo'q!")
    
    elif data == "profile":
        user = db.get(uid)
        vip_status = "✅ HA" if user["vip"] else "❌ YO'Q"
        history = db.get_history(uid)
        last_5 = history[:5]
        
        text = f"""
📊 <b>TO'LIQ PROFIL</b>

👤 {call.from_user.first_name}
🆔 <code>{uid}</code>
👑 VIP: <b>{vip_status}</b>
🔥 Streak: {user['streak']} kun

━━━━━━━━━━━━━━━━━━━━
👥 Takliflar: <b>{user['invites']}</b> ta
⭐ Yulduzlar: <b>{format_stars(user['stars'])}</b>
💰 Sarflangan: {format_stars(user['spent'])}⭐
━━━━━━━━━━━━━━━━━━━━

📜 <b>Oxirgi takliflar:</b>
"""
        if last_5:
            for iid, name, dt in last_5:
                text += f"• {name} ({dt[:10]})\n"
        else:
            text += "Hali taklif yo'q\n"
        
        bot.send_message(call.message.chat.id, add_footer(text))
    
    elif data == "link":
        link = get_invite_link(uid)
        text = f"""
🔗 <b>TAKLIF LINKINGIZ</b>

<code>{link}</code>

📤 Do'stlaringizga yuboring!
👥 Har 2 ta do'st = 1⭐
🎁 Sovg'alar do'konida xarid qiling!

📢 Guruh: {GROUP_LINK}
"""
        bot.send_message(call.message.chat.id, add_footer(text))
    
    elif data == "purchases":
        purchases = db.get_purchase_history(uid)
        if purchases:
            text = "📜 <b>XARIDLAR TARIXI</b>\n\n"
            for name, price, dt in purchases:
                text += f"🎁 {name} - {format_stars(price)}⭐ ({dt[:10]})\n"
        else:
            text = "❌ Hali xarid yo'q!\n\n🛒 Do'kondan sovg'a oling!"
        bot.send_message(call.message.chat.id, add_footer(text))
    
    elif data.startswith("buy_"):
        price = int(data.split("_")[1])
        user = db.get(uid)
        
        if user["stars"] < price:
            need = price - user["stars"]
            bot.answer_callback_query(
                call.id,
                f"❌ {format_stars(need)}⭐ yetmaydi!\n\nBor: {format_stars(user['stars'])}⭐\nKerak: {price}⭐",
                show_alert=True
            )
        else:
            item = SHOP[price]
            new_stars = db.sub_star(uid, price)
            db.add_purchase_history(uid, item['name'], price)
            
            extra = ""
            if price >= 50:
                db.grant_vip(uid)
                extra = "\n\n👑 <b>VIP STATUS BERILDI!</b>"
            
            caption = f"""
✅ <b>XARID MUVAFFAQIYATLI!</b>

{item['emoji']} <b>{item['name']}</b>
📝 {item['desc']}

💰 Sarflandi: <b>{price}⭐</b>
⭐ Qoldi: <b>{format_stars(new_stars)}</b>{extra}

🎉 Xaridingiz bilan tabriklaymiz!
"""
            caption = add_footer(caption)
            bot.send_photo(call.message.chat.id, item['photo'], caption=caption)
            bot.answer_callback_query(call.id, "✅ Xarid qilindi!", show_alert=True)
            
            # Guruhga e'lon
            try:
                group_text = f"""
🛍 <b>YANGI XARID!</b>

👤 <b>{call.from_user.first_name}</b>
🎁 {item['emoji']} <b>{item['name']}</b>
💰 {price}⭐

🔗 @{BOT_USERNAME}
"""
                bot.send_message(GROUP_ID, group_text)
            except:
                pass
            
            # Admin
            try:
                bot.send_message(ADMIN_ID, f"🛍 {call.from_user.first_name} - {item['name']} ({price}⭐)")
            except:
                pass
    
    bot.answer_callback_query(call.id)

# ================= ADMIN =================
@bot.message_handler(commands=["admin"])
def admin_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    text = f"""
🔐 <b>ADMIN PANEL</b>

📊 <b>Statistika:</b>
👥 Users: {stats['users']}
👥 Invites: {stats['invites']}
⭐ Stars: {format_stars(stats['stars'])}
👑 VIP: {stats['vip']}
💰 Spent: {format_stars(stats['spent'])}⭐

⚙️ <b>Buyruqlar:</b>
/addstars [id] [miqdor]
/ban [id] | /unban [id]
/search [id/username]
/broadcast [text]
"""
    bot.send_message(m.chat.id, add_footer(text))

@bot.message_handler(commands=["addstars"])
def addstars_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        parts = m.text.split()
        uid = int(parts[1])
        amount = float(parts[2])
        db.create_user(uid, None, "Foydalanuvchi")
        new_stars = db.add_stars_admin(uid, amount)
        bot.reply_to(m, f"✅ {uid} ga +{format_stars(amount)}⭐ berildi!\nJami: {format_stars(new_stars)}⭐")
        try:
            bot.send_message(uid, f"🎉 Admin sizga {format_stars(amount)}⭐ berdi!\nJami: {format_stars(new_stars)}⭐")
        except:
            pass
    except:
        bot.reply_to(m, "❌ /addstars [user_id] [miqdor]")

@bot.message_handler(commands=["ban"])
def ban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(m.text.split()[1])
        db.ban_user(uid)
        bot.reply_to(m, f"✅ {uid} ban!")
    except:
        bot.reply_to(m, "❌ /ban [id]")

@bot.message_handler(commands=["unban"])
def unban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(m.text.split()[1])
        db.unban_user(uid)
        bot.reply_to(m, f"✅ {uid} unban!")
    except:
        bot.reply_to(m, "❌ /unban [id]")

@bot.message_handler(commands=["search"])
def search_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        query = m.text.split(maxsplit=1)[1]
        results = db.search_user(query)
        if results:
            text = "🔍 <b>Qidiruv natijalari:</b>\n\n"
            for uid, un, nm, inv, st, vip in results[:10]:
                user = f"@{un}" if un else nm
                vip_mark = "👑" if vip else ""
                text += f"🆔 {uid} | {user} {vip_mark}\n👥{inv} ⭐{format_stars(st)}\n\n"
            bot.reply_to(m, text)
        else:
            bot.reply_to(m, "❌ Topilmadi!")
    except:
        bot.reply_to(m, "❌ /search [id/username]")

@bot.message_handler(commands=["broadcast"])
def broadcast_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        text = m.text.split(maxsplit=1)[1]
        users = db.get_all_users_for_ad()
        sent = 0
        for uid in users:
            try:
                bot.send_message(uid, add_footer(f"📢 <b>E'LON</b>\n\n{text}"))
                sent += 1
                time.sleep(0.1)
            except:
                pass
        bot.reply_to(m, f"✅ {sent}/{len(users)} ga yuborildi!")
    except:
        bot.reply_to(m, "❌ /broadcast [matn]")

@bot.message_handler(commands=["stats"])
def stats_cmd(m):
    uid = m.from_user.id
    user = db.get(uid)
    vip_status = "✅ HA" if user["vip"] else "❌ YO'Q"
    text = f"""
📊 <b>STATISTIKA</b>

👥 Taklif: {user['invites']}
⭐ Yulduz: {format_stars(user['stars'])}
👑 VIP: {vip_status}
💰 Sarflangan: {format_stars(user['spent'])}⭐
🔥 Streak: {user['streak']} kun
"""
    bot.reply_to(m, add_footer(text))

@bot.message_handler(commands=["daily"])
def daily_cmd(m):
    uid = m.from_user.id
    success, new_stars, bonus, streak = db.give_daily_bonus(uid)
    if success:
        text = f"🎁 <b>KUNLIK BONUS</b>\n\n+{format_stars(bonus)}⭐ berildi!\nJami: {format_stars(new_stars)}⭐\n🔥 Streak: {streak} kun"
        bot.reply_to(m, add_footer(text))
    else:
        bot.reply_to(m, "❌ Bugun olgansiz! Ertaga keling. 🗓")

@bot.message_handler(commands=["link"])
def link_cmd(m):
    uid = m.from_user.id
    link = get_invite_link(uid)
    text = f"""
🔗 <b>TAKLIF LINKI</b>

<code>{link}</code>

👥 Har 2 do'st = 1⭐
📢 Guruh: {GROUP_LINK}
"""
    bot.reply_to(m, add_footer(text))

@bot.message_handler(commands=["help"])
def help_cmd(m):
    text = f"""
🤖 <b>{BOT_USERNAME}</b>

📌 <b>Buyruqlar:</b>
/start - Boshlash
/stats - Statistika
/daily - Kunlik bonus (+{DAILY_BONUS}⭐)
/link - Taklif linki
/help - Yordam

👥 <b>Yulduz olish:</b>
• Guruhga odam qo'shing
• Do'stlaringizni taklif qiling
• Har kuni bonus oling
• 7 kun ketma-ket = +0.5⭐

🛍 Yulduzlar bilan sovg'alar oling!

📢 Guruh: {GROUP_LINK}
🎵 Musiqa: {ADS_BOT}
"""
    bot.reply_to(m, text)

# ================= AVTOMATIK XABARLAR =================
def auto_ad_sender():
    """Har 48 soatda sovg'a reklamasi"""
    while True:
        try:
            users = db.get_all_users_for_ad()
            gift = random.choice(GIFT_ADS)
            
            for uid in users:
                if db.can_send_ad(uid, 48):
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🛒 Do'konga o'tish", callback_data="shop"))
                    markup.add(types.InlineKeyboardButton("👥 Guruhga qo'shilish", url=GROUP_LINK))
                    
                    caption = f"""
🎁 <b>SIZGA MAXSUS SOVG'A!</b>

{gift['emoji']} <b>{gift['name']}</b>
📝 {gift['desc']}

⭐ Do'kondan yulduzlar evaziga oling!
👥 Odam qo'shib yulduz to'plang!
🎁 Har kuni bonus oling!

🔗 @{BOT_USERNAME}
"""
                    try:
                        bot.send_photo(uid, gift['photo'], caption=caption, reply_markup=markup)
                        db.update_last_ad(uid)
                    except:
                        pass
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Ad error: {e}")
        time.sleep(172800)

def daily_reminder():
    """Har kuni bonus eslatmasi"""
    while True:
        try:
            now = datetime.now()
            if now.hour in [9, 12, 18, 21]:  # Kun davomida 4 marta
                users = db.get_all_users_for_ad()
                for uid in users:
                    user = db.get(uid)
                    if user["last_daily"]:
                        last = datetime.fromisoformat(user["last_daily"])
                        if last.date() == now.date():
                            continue  # Bugun olgan
                    
                    try:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton(f"🎁 +{DAILY_BONUS}⭐ BONUS", callback_data="daily"))
                        
                        text = f"""
⏰ <b>BONUS ESKARTMA!</b>

🎁 Kunlik bonusingiz {DAILY_BONUS}⭐
🔥 {user['streak']} kun ketma-ket!

Bonus olish uchun hoziroq bosing!
"""
                        bot.send_message(uid, text, reply_markup=markup)
                    except:
                        pass
                    time.sleep(1)
        except:
            pass
        time.sleep(3600)

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 60)
    print("🌟 STARS BOT v2.0")
    print(f"👥 Guruh: {GROUP_ID}")
    print(f"🆔 Admin: {ADMIN_ID}")
    print(f"🎵 Hamkor: {ADS_BOT}")
    print(f"💰 Kunlik bonus: {DAILY_BONUS}⭐")
    print("=" * 60)
    
    try:
        requests.get(f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        time.sleep(1)
    except:
        pass
    
    Thread(target=auto_ad_sender, daemon=True).start()
    Thread(target=daily_reminder, daemon=True).start()
    
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
