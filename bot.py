import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import sqlite3
import random
from datetime import datetime
import asyncio

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== BOT TOKEN ====================
BOT_TOKEN = "7609017169:AAEyJM0vjOnOyC-BssT42tZ2-Ibbgby0ZBs"
# ==================== BOT TOKEN ====================

# এডমিন ইউজার আইডি
ADMIN_USER_ID = 6769975612

def is_admin(user_id):
    return user_id == ADMIN_USER_ID

# ডাটাবেস সেটআপ
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  first_name TEXT,
                  balance REAL DEFAULT 0, 
                  total_earned REAL DEFAULT 0,
                  referred_by INTEGER DEFAULT NULL,
                  referral_count INTEGER DEFAULT 0,
                  referral_earnings REAL DEFAULT 0,
                  ads_watched_today INTEGER DEFAULT 0,
                  last_ad_watch DATE DEFAULT NULL,
                  joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_id INTEGER,
                  referred_id INTEGER,
                  earned_amount REAL DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  method TEXT,
                  account_number TEXT,
                  transaction_id TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  processed_at TIMESTAMP DEFAULT NULL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # ডিফল্ট সেটিংস
    default_settings = [
        ('min_withdrawal', '100'),
        ('earn_per_ad', '5'),
        ('referral_bonus', '25'),
        ('daily_ad_limit', '20'),
        ('ad_wait_time', '15')
    ]
    
    for key, value in default_settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()
    print("✅ ডাটাবেস তৈরি হয়েছে")

def register_user(user_id, first_name, referred_by=None):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    if c.fetchone() is None:
        c.execute("INSERT INTO users (user_id, first_name, referred_by) VALUES (?, ?, ?)", 
                 (user_id, first_name, referred_by))
        
        if referred_by:
            referral_bonus = float(get_setting('referral_bonus'))
            c.execute('''UPDATE users SET 
                        referral_count = referral_count + 1, 
                        referral_earnings = referral_earnings + ?, 
                        balance = balance + ? 
                        WHERE user_id=?''', 
                     (referral_bonus, referral_bonus, referred_by))
            
            c.execute("INSERT INTO referrals (referrer_id, referred_id, earned_amount) VALUES (?, ?, ?)",
                     (referred_by, user_id, referral_bonus))
    
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def update_setting(key, value):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT balance, total_earned FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (0.0, 0.0)

