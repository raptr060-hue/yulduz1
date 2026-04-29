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
DAILY_BONUS = 0.25

# ================= REKLAMA =================
ADS_BOT = "@zurnavolarbot"
ADS_MESSAGES = [
    f"🎵 {ADS_BOT} - Eng zo'r musiqa boti!",
    f"🔥 {ADS_BOT} - Sevimli qo'shiqlaringiz!",
    f"🎶 {ADS_BOT} - Musiqa dunyosi!",
]

MOTIVATIONS = [
    "🔥 Siz zo'rsiz! Davom eting!",
    "💪 Har bir taklif - yulduz sari qadam!",
    "⭐ Yulduzlar sizni kutmoqda!",
    "🚀 Oldinga, lider bo'ling!",
    "👑 Siz eng yaxshisisiz!",
]

GIFT_ADS = [
    {"emoji": "🧸", "name": "Ayiqcha", "desc": "Do'stingizga yoqimli sovg'a!", "photo": "https://i.imgur.com/5f2vL8K.jpg"},
    {"emoji": "🌹", "name": "Atirgul", "desc": "Romantik sovg'a!", "photo": "https://i.imgur.com/7zK9pQm.jpg"},
    {"emoji": "🎁", "name": "Sovg'a qutisi", "desc": "Sirli sovg'a!", "photo": "https://i.imgur.com/3vX9pLm.jpg"},
    {"emoji": "🎂", "name": "Tort", "desc": "Shirin sovg'a!", "photo": "https://i.imgur.com/9pL2mNx.jpg"},
]