def get_referral_stats(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT referral_count, referral_earnings FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (0, 0.0)

def get_available_ads_count(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute("SELECT ads_watched_today, last_ad_watch FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    
    if result:
        ads_watched_today, last_ad_watch = result
        today = datetime.now().strftime('%Y-%m-%d')
        
        if last_ad_watch != today:
            ads_watched_today = 0
            c.execute("UPDATE users SET ads_watched_today = 0, last_ad_watch = ? WHERE user_id=?", 
                     (today, user_id))
            conn.commit()
    else:
        ads_watched_today = 0
    
    daily_limit = int(get_setting('daily_ad_limit'))
    available_ads = daily_limit - ads_watched_today
    conn.close()
    return max(0, available_ads)

def watch_ad(user_id):
    earn_per_ad = float(get_setting('earn_per_ad'))
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    c.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, ads_watched_today = ads_watched_today + 1, last_ad_watch = ? WHERE user_id=?", 
              (earn_per_ad, earn_per_ad, today, user_id))
    conn.commit()
    conn.close()
    return earn_per_ad

def create_withdrawal(user_id, amount, method, account_number):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''INSERT INTO withdrawals 
                 (user_id, amount, method, account_number, status) 
                 VALUES (?, ?, ?, ?, 'pending')''',
              (user_id, amount, method, account_number))
    c.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def get_pending_withdrawals():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''SELECT w.id, w.user_id, u.first_name, w.amount, w.method, w.account_number, w.created_at 
                 FROM withdrawals w 
                 JOIN users u ON w.user_id = u.user_id 
                 WHERE w.status = 'pending' 
                 ORDER BY w.created_at DESC''')
    results = c.fetchall()
    conn.close()
    return results

def update_withdrawal_status(withdrawal_id, status, transaction_id=None):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    if transaction_id:
        c.execute("UPDATE withdrawals SET status = ?, processed_at = datetime('now'), transaction_id = ? WHERE id = ?", 
                 (status, transaction_id, withdrawal_id))
    else:
        c.execute("UPDATE withdrawals SET status = ?, processed_at = datetime('now') WHERE id = ?", 
                 (status, withdrawal_id))
    conn.commit()
    conn.close()

def get_user_name(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT first_name FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else "Unknown"

# EffectiveGate CPM ভ্যারিয়েশন লিংক - FIXED
EFFECTIVEGATE_SMARTLINK = "https://www.effectivegatecpm.com/kkhr2s2w47?key=6ccf9216d6f8e266910f8fbd0c3319da"

EFFECTIVEGATE_ADS = [
    {
        "title": "🛒 এক্সক্লুসিভ শপিং অফার",
        "url": f"{EFFECTIVEGATE_SMARTLINK}&subid=shopping",
    },
    {
        "title": "🎮 প্রিমিয়াম গেম ডাউনলোড",
        "url": f"{EFFECTIVEGATE_SMARTLINK}&subid=gaming", 
    },
    {
        "title": "💰 হাই-পেইং মানি অ্যাপ",
        "url": f"{EFFECTIVEGATE_SMARTLINK}&subid=moneyapp",
    },
    {
        "title": "📱 মোবাইল রিচার্জ বোনাস",
        "url": f"{EFFECTIVEGATE_SMARTLINK}&subid=recharge",
    },
    {
        "title": "🎬 ভিডিও স্ট্রিমিং অফার",
        "url": f"{EFFECTIVEGATE_SMARTLINK}&subid=streaming",
    }
]

# কীবোর্ড ফাংশন
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📺 অ্যাড দেখুন"), KeyboardButton("💰 ব্যালেন্স")],
        [KeyboardButton("💸 টাকা তুলুন"), KeyboardButton("👥 রেফারেল")],
        [KeyboardButton("👤 প্রোফাইল"), KeyboardButton("❓ হেল্প")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📺 অ্যাড দেখুন"), KeyboardButton("💰 ব্যালেন্স")],
        [KeyboardButton("💸 টাকা তুলুন"), KeyboardButton("👥 রেফারেল")],
        [KeyboardButton("👤 প্রোফাইল"), KeyboardButton("❓ হেল্প")],
        [KeyboardButton("👑 অ্যাডমিন প্যানেল")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚙️ সেটিংস পরিবর্তন", callback_data="admin_change_settings")],
        [InlineKeyboardButton("📊 ইউজার স্ট্যাটস", callback_data="admin_user_stats")],
        [InlineKeyboardButton("💳 উত্তোলন রিকোয়েস্ট", callback_data="admin_withdrawal_requests")],
        [InlineKeyboardButton("📈 আয় রিপোর্ট", callback_data="admin_earnings_report")],
        [InlineKeyboardButton("🔙 মেনুতে ফিরুন", callback_data="admin_back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard():
    keyboard = [
        [InlineKeyboardButton("💰 প্রতি অ্যাড আয়", callback_data="setting_earn_per_ad")],
        [InlineKeyboardButton("🎯 দৈনিক অ্যাড লিমিট", callback_data="setting_daily_limit")],
        [InlineKeyboardButton("💸 ন্যূনতম উত্তোলন", callback_data="setting_min_withdrawal")],
        [InlineKeyboardButton("👥 রেফারেল বোনাস", callback_data="setting_referral_bonus")],
        [InlineKeyboardButton("⏱️ অ্যাড সময় (সেকেন্ড)", callback_data="setting_ad_wait_time")],
        [InlineKeyboardButton("🔙 অ্যাডমিন প্যানেল", callback_data="admin_back_to_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdrawal_requests_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 পেন্ডিং রিকোয়েস্ট", callback_data="admin_pending_withdrawals")],
        [InlineKeyboardButton("✅ অ্যাপ্রুভড রিকোয়েস্ট", callback_data="admin_approved_withdrawals")],
        [InlineKeyboardButton("❌ রিজেক্টেড রিকোয়েস্ট", callback_data="admin_rejected_withdrawals")],
        [InlineKeyboardButton("🔙 অ্যাডমিন প্যানেল", callback_data="admin_back_to_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdrawal_action_keyboard(withdrawal_id):
    keyboard = [
        [
            InlineKeyboardButton("✅ অ্যাপ্রুভ", callback_data=f"approve_{withdrawal_id}"),
            InlineKeyboardButton("❌ রিজেক্ট", callback_data=f"reject_{withdrawal_id}")
        ],
        [InlineKeyboardButton("🔙 উত্তোলন রিকোয়েস্ট", callback_data="admin_withdrawal_requests")]
    ]
    return InlineKeyboardMarkup(keyboard)

# মেইন মেনু
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    command_text = update.message.text
    
    referred_by = None
    if 'ref' in command_text:
        import re
        match = re.search(r'ref(\d+)', command_text)
        if match:
            referred_by = int(match.group(1))
    
    register_user(user.id, user.first_name, referred_by)
    
    welcome_text = f"""🤖 <b>টেলিগ্রাম ইনকাম বটে স্বাগতম!</b> {user.first_name}

🎯 <b>সরলীকৃত অ্যাড সিস্টেম:</b>
• 📺 অ্যাডে ক্লিক করুন এবং ১৫ সেকেন্ড অপেক্ষা করুন
• ⏱️ স্বয়ংক্রিয়ভাবে টাকা পেয়ে যান
• 💰 কোন অতিরিক্ত ক্লিকের প্রয়োজন নেই

💰 <b>আয় করার রেট:</b>
• প্রতি অ্যাড: ৳{get_setting('earn_per_ad')}
• দৈনিক লিমিট: {get_setting('daily_ad_limit')} অ্যাড

🚀 <b>এখনই শুরু করুন!</b>"""
    
    if is_admin(user.id):
        reply_markup = get_admin_keyboard()
    else:
        reply_markup = get_main_keyboard()
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

# 📺 অ্যাড দেখুন ফাংশন - COMPLETELY FIXED
async def watch_ads_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    
    available_ads = get_available_ads_count(user.id)
    daily_limit = int(get_setting('daily_ad_limit'))
    
    if available_ads <= 0:
        await update.message.reply_text(
            f"📺 <b>অ্যাড দেখুন</b>\n\n"
            f"❌ আপনি আজকের সব অ্যাড দেখে ফেলেছেন!\n"
            f"📊 দৈনিক লিমিট: {daily_limit} অ্যাড\n"
            f"🕒 আগামীকাল আবার আসবেন!",
            parse_mode='HTML'
        )
        return
    
    # EffectiveGate CPM থেকে র্যান্ডম অ্যাড নিন
    ad = random.choice(EFFECTIVEGATE_ADS)
    wait_time = int(get_setting('ad_wait_time'))
    earn_per_ad = float(get_setting('earn_per_ad'))
    
    keyboard = [
        [InlineKeyboardButton("🚀 অ্যাড দেখুন", url=ad["url"])],
        [InlineKeyboardButton("⏱️ ১৫ সেকেন্ড কাউন্টডাউন শুরু করুন", callback_data="start_countdown")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = await update.message.reply_text(
        f"📺 <b>অ্যাড দেখুন ও টাকা আয় করুন</b>\n\n"
        f"🏷️ <b>শিরোনাম:</b> {ad['title']}\n"
        f"💰 <b>আয়:</b> ৳{earn_per_ad:.2f}\n"
        f"⏰ <b>সময়:</b> {wait_time} সেকেন্ড\n\n"
        f"📊 আজকের অগ্রগতি: {daily_limit - available_ads}/{daily_limit}\n"
        f"🎯 বাকি অ্যাড: {available_ads}\n\n"
        f"<b>নির্দেশনা:</b>\n"
        f"1. প্রথমে '🚀 অ্যাড দেখুন' বাটনে ক্লিক করুন\n"
        f"2. অ্যাডটি ওপেন হলে '⏱️ ১৫ সেকেন্ড কাউন্টডাউন শুরু করুন' বাটনে ক্লিক করুন\n"
        f"3. {wait_time} সেকেন্ড অপেক্ষা করুন\n"
        f"4. স্বয়ংক্রিয়ভাবে টাকা পেয়ে যান!",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    # context-এ ডাটা সেভ করুন
    context.user_data['current_ad'] = ad
    context.user_data['ad_message_id'] = message.message_id
    context.user_data['user_id'] = user.id

# কাউন্টডাউন স্টার্ট কলব্যাক - FIXED
async def start_countdown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    # ইউজারের জন্য উপলব্ধ অ্যাড চেক করুন
    user_id = context.user_data.get('user_id', user.id)
    available_ads = get_available_ads_count(user_id)
    if available_ads <= 0:
        await query.edit_message_text("❌ আপনি আজকের সব অ্যাড দেখে ফেলেছেন! আগামীকাল আবার আসবেন।")
        return
    
    ad = context.user_data.get('current_ad')
    if not ad:
        await query.edit_message_text("❌ অ্যাড ডাটা পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return
    
    wait_time = int(get_setting('ad_wait_time'))
    earn_per_ad = float(get_setting('earn_per_ad'))
    
    # কাউন্টডাউন শুরু করুন
    remaining_time = wait_time
    
    # প্রথমে মেসেজ আপডেট করুন
    countdown_text = (
        f"⏳ <b>অ্যাড কাউন্টডাউন শুরু হয়েছে!</b>\n\n"
        f"🏷️ <b>অ্যাড:</b> {ad['title']}\n"
        f"💰 <b>আয়:</b> ৳{earn_per_ad:.2f}\n"
        f"⏰ <b>বাকি সময়:</b> {remaining_time} সেকেন্ড\n\n"
        f"✅ সময় শেষে স্বয়ংক্রিয়ভাবে টাকা যোগ হবে!\n"
        f"🔒 দয়া করে এই পেজটি ক্লোজ করবেন না..."
    )
    
    try:
        await query.edit_message_text(countdown_text, parse_mode='HTML')
    except Exception as e:
        print(f"Error updating message: {e}")
        return
    
    # কাউন্টডাউন লুপ
    while remaining_time > 0:
        remaining_time -= 1
        await asyncio.sleep(1)
        
        if remaining_time > 0:
            countdown_text = (
                f"⏳ <b>অ্যাড কাউন্টডাউন চলছে...</b>\n\n"
                f"🏷️ <b>অ্যাড:</b> {ad['title']}\n"
                f"💰 <b>আয়:</b> ৳{earn_per_ad:.2f}\n"
                f"⏰ <b>বাকি সময়:</b> {remaining_time} সেকেন্ড\n\n"
                f"✅ সময় শেষে স্বয়ংক্রিয়ভাবে টাকা যোগ হবে!\n"
                f"🔒 দয়া করে এই পেজটি ক্লোজ করবেন না..."
            )
            
            try:
                await query.edit_message_text(countdown_text, parse_mode='HTML')
            except Exception as e:
                print(f"Error updating countdown: {e}")
                continue
    
    # কাউন্টডাউন শেষ - টাকা যোগ করুন
    earnings = watch_ad(user_id)
    
    available_ads = get_available_ads_count(user_id)
    daily_limit = int(get_setting('daily_ad_limit'))
    balance, total_earned = get_user_balance(user_id)
    
    success_text = (
        f"🎉 <b>অ্যাড সফলভাবে দেখা হয়েছে!</b>\n\n"
        f"🏷️ <b>অ্যাড:</b> {ad['title']}\n"
        f"💰 <b>আয় করেছেন:</b> ৳{earnings:.2f}\n"
        f"💵 <b>নতুন ব্যালেন্স:</b> ৳{balance:.2f}\n\n"
        f"📊 আজকের অগ্রগতি: {daily_limit - available_ads}/{daily_limit}\n"
        f"🎯 বাকি অ্যাড: {available_ads}\n\n"
        f"✅ টাকা আপনার অ্যাকাউন্টে যোগ করা হয়েছে!\n\n"
        f"🔄 আরও অ্যাড দেখতে '📺 অ্যাড দেখুন' ক্লিক করুন"
    )
    
    try:
        await query.edit_message_text(success_text, parse_mode='HTML')
    except Exception as e:
        print(f"Error showing success message: {e}")

# উত্তোলন প্রসেস - FIXED
async def process_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, account_number: str):
    user = update.effective_user
    balance, _ = get_user_balance(user.id)
    method_name = context.user_data['withdraw_method_name']
    
    amount = balance
    create_withdrawal(user.id, amount, method_name, account_number)
    
    await update.message.reply_text(
        f"✅ <b>উত্তোলন রিকোয়েস্ট সাবমিট হয়েছে!</b>\n\n"
        f"💰 উত্তোলনের পরিমাণ: ৳{amount:.2f}\n"
        f"📱 মাধ্যম: {method_name}\n"
        f"📞 অ্যাকাউন্ট: {account_number}\n"
        f"🕒 স্ট্যাটাস: পেন্ডিং\n\n"
        f"⚡ এডমিন ২৪ ঘন্টার মধ্যে টাকা পাঠাবে।",
        parse_mode='HTML'
    )
    
    # এডমিনকে নোটিফিকেশন
    admin_msg = (
        f"🔔 <b>নতুন উত্তোলন রিকোয়েস্ট!</b>\n\n"
        f"👤 ইউজার: {user.first_name} (ID: {user.id})\n"
        f"💰 পরিমাণ: ৳{amount:.2f}\n"
        f"📱 মাধ্যম: {method_name}\n"
        f"📞 অ্যাকাউন্ট: {account_number}"
    )
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_msg, parse_mode='HTML')
    
    context.user_data.pop('withdraw_method', None)
    context.user_data.pop('withdraw_method_name', None)

# এডমিন প্যানেল - COMPLETELY FIXED
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ শুধুমাত্র এডমিন এক্সেস করতে পারবেন!")
        return
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    # মোট ইউজার
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    # মোট ব্যালেন্স
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    
    # আজকের অ্যাড
    c.execute("SELECT SUM(ads_watched_today) FROM users")
    today_ads = c.fetchone()[0] or 0
    
    # পেন্ডিং উত্তোলন
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    pending_withdrawals = c.fetchone()[0]
    
    conn.close()
    
    admin_text = (
        f"👑 <b>এডমিন প্যানেল</b>\n\n"
        f"📊 <b>সিস্টেম স্ট্যাটাস:</b>\n"
        f"• মোট ইউজার: {total_users}\n"
        f"• ইউজার ব্যালেন্স: ৳{total_balance:.2f}\n"
        f"• আজকের অ্যাড: {today_ads}\n"
        f"• পেন্ডিং উত্তোলন: {pending_withdrawals}\n\n"
        f"⚙️ <b>বর্তমান সেটিংস:</b>\n"
        f"• প্রতি অ্যাড আয়: ৳{get_setting('earn_per_ad')}\n"
        f"• দৈনিক অ্যাড লিমিট: {get_setting('daily_ad_limit')}\n"
        f"• ন্যূনতম উত্তোলন: ৳{get_setting('min_withdrawal')}\n"
        f"• রেফারেল বোনাস: ৳{get_setting('referral_bonus')}\n"
        f"• অ্যাড সময়: {get_setting('ad_wait_time')} সেকেন্ড\n\n"
        f"🔧 <b>অ্যাডমিন কন্ট্রোলস:</b>"
    )
    
    await update.message.reply_text(admin_text, parse_mode='HTML', reply_markup=get_admin_panel_keyboard())

# উত্তোলন রিকোয়েস্ট ম্যানেজমেন্ট
async def admin_withdrawal_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pending_count = len(get_pending_withdrawals())
    
    requests_text = (
        f"💳 <b>উত্তোলন রিকোয়েস্ট ম্যানেজমেন্ট</b>\n\n"
        f"📊 <b>স্ট্যাটাস:</b>\n"
        f"• ⏳ পেন্ডিং রিকোয়েস্ট: {pending_count}\n\n"
        f"<b>ম্যানেজমেন্ট অপশনস:</b>"
    )
    
    await query.edit_message_text(requests_text, parse_mode='HTML', reply_markup=get_withdrawal_requests_keyboard())

# পেন্ডিং উত্তোলন দেখানো
async def admin_pending_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pending_withdrawals = get_pending_withdrawals()
    
    if not pending_withdrawals:
        await query.edit_message_text(
            "✅ <b>কোন পেন্ডিং উত্তোলন রিকোয়েস্ট নেই!</b>\n\n"
            "সকল রিকোয়েস্ট প্রসেস করা হয়েছে।",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 উত্তোলন রিকোয়েস্ট", callback_data="admin_withdrawal_requests")]
            ])
        )
        return
    
    # প্রথম রিকোয়েস্ট দেখানো
    withdrawal = pending_withdrawals[0]
    withdrawal_id, user_id, user_name, amount, method, account_number, created_at = withdrawal
    
    withdrawal_text = (
        f"⏳ <b>পেন্ডিং উত্তোলন রিকোয়েস্ট</b>\n\n"
        f"🆔 রিকোয়েস্ট আইডি: {withdrawal_id}\n"
        f"👤 ইউজার: {user_name} (ID: {user_id})\n"
        f"💰 পরিমাণ: ৳{amount:.2f}\n"
        f"📱 মাধ্যম: {method}\n"
        f"📞 অ্যাকাউন্ট: {account_number}\n"
        f"📅 তারিখ: {created_at}\n\n"
        f"<b>কি করতে চান?</b>"
    )
    
    context.user_data['current_withdrawal_index'] = 0
    context.user_data['pending_withdrawals'] = pending_withdrawals
    
    await query.edit_message_text(withdrawal_text, parse_mode='HTML', 
                                 reply_markup=get_withdrawal_action_keyboard(withdrawal_id))

# উত্তোলন অ্যাপ্রুভ/রিজেক্ট
async def handle_withdrawal_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('approve_'):
        withdrawal_id = int(query.data.replace('approve_', ''))
        
        # ট্রানজেকশন আইডি চাই
        context.user_data['awaiting_transaction_id'] = withdrawal_id
        context.user_data['action_type'] = 'approve'
        
        await query.edit_message_text(
            f"✅ <b>উত্তোলন অ্যাপ্রুভ</b>\n\n"
            f"রিকোয়েস্ট আইডি: {withdrawal_id}\n\n"
            f"<b>ট্রানজেকশন আইডি/রেফারেন্স নম্বর দিন:</b>\n"
            f"উদাহরণ: TXN123456789",
            parse_mode='HTML'
        )
        
    elif query.data.startswith('reject_'):
        withdrawal_id = int(query.data.replace('reject_', ''))
        update_withdrawal_status(withdrawal_id, 'rejected')
        
        # রিজেক্ট করার পর পরবর্তী রিকোয়েস্ট দেখানো
        await show_next_withdrawal(update, context, "❌ উত্তোলন রিকোয়েস্ট রিজেক্ট করা হয়েছে!")

async def process_transaction_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    
    if 'awaiting_transaction_id' in context.user_data:
        withdrawal_id = context.user_data['awaiting_transaction_id']
        action_type = context.user_data.get('action_type')
        transaction_id = update.message.text.strip()
        
        if action_type == 'approve':
            update_withdrawal_status(withdrawal_id, 'approved', transaction_id)
            success_msg = f"✅ উত্তোলন রিকোয়েস্ট অ্যাপ্রুভ করা হয়েছে!\nট্রানজেকশন আইডি: {transaction_id}"
        else:
            update_withdrawal_status(withdrawal_id, 'rejected')
            success_msg = "❌ উত্তোলন রিকোয়েস্ট রিজেক্ট করা হয়েছে!"
        
        await update.message.reply_text(success_msg)
        
        # পরবর্তী রিকোয়েস্ট দেখানো
        await show_next_withdrawal_from_message(update, context, success_msg)
        
        context.user_data.pop('awaiting_transaction_id', None)
        context.user_data.pop('action_type', None)

async def show_next_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, previous_message=""):
    query = update.callback_query
    current_index = context.user_data.get('current_withdrawal_index', 0)
    pending_withdrawals = context.user_data.get('pending_withdrawals', [])
    
    current_index += 1
    
    if current_index < len(pending_withdrawals):
        context.user_data['current_withdrawal_index'] = current_index
        withdrawal = pending_withdrawals[current_index]
        withdrawal_id, user_id, user_name, amount, method, account_number, created_at = withdrawal
        
        withdrawal_text = (
            f"{previous_message}\n\n"
            f"⏳ <b>পরবর্তী পেন্ডিং উত্তোলন রিকোয়েস্ট</b>\n\n"
            f"🆔 রিকোয়েস্ট আইডি: {withdrawal_id}\n"
            f"👤 ইউজার: {user_name} (ID: {user_id})\n"
            f"💰 পরিমাণ: ৳{amount:.2f}\n"
            f"📱 মাধ্যম: {method}\n"
            f"📞 অ্যাকাউন্ট: {account_number}\n"
            f"📅 তারিখ: {created_at}\n\n"
            f"<b>কি করতে চান?</b>"
        )
        
        await query.edit_message_text(withdrawal_text, parse_mode='HTML', 
                                     reply_markup=get_withdrawal_action_keyboard(withdrawal_id))
    else:
        await query.edit_message_text(
            f"{previous_message}\n\n"
            f"✅ <b>সকল পেন্ডিং রিকোয়েস্ট প্রসেস করা হয়েছে!</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 উত্তোলন রিকোয়েস্ট", callback_data="admin_withdrawal_requests")]
            ])
        )

async def show_next_withdrawal_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE, previous_message=""):
    current_index = context.user_data.get('current_withdrawal_index', 0)
    pending_withdrawals = context.user_data.get('pending_withdrawals', [])
    
    current_index += 1
    
    if current_index < len(pending_withdrawals):
        context.user_data['current_withdrawal_index'] = current_index
        withdrawal = pending_withdrawals[current_index]
        withdrawal_id, user_id, user_name, amount, method, account_number, created_at = withdrawal
        
        withdrawal_text = (
            f"{previous_message}\n\n"
            f"⏳ <b>পরবর্তী পেন্ডিং উত্তোলন রিকোয়েস্ট</b>\n\n"
            f"🆔 রিকোয়েস্ট আইডি: {withdrawal_id}\n"
            f"👤 ইউজার: {user_name} (ID: {user_id})\n"
            f"💰 পরিমাণ: ৳{amount:.2f}\n"
            f"📱 মাধ্যম: {method}\n"
            f"📞 অ্যাকাউন্ট: {account_number}\n"
            f"📅 তারিখ: {created_at}\n\n"
            f"<b>কি করতে চান?</b>"
        )
        
        await update.message.reply_text(withdrawal_text, parse_mode='HTML', 
                                      reply_markup=get_withdrawal_action_keyboard(withdrawal_id))
    else:
        await update.message.reply_text(
            f"{previous_message}\n\n"
            f"✅ <b>সকল পেন্ডিং রিকোয়েস্ট প্রসেস করা হয়েছে!</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 উত্তোলন রিকোয়েস্ট", callback_data="admin_withdrawal_requests")]
            ])
        )

# এডমিন সেটিংস ম্যানেজমেন্ট
async def admin_change_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    settings_text = (
        f"⚙️ <b>সেটিংস পরিবর্তন</b>\n\n"
        f"<b>বর্তমান সেটিংস:</b>\n"
        f"• 💰 প্রতি অ্যাড আয়: ৳{get_setting('earn_per_ad')}\n"
        f"• 🎯 দৈনিক অ্যাড লিমিট: {get_setting('daily_ad_limit')}\n"
        f"• 💸 ন্যূনতম উত্তোলন: ৳{get_setting('min_withdrawal')}\n"
        f"• 👥 রেফারেল বোনাস: ৳{get_setting('referral_bonus')}\n"
        f"• ⏱️ অ্যাড সময়: {get_setting('ad_wait_time')} সেকেন্ড\n\n"
        f"<b>কোন সেটিংস পরিবর্তন করতে চান?</b>"
    )
    
    await query.edit_message_text(settings_text, parse_mode='HTML', reply_markup=get_settings_keyboard())

# সেটিংস আপডেট হ্যান্ডলার
async def handle_setting_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    setting_map = {
        'setting_earn_per_ad': ('earn_per_ad', 'প্রতি অ্যাড আয়'),
        'setting_daily_limit': ('daily_ad_limit', 'দৈনিক অ্যাড লিমিট'),
        'setting_min_withdrawal': ('min_withdrawal', 'ন্যূনতম উত্তোলন'),
        'setting_referral_bonus': ('referral_bonus', 'রেফারেল বোনাস'),
        'setting_ad_wait_time': ('ad_wait_time', 'অ্যাড সময়')
    }
    
    if query.data in setting_map:
        setting_key, setting_name = setting_map[query.data]
        context.user_data['awaiting_setting'] = setting_key
        context.user_data['setting_name'] = setting_name
        context.user_data['setting_message_id'] = query.message.message_id
        
        await query.edit_message_text(
            f"✏️ <b>{setting_name} পরিবর্তন</b>\n\n"
            f"বর্তমান মান: {get_setting(setting_key)}\n\n"
            f"<b>নতুন মান টাইপ করুন:</b>",
            parse_mode='HTML'
        )