# ================= BOT =================
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML", threaded=False)
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
            self.cur.execute("INSERT OR IGNORE INTO users(user_id, username, first_name) VALUES(?,?,?)", (uid, username, name))
            self.conn.commit()

    def get(self, uid):
        with lock:
            self.cur.execute("SELECT invites, stars, vip, total_spent, last_daily, last_ad, daily_streak FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            if row:
                return {"invites": row[0] or 0, "stars": float(row[1] or 0), "vip": row[2] or 0, "spent": float(row[3] or 0), "last_daily": row[4], "last_ad": row[5], "streak": row[6] or 0}
            return {"invites": 0, "stars": 0.0, "vip": 0, "spent": 0.0, "last_daily": None, "last_ad": None, "streak": 0}

    def add_invite(self, uid):
        with lock:
            self.cur.execute("UPDATE users SET invites = invites + 1 WHERE user_id=?", (uid,))
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            invites = row[0] or 0
            stars = invites / 2.0
            self.cur.execute("UPDATE users SET stars=? WHERE user_id=?", (stars, uid))
            self.conn.commit()
            return invites, stars

    def add_history(self, inviter_id, invited_id, invited_name):
        with lock:
            self.cur.execute("INSERT INTO invite_history(inviter_id, invited_id, invited_name) VALUES(?,?,?)", (inviter_id, invited_id, invited_name))
            self.conn.commit()

    def add_purchase_history(self, uid, item_name, price):
        with lock:
            self.cur.execute("INSERT INTO purchase_history(user_id, item_name, price) VALUES(?,?,?)", (uid, item_name, price))
            self.conn.commit()

    def check_duplicate(self, inviter_id, invited_id):
        with lock:
            self.cur.execute("SELECT COUNT(*) FROM invite_history WHERE inviter_id=? AND invited_id=?", (inviter_id, invited_id))
            return self.cur.fetchone()[0] > 0

    def sub_star(self, uid, amount):
        with lock:
            self.cur.execute("SELECT stars FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            current = float(row[0] or 0)
            new_stars = max(0.0, current - amount)
            self.cur.execute("UPDATE users SET stars=?, total_spent=total_spent+? WHERE user_id=?", (new_stars, amount, uid))
            self.conn.commit()
            return new_stars

    def add_stars_admin(self, uid, amount):
        with lock:
            self.cur.execute("SELECT invites FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            ci = row[0] or 0
            ni = ci + int(amount * 2)
            ns = ni / 2.0
            self.cur.execute("UPDATE users SET invites=?, stars=? WHERE user_id=?", (ni, ns, uid))
            self.conn.commit()
            return ns

    def give_daily_bonus(self, uid):
        with lock:
            self.cur.execute("SELECT last_daily, stars, daily_streak FROM users WHERE user_id=?", (uid,))
            row = self.cur.fetchone()
            if row:
                last_daily = row[0]
                cs = float(row[1] or 0)
                streak = row[2] or 0
                now = datetime.now()
                if last_daily:
                    try:
                        last = datetime.fromisoformat(last_daily)
                        if now.date() == last.date():
                            return False, cs, 0, streak
                        if (now.date() - last.date()).days == 1:
                            streak += 1
                        else:
                            streak = 1
                    except:
                        streak = 1
                else:
                    streak = 1
                bonus = DAILY_BONUS
                if streak > 0 and streak % 7 == 0:
                    bonus += 0.5
                ns = cs + bonus
                self.cur.execute("UPDATE users SET stars=?, last_daily=?, daily_streak=? WHERE user_id=?", (ns, now.isoformat(), streak, uid))
                self.conn.commit()
                return True, ns, bonus, streak
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
            self.cur.execute("SELECT username, first_name, invites, stars, vip FROM users WHERE is_banned=0 ORDER BY invites DESC LIMIT ?", (limit,))
            return self.cur.fetchall()

    def get_history(self, uid):
        with lock:
            self.cur.execute("SELECT invited_id, invited_name, created_at FROM invite_history WHERE inviter_id=? ORDER BY created_at DESC LIMIT 20", (uid,))
            return self.cur.fetchall()

    def get_purchase_history(self, uid):
        with lock:
            self.cur.execute("SELECT item_name, price, created_at FROM purchase_history WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (uid,))
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
            self.cur.execute("SELECT user_id, username, first_name, invites, stars, vip FROM users WHERE user_id=? OR username LIKE ? OR first_name LIKE ?", (query, f"%{query}%", f"%{query}%"))
            return self.cur.fetchall()

    def get_stats(self):
        with lock:
            stats = {}
            self.cur.execute("SELECT COUNT(*) FROM users")
            stats["users"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(invites) FROM users")
            stats["invites"] = self.cur.fetchone()[0] or 0
            self.cur.execute("SELECT SUM(stars) FROM users")
            stats["stars"] = float(self.cur.fetchone()[0] or 0)
            self.cur.execute("SELECT COUNT(*) FROM users WHERE vip=1")
            stats["vip"] = self.cur.fetchone()[0]
            self.cur.execute("SELECT SUM(total_spent) FROM users")
            stats["spent"] = float(self.cur.fetchone()[0] or 0)
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
    50: {"name": "🎂 Birthday Cake", "emoji": "🎂", "photo": "https://i.imgur.com/9pL2mNx.jpg", "desc": "Tort + VIP"},
    100: {"name": "🏆 Golden Trophy", "emoji": "🏆", "photo": "https://i.imgur.com/vL9pQmN.jpg", "desc": "Oltin kubok + VIP"},
    200: {"name": "💎 Diamond", "emoji": "💎", "photo": "https://i.imgur.com/kP8mNxZ.jpg", "desc": "Olmos + VIP"},
    500: {"name": "👑 Crown", "emoji": "👑", "photo": "https://i.imgur.com/XkP5vRt.jpg", "desc": "Qirol toji + VIP"},
}

# ================= YORDAMCHI =================
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

def add_footer(text):
    ad = random.choice(ADS_MESSAGES)
    mot = random.choice(MOTIVATIONS)
    return f"{text}\n\n{'─' * 20}\n💡 <i>{mot}</i>\n{ad}"

def format_stars(stars):
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
        return bot.send_message(m.chat.id, "❌ Bloklangansiz!")
    
    if m.text and len(m.text.split()) > 1:
        try:
            ref = int(m.text.split()[1])
            if ref != uid and not db.check_duplicate(ref, uid):
                db.create_user(ref, None, "User")
                db.add_history(ref, uid, m.from_user.first_name)
                inv, st = db.add_invite(ref)
                try:
                    bot.send_message(ref, f"🎉 {m.from_user.first_name} qo'shildi!\n👥 Taklif: {inv}\n⭐ Yulduz: {format_stars(st)}")
                except:
                    pass
        except:
            pass
    
    not_sub = check_sub(uid)
    if not_sub:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_sub:
            markup.add(types.InlineKeyboardButton(f"{ch['name']} - OBUNA", url=ch['url']))
        markup.add(types.InlineKeyboardButton("✅ OBUNA BO'LDIM", callback_data="check_sub"))
        channels = "\n".join([f"• {ch['name']}: {ch['username']}" for ch in not_sub])
        return bot.send_message(m.chat.id, f"❌ Obuna bo'ling:\n\n{channels}", reply_markup=markup)
    
    db.create_user(uid, m.from_user.username, m.from_user.first_name)
    u = db.get(uid)
    vip_status = "✅ HA" if u["vip"] else "❌ YO'Q"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🛒 DO'KON", callback_data="shop"), types.InlineKeyboardButton(f"🎁 +{DAILY_BONUS}⭐ BONUS", callback_data="daily"))
    markup.add(types.InlineKeyboardButton("🏆 TOP", callback_data="top"), types.InlineKeyboardButton("📊 PROFIL", callback_data="profile"))
    markup.add(types.InlineKeyboardButton("🔗 LINK", callback_data="link"), types.InlineKeyboardButton("📜 XARIDLAR", callback_data="purchases"))
    
    text = f"""
🌟 <b>STARS BOT</b> 🌟

👤 <b>{m.from_user.first_name}</b>
👥 Takliflar: <b>{u['invites']}</b> ta
⭐ Yulduzlar: <b>{format_stars(u['stars'])}</b>
👑 VIP: <b>{vip_status}</b>
🔥 Streak: {u['streak']} kun

🎯 <i>2 ta taklif = 1⭐ | Bonus: +{DAILY_BONUS}⭐/kun</i>
"""
    bot.send_message(m.chat.id, add_footer(text), reply_markup=markup)

# ================= GURUH =================
@bot.message_handler(content_types=['new_chat_members'])
def new_members(message):
    if message.chat.id != GROUP_ID:
        return
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        inviter_id = message.from_user.id
        invited_id = member.id
        if inviter_id == invited_id or db.check_duplicate(inviter_id, invited_id):
            continue
        db.create_user(inviter_id, message.from_user.username, message.from_user.first_name)
        db.create_user(invited_id, member.username, member.first_name)
        db.add_history(inviter_id, invited_id, member.first_name)
        inv, st = db.add_invite(inviter_id)
        try:
            bot.send_message(message.chat.id, f"🎉 <b>{member.first_name}</b> qo'shildi!\n👤 {message.from_user.first_name} +1⭐\n📊 Jami: {inv} ta, {format_stars(st)} yulduz")
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
            bot.answer_callback_query(call.id, "❌ Obuna bo'ling!", show_alert=True)
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
        ok, ns, bonus, streak = db.give_daily_bonus(uid)
        if ok:
            extra = ""
            if streak % 7 == 0 and streak > 0:
                extra = "\n🎉 <b>HAFTALIK BONUS!</b> +0.5⭐"
            text = f"🎁 <b>KUNLIK BONUS</b>\n\n✨ +{bonus}⭐ berildi!\n💰 Jami: <b>{format_stars(ns)}</b>\n🔥 Streak: <b>{streak}</b> kun{extra}\n\n🗓 Ertaga yana keling!"
            bot.send_message(call.message.chat.id, add_footer(text))
            bot.answer_callback_query(call.id, f"✅ +{bonus}⭐", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Bugun olgansiz!\nErtaga keling! 🗓", show_alert=True)
        return
    
    if data == "shop":
        u = db.get(uid)
        markup = types.InlineKeyboardMarkup(row_width=2)
        for price, item in SHOP.items():
            can = "✅" if u["stars"] >= price else "🔒"
            markup.add(types.InlineKeyboardButton(f"{can} {item['emoji']} {price}⭐", callback_data=f"buy_{price}"))
        text = f"🛒 <b>DO'KON</b>\n\n⭐ Balans: <b>{format_stars(u['stars'])}</b>\n\n✅ - Mavjud | 🔒 - Yulduz yetmaydi"
        bot.send_message(call.message.chat.id, add_footer(text), reply_markup=markup)
    
    elif data == "top":
        top = db.get_top(10)
        if top:
            text = "🏆 <b>TOP 10</b>\n\n"
            for i, (u, n, inv, st, v) in enumerate(top, 1):
                user = f"@{u}" if u else n
                medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
                vip_mark = " 👑" if v else ""
                text += f"{medal} <b>{user}</b>{vip_mark}\n   👥 {inv} | ⭐ {format_stars(st)}\n\n"
            bot.send_message(call.message.chat.id, add_footer(text))
        else:
            bot.send_message(call.message.chat.id, "❌ Hali top yo'q!")
    
    elif data == "profile":
        u = db.get(uid)
        vip_status = "✅ HA" if u["vip"] else "❌ YO'Q"
        history = db.get_history(uid)[:5]
        
        text = f"""
📊 <b>TO'LIQ PROFIL</b>

👤 {call.from_user.first_name}
🆔 <code>{uid}</code>
👑 VIP: <b>{vip_status}</b>
🔥 Streak: <b>{u['streak']}</b> kun

━━━━━━━━━━━━━━━━━━━━
👥 Takliflar: <b>{u['invites']}</b> ta
⭐ Yulduzlar: <b>{format_stars(u['stars'])}</b>
💰 Sarflangan: {format_stars(u['spent'])}⭐
━━━━━━━━━━━━━━━━━━━━

📜 <b>Oxirgi takliflar:</b>
"""
        if history:
            for iid, name, dt in history:
                text += f"• {name} ({dt[:10]})\n"
        else:
            text += "Hali taklif yo'q\n"
        
        text += f"""
━━━━━━━━━━━━━━━━━━━━
🎯 <b>QANDAY YULDUZ OLISH:</b>
• Guruhga odam qo'shing
• Do'stlaringizni taklif qiling
• Har kuni bonus oling (+{DAILY_BONUS}⭐)
• 7 kun ketma-ket = +0.5⭐
"""
        bot.send_message(call.message.chat.id, add_footer(text))
    
    elif data == "link":
        link = get_invite_link(uid)
        text = f"🔗 <b>TAKLIF LINKI</b>\n\n<code>{link}</code>\n\n📤 Do'stlarga yuboring!\n👥 2 ta do'st = 1⭐\n📢 Guruh: {GROUP_LINK}"
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
        u = db.get(uid)
        
        if u["stars"] < price:
            need = price - u["stars"]
            bot.answer_callback_query(call.id, f"❌ {format_stars(need)}⭐ yetmaydi!\n\nBor: {format_stars(u['stars'])}⭐\nKerak: {price}⭐", show_alert=True)
        else:
            item = SHOP[price]
            ns = db.sub_star(uid, price)
            db.add_purchase_history(uid, item['name'], price)
            extra = ""
            if price >= 50:
                db.grant_vip(uid)
                extra = "\n\n👑 <b>VIP STATUS BERILDI!</b>"
            caption = f"✅ <b>{item['emoji']} {item['name']}</b>\n📝 {item['desc']}\n\n💰 Sarflandi: <b>{price}⭐</b>\n⭐ Qoldi: <b>{format_stars(ns)}</b>{extra}"
            bot.send_photo(call.message.chat.id, item['photo'], caption=add_footer(caption))
            bot.answer_callback_query(call.id, "✅ Xarid qilindi!", show_alert=True)
            try:
                bot.send_message(GROUP_ID, f"🛍 <b>{call.from_user.first_name}</b> {item['emoji']} <b>{item['name']}</b> ({price}⭐)\n🔗 @{BOT_USERNAME}")
            except:
                pass
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
    s = db.get_stats()
    text = f"🔐 <b>ADMIN PANEL</b>\n\n👥 Users: {s['users']}\n👥 Invites: {s['invites']}\n⭐ Stars: {format_stars(s['stars'])}\n👑 VIP: {s['vip']}\n💰 Spent: {format_stars(s['spent'])}⭐\n\n/addstars [id] [miqdor]\n/ban [id] | /unban [id]\n/search [id/username]\n/broadcast [text]"
    bot.send_message(m.chat.id, add_footer(text))

@bot.message_handler(commands=["addstars"])
def addstars_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        parts = m.text.split()
        uid, amount = int(parts[1]), float(parts[2])
        db.create_user(uid, None, "User")
        ns = db.add_stars_admin(uid, amount)
        bot.reply_to(m, f"✅ {uid} ga +{format_stars(amount)}⭐ berildi!\nJami: {format_stars(ns)}⭐")
        try:
            bot.send_message(uid, f"🎉 Admin sizga {format_stars(amount)}⭐ berdi!\nJami: {format_stars(ns)}⭐")
        except:
            pass
    except:
        bot.reply_to(m, "❌ /addstars [id] [miqdor]")

@bot.message_handler(commands=["ban"])
def ban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        db.ban_user(int(m.text.split()[1]))
        bot.reply_to(m, "✅ Ban!")
    except:
        bot.reply_to(m, "❌ /ban [id]")

@bot.message_handler(commands=["unban"])
def unban_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return
    try:
        db.unban_user(int(m.text.split()[1]))
        bot.reply_to(m, "✅ Unban!")
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
            text = "🔍 <b>Qidiruv:</b>\n\n"
            for uid, un, nm, inv, st, vip in results[:10]:
                user = f"@{un}" if un else nm
                text += f"🆔 {uid} | {user} {'👑' if vip else ''}\n👥{inv} ⭐{format_stars(st)}\n\n"
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
    u = db.get(m.from_user.id)
    vip_status = "✅ HA" if u["vip"] else "❌ YO'Q"
    text = f"📊 <b>STATISTIKA</b>\n\n👤 {m.from_user.first_name}\n👥 Taklif: {u['invites']}\n⭐ Yulduz: {format_stars(u['stars'])}\n👑 VIP: {vip_status}\n💰 Sarflangan: {format_stars(u['spent'])}⭐\n🔥 Streak: {u['streak']} kun"
    bot.reply_to(m, add_footer(text))

@bot.message_handler(commands=["daily"])
def daily_cmd(m):
    uid = m.from_user.id
    ok, ns, bonus, streak = db.give_daily_bonus(uid)
    if ok:
        bot.reply_to(m, add_footer(f"🎁 <b>KUNLIK BONUS</b>\n\n+{bonus}⭐!\nJami: {format_stars(ns)}⭐\n🔥 Streak: {streak} kun"))
    else:
        bot.reply_to(m, "❌ Bugun olgansiz! Ertaga keling.")

@bot.message_handler(commands=["link"])
def link_cmd(m):
    link = get_invite_link(m.from_user.id)
    bot.reply_to(m, add_footer(f"🔗 <b>TAKLIF LINKI</b>\n\n<code>{link}</code>\n\n📢 Guruh: {GROUP_LINK}"))

@bot.message_handler(commands=["help"])
def help_cmd(m):
    text = f"""
🤖 <b>{BOT_USERNAME}</b>

📌 <b>Buyruqlar:</b>
/start - Boshlash
/stats - Statistika
/daily - Bonus (+{DAILY_BONUS}⭐)
/link - Taklif linki
/help - Yordam

👥 Yulduz olish:
• Guruhga odam qo'shing
• Do'stlarni taklif qiling
• Har kuni bonus oling
• 7 kun = +0.5⭐ bonus

🛍 Do'kondan sovg'alar oling!

📢 Guruh: {GROUP_LINK}
🎵 Musiqa: {ADS_BOT}
"""
    bot.reply_to(m, text)

# ================= AVTOMATIK =================
def auto_ad_sender():
    while True:
        try:
            users = db.get_all_users_for_ad()
            gift = random.choice(GIFT_ADS)
            for uid in users:
                if db.can_send_ad(uid, 48):
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🛒 Do'kon", callback_data="shop"), types.InlineKeyboardButton("👥 Guruh", url=GROUP_LINK))
                    try:
                        bot.send_photo(uid, gift['photo'], caption=f"🎁 <b>{gift['emoji']} {gift['name']}</b>\n📝 {gift['desc']}\n\n⭐ Do'kondan oling!\n👥 Odam qo'shing!\n\n🔗 @{BOT_USERNAME}", reply_markup=markup)
                        db.update_last_ad(uid)
                    except:
                        pass
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Ad error: {e}")
        time.sleep(172800)

def daily_reminder():
    while True:
        try:
            now = datetime.now()
            if now.hour in [9, 12, 18, 21]:
                users = db.get_all_users_for_ad()
                for uid in users:
                    u = db.get(uid)
                    if u["last_daily"]:
                        try:
                            last = datetime.fromisoformat(u["last_daily"])
                            if last.date() == now.date():
                                continue
                        except:
                            pass
                    try:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton(f"🎁 +{DAILY_BONUS}⭐ BONUS", callback_data="daily"))
                        bot.send_message(uid, f"⏰ <b>BONUS ESKARTMA!</b>\n\n🎁 Kunlik bonus: {DAILY_BONUS}⭐\n🔥 Streak: {u['streak']} kun\n\nHoziroq oling!", reply_markup=markup)
                    except:
                        pass
                    time.sleep(1)
        except:
            pass
        time.sleep(3600)

# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 STARS BOT ISHGA TUSHIRILDI")
    print(f"💰 Kunlik bonus: {DAILY_BONUS}⭐")
    print("=" * 50)
    
    try:
        requests.get(f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        time.sleep(1)
    except:
        pass
    
    Thread(target=auto_ad_sender, daemon=True).start()
    Thread(target=daily_reminder, daemon=True).start()
    
    while True:
        try:
            bot.infinity_polling(timeout=60, skip_pending=True)
        except KeyboardInterrupt:
            print("👋 To'xtadi")
            break
        except Exception as e:
            if "409" in str(e):
                print("⚠️ 409 - qayta urinish...")
                time.sleep(15)
            else:
                print(f"❌ Xato: {str(e)[:80]}")
                time.sleep(5)