# এডমিন কলব্যাক হ্যান্ডলার
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_change_settings":
        await admin_change_settings(update, context)
    elif query.data == "admin_back_to_panel":
        await admin_panel_from_query(update, context)
    elif query.data == "admin_back_to_menu":
        await query.edit_message_text("🔙 মেনুতে ফিরে যাচ্ছেন...")
    elif query.data == "admin_user_stats":
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(balance) FROM users")
        total_balance = c.fetchone()[0] or 0
        c.execute("SELECT SUM(ads_watched_today) FROM users")
        today_ads = c.fetchone()[0] or 0
        conn.close()
        
        await query.edit_message_text(
            f"📊 <b>ইউজার স্ট্যাটিস্টিক্স</b>\n\n"
            f"• মোট রেজিস্টার্ড ইউজার: {total_users}\n"
            f"• মোট ব্যালেন্স: ৳{total_balance:.2f}\n"
            f"• আজকের অ্যাড: {today_ads}\n"
            f"• গড় আয়: ৳{total_balance/total_users:.2f}" if total_users > 0 else "• গড় আয়: ৳০.০০",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 অ্যাডমিন প্যানেল", callback_data="admin_back_to_panel")]
            ])
        )
    elif query.data == "admin_earnings_report":
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("SELECT SUM(total_earned) FROM users")
        total_earnings = c.fetchone()[0] or 0
        c.execute("SELECT SUM(earned_amount) FROM referrals")
        referral_earnings = c.fetchone()[0] or 0
        conn.close()
        
        await query.edit_message_text(
            f"📈 <b>আয় রিপোর্ট</b>\n\n"
            f"• মোট আয়: ৳{total_earnings:.2f}\n"
            f"• রেফারেল আয়: ৳{referral_earnings:.2f}\n"
            f"• অ্যাড আয়: ৳{total_earnings - referral_earnings:.2f}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 অ্যাডমিন প্যানেল", callback_data="admin_back_to_panel")]
            ])
        )
    elif query.data == "admin_withdrawal_requests":
        await admin_withdrawal_requests(update, context)
    elif query.data == "admin_pending_withdrawals":
        await admin_pending_withdrawals(update, context)
    elif query.data.startswith('approve_') or query.data.startswith('reject_'):
        await handle_withdrawal_action(update, context)
    elif query.data.startswith('setting_'):
        await handle_setting_change(update, context)

async def admin_panel_from_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    
    if not is_admin(user.id):
        await query.edit_message_text("❌ শুধুমাত্র এডমিন এক্সেস করতে পারবেন!")
        return
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(ads_watched_today) FROM users")
    today_ads = c.fetchone()[0] or 0
    
    conn.close()
    
    admin_text = (
        f"👑 <b>এডমিন প্যানেল</b>\n\n"
        f"📊 <b>সিস্টেম স্ট্যাটাস:</b>\n"
        f"• মোট ইউজার: {total_users}\n"
        f"• ইউজার ব্যালেন্স: ৳{total_balance:.2f}\n"
        f"• আজকের অ্যাড: {today_ads}\n\n"
        f"⚙️ <b>বর্তমান সেটিংস:</b>\n"
        f"• প্রতি অ্যাড আয়: ৳{get_setting('earn_per_ad')}\n"
        f"• দৈনিক অ্যাড লিমিট: {get_setting('daily_ad_limit')}\n"
        f"• ন্যূনতম উত্তোলন: ৳{get_setting('min_withdrawal')}\n"
        f"• রেফারেল বোনাস: ৳{get_setting('referral_bonus')}\n"
        f"• অ্যাড সময়: {get_setting('ad_wait_time')} সেকেন্ড\n\n"
        f"🔧 <b>অ্যাডমিন কন্ট্রোলস:</b>"
    )
    
    await query.edit_message_text(admin_text, parse_mode='HTML', reply_markup=get_admin_panel_keyboard())

# মেসেজ হ্যান্ডলার
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    
    register_user(user.id, user.first_name)
    
    # উত্তোলন ট্রানজেকশন আইডি হ্যান্ডলিং
    if is_admin(user.id) and 'awaiting_transaction_id' in context.user_data:
        await process_transaction_id(update, context)
        return
    
    # এডমিন সেটিংস আপডেট হ্যান্ডলিং
    if is_admin(user.id) and 'awaiting_setting' in context.user_data:
        setting_key = context.user_data['awaiting_setting']
        setting_name = context.user_data['setting_name']
        
        try:
            new_value = text.strip()
            # সংখ্যা চেক করুন
            if new_value.replace('.', '').isdigit():
                new_value = float(new_value) if '.' in new_value else int(new_value)
                update_setting(setting_key, str(new_value))
                
                await update.message.reply_text(
                    f"✅ <b>{setting_name} সফলভাবে আপডেট হয়েছে!</b>\n\n"
                    f"নতুন মান: {new_value}",
                    parse_mode='HTML'
                )
                
                # সেটিংস মেনুতে ফিরে যান
                await admin_change_settings_from_message(update, context)
            else:
                await update.message.reply_text("❌ দয়া করে একটি সঠিক সংখ্যা দিন!")
            
        except ValueError:
            await update.message.reply_text("❌ দয়া করে একটি সঠিক সংখ্যা দিন!")
        
        context.user_data.pop('awaiting_setting', None)
        context.user_data.pop('setting_name', None)
        return
    
    # উত্তোলন প্রসেস হ্যান্ডলিং
    if 'withdraw_method' in context.user_data and text.replace(' ', '').isdigit() and len(text) == 11:
        await process_withdrawal(update, context, text)
        return
    
    # রেগুলার মেসেজ হ্যান্ডলিং
    if text == "📺 অ্যাড দেখুন":
        await watch_ads_message(update, context)
    elif text == "💰 ব্যালেন্স":
        await show_balance_message(update, context)
    elif text == "💸 টাকা তুলুন":
        await withdraw_money_message(update, context)
    elif text == "👥 রেফারেল":
        await show_referrals_message(update, context)
    elif text == "👤 প্রোফাইল":
        await my_accounts_message(update, context)
    elif text == "❓ হেল্প":
        await show_help_message(update, context)
    elif text == "👑 অ্যাডমিন প্যানেল" and is_admin(user.id):
        await admin_panel(update, context)
    else:
        if is_admin(user.id):
            reply_markup = get_admin_keyboard()
        else:
            reply_markup = get_main_keyboard()
        
        await update.message.reply_text(
            "🤖 নিচের মেনু থেকে অপশন সিলেক্ট করুন:",
            reply_markup=reply_markup
        )

async def admin_change_settings_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_text = (
        f"⚙️ <b>সেটিংস পরিবর্তন</b>\n\n"
        f"<b>বর্তমান সেটিংস:</b>\n"
        f"• 💰 প্রতি অ্যাড আয়: ৳{get_setting('earn_per_ad')}\n"
        f"• 🎯 দৈনিক অ্যাড লিমিট: {get_setting('daily_ad_limit')}\n"
        f"• 💸 ন্যূনতম উত্তোলন: ৳{get_setting('min_withdrawal')}\n"
        f"• 👥 রেফারেল বোনাস: ৳{get_setting('referral_bonus')}\n"
        f"• ⏱️ অ্যাড সময়: {get_setting('ad_wait_time')} সেকেন্ড\n\n"
        f"<b>কোন সেটিংস পরিবর্তন করতে চান?</b>"
    )
    
    await update.message.reply_text(settings_text, parse_mode='HTML', reply_markup=get_settings_keyboard())

# কলব্যাক হ্যান্ডলার
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    
    try:
        await query.answer()
    except Exception as e:
        print(f"Error answering callback: {e}")
    
    if query.data == "start_countdown":
        await start_countdown_callback(update, context)
    elif query.data.startswith('admin_') or query.data.startswith('setting_'):
        await handle_admin_callback(update, context)
    elif query.data.startswith('withdraw_'):
        await handle_withdraw_callback(update, context)
    elif query.data.startswith('approve_') or query.data.startswith('reject_'):
        await handle_withdrawal_action(update, context)

# বাকি ফাংশনগুলি
async def show_balance_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    
    balance, total_earned = get_user_balance(user.id)
    min_withdrawal = get_setting('min_withdrawal')
    
    await update.message.reply_text(
        f"💰 <b>ব্যালেন্স</b>\n\n"
        f"💵 <b>বর্তমান ব্যালেন্স:</b> ৳{balance:.2f}\n"
        f"📈 <b>মোট আয়:</b> ৳{total_earned:.2f}\n\n"
        f"💸 <b>ন্যূনতম উত্তোলন:</b> ৳{min_withdrawal}",
        parse_mode='HTML'
    )

async def withdraw_money_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    
    balance, total_earned = get_user_balance(user.id)
    min_withdrawal = float(get_setting('min_withdrawal'))
    
    if balance < min_withdrawal:
        await update.message.reply_text(
            f"💸 <b>টাকা তুলুন</b>\n\n"
            f"❌ আপনার ব্যালেন্স যথেষ্ট নয়!\n"
            f"💰 আপনার ব্যালেন্স: ৳{balance:.2f}\n"
            f"💵 ন্যূনতম উত্তোলন: ৳{min_withdrawal:.2f}",
            parse_mode='HTML'
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("📱 বিকাশ", callback_data="withdraw_bkash")],
        [InlineKeyboardButton("📱 নগদ", callback_data="withdraw_nagad")],
        [InlineKeyboardButton("📱 রকেট", callback_data="withdraw_rocket")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"💸 <b>টাকা তুলুন</b>\n\n"
        f"💰 আপনার ব্যালেন্স: ৳{balance:.2f}\n"
        f"📊 ন্যূনতম উত্তোলন: ৳{min_withdrawal:.2f}\n\n"
        f"⚡ উত্তোলনের মাধ্যম সিলেক্ট করুন:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def show_referrals_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    
    user_id = user.id
    referral_count, referral_earnings = get_referral_stats(user_id)
    referral_bonus = get_setting('referral_bonus')
    
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start=ref{user_id}"
    
    await update.message.reply_text(
        f"👥 <b>রেফারেল সিস্টেম</b>\n\n"
        f"🔗 <b>আপনার রেফারেল লিংক:</b>\n<code>{referral_link}</code>\n\n"
        f"📊 রেফারেল স্ট্যাটস:\n"
        f"• মোট রেফারেল: {referral_count}\n"
        f"• রেফারেল থেকে আয়: ৳{referral_earnings:.2f}\n"
        f"• রেফারেল বোনাস: ৳{referral_bonus} প্রতি সাইনআপ",
        parse_mode='HTML'
    )

async def my_accounts_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    
    balance, total_earned = get_user_balance(user.id)
    referral_count, referral_earnings = get_referral_stats(user.id)
    available_ads = get_available_ads_count(user.id)
    daily_limit = int(get_setting('daily_ad_limit'))
    
    await update.message.reply_text(
        f"👤 <b>প্রোফাইল</b>\n\n"
        f"👤 নাম: {user.first_name}\n"
        f"💵 ব্যালেন্স: ৳{balance:.2f}\n"
        f"📈 মোট আয়: ৳{total_earned:.2f}\n"
        f"👥 রেফারেল: {referral_count} জন\n"
        f"📺 আজকের অ্যাড: {daily_limit - available_ads}/{daily_limit}",
        parse_mode='HTML'
    )

async def show_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    earn_per_ad = get_setting('earn_per_ad')
    daily_limit = get_setting('daily_ad_limit')
    min_withdrawal = get_setting('min_withdrawal')
    ad_wait_time = get_setting('ad_wait_time')
    
    help_text = (
        f"❓ <b>হেল্প ও সাপোর্ট</b>\n\n"
        f"📖 <b>টাকা আয় করার উপায়:</b>\n"
        f"1. '📺 অ্যাড দেখুন' ক্লিক করুন\n"
        f"2. '🚀 অ্যাড দেখুন' বাটনে ক্লিক করে অ্যাড ওপেন করুন\n"
        f"3. '⏱️ ১৫ সেকেন্ড কাউন্টডাউন শুরু করুন' বাটনে ক্লিক করুন\n"
        f"4. {ad_wait_time} সেকেন্ড অপেক্ষা করুন\n"
        f"5. স্বয়ংক্রিয়ভাবে টাকা পেয়ে যান\n"
        f"6. দৈনিক লিমিট: {daily_limit} অ্যাড\n"
        f"7. টাকা উঠান ৳{min_withdrawal} থেকে\n\n"
        f"👥 <b>আমাদের অফিসিয়াল গ্রুপ:</b>\n"
        f"<a href='https://t.me/+hgds2QYqh9piNmM1'>📢 টেলিগ্রাম ইনকাম গ্রুপ</a>\n\n"
        f"📞 <b>সাপোর্ট:</b> @Mohammad2021g\n\n"
        f"💡 <b>সমস্যা হলে গ্রুপে জয়েন করে জানান</b>"
    )
    
    keyboard = [
        [InlineKeyboardButton("📢 অফিসিয়াল গ্রুপে জয়েন করুন", url="https://t.me/+hgds2QYqh9piNmM1")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)

async def handle_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if query.data.startswith('withdraw_'):
        method = query.data.replace('withdraw_', '')
        method_names = {
            'bkash': 'বিকাশ',
            'nagad': 'নগদ', 
            'rocket': 'রকেট'
        }
        
        context.user_data['withdraw_method'] = method
        context.user_data['withdraw_method_name'] = method_names[method]
        
        await query.edit_message_text(
            f"💸 <b>{method_names[method]} এ টাকা তুলুন</b>\n\n"
            f"📱 আপনার {method_names[method]} নম্বর দিন:\n\n"
            f"📝 ফরম্যাট: 01XXXXXXXXX",
            parse_mode='HTML'
        )

def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", main_menu))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 বট সেটআপ সম্পূর্ণ!")
    print("✅ উত্তোলন রিকোয়েস্ট ম্যানেজমেন্ট সিস্টেম যোগ করা হয়েছে")
    print("💰 এডমিন এখন আয় রেট কন্ট্রোল করতে পারবে")
    print("💳 উত্তোলন রিকোয়েস্ট অ্যাপ্রুভ/রিজেক্ট করা যাবে")
    print("📊 সকল ফাংশন সম্পূর্ণ কাজ করবে")
    
    application.run_polling()

if __name__ == "__main__":
    main()
