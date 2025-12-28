# bot.py
import os
import random
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
import re
from collections import defaultdict

# КОНФИГУРАЦИЯ
BOT_TOKEN = "8223819252:AAHITzl1-monrSkS775VLL4BaY0AMQp80k8"  # Токенуңузду текшериңиз!
ADMIN_ID = 7804443638
ADMIN_USERNAME = "@mrxkasa"
CHANNELS = [
    "https://t.me/KG_MRX",
    "https://t.me/Taanyshuu777",
    "https://t.me/MEDUZA044"
]

# Донат ссылка
DONATE_LINK = "https://t.me/MrxKassa"

DATABASE_NAME = "games_bot.db"
INITIAL_BALANCE = 5000
REFERRAL_BONUS = 1000
MIN_BET = 1000
ROULETTE_LIMIT = 999999999
TRANSFER_COOLDOWN_HOURS = 6
TRANSFER_DAILY_LIMIT = 10000

# GIF файлы - Render'де жок болсо, аны URL менен алмаштырыңыз
GIF_PATH = "animation (1) (1).gif"  # Эгерде GIF жок болсо, жөнөкөй текст колдонулат

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatManager:
    def __init__(self):
        self.roulette_bets = defaultdict(dict)
        self.roulette_spinning = defaultdict(bool)
        self.next_roulette_result = {}
        self.group_roulette_results = defaultdict(list)
        self.last_bet_amounts = defaultdict(dict)
        self.last_bet_types = defaultdict(dict)
        self.go_tasks = {}
        
    def reset_chat_roulette(self, chat_id):
        if chat_id in self.roulette_bets:
            del self.roulette_bets[chat_id]
        if chat_id in self.last_bet_amounts:
            del self.last_bet_amounts[chat_id]
        if chat_id in self.last_bet_types:
            del self.last_bet_types[chat_id]
        if chat_id in self.next_roulette_result:
            del self.next_roulette_result[chat_id]

def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0,
            last_transfer TIMESTAMP,
            referral_code TEXT,
            total_bet INTEGER DEFAULT 0,
            total_win INTEGER DEFAULT 0,
            max_bet INTEGER DEFAULT 0,
            max_win INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Не женат',
            licenses INTEGER DEFAULT 0,
            vip_licenses INTEGER DEFAULT 0,
            roulette_limit INTEGER DEFAULT 2000000,
            display_name TEXT,
            daily_transfer_used INTEGER DEFAULT 0,
            last_daily_reset TIMESTAMP,
            married_to INTEGER DEFAULT NULL,
            marriage_date TIMESTAMP,
            marriage_partner_name TEXT,
            transfer_limit INTEGER DEFAULT 10000,
            added_users INTEGER DEFAULT 0,
            is_muted INTEGER DEFAULT 0,
            mute_until TIMESTAMP,
            mute_by INTEGER DEFAULT NULL,
            can_mute INTEGER DEFAULT 0,
            can_ban INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            blocked_by INTEGER,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roulette_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bet_type TEXT,
            bet_value TEXT,
            amount INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roulette_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            amount INTEGER,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS global_roulette_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS added_users_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            added_user_id INTEGER,
            chat_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            reason TEXT,
            warned_by INTEGER,
            warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            can_mute INTEGER DEFAULT 0,
            can_ban INTEGER DEFAULT 0,
            granted_by INTEGER,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            top_users TEXT,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("База инициализирована")

init_db()

class UserManager:
    @staticmethod
    def get_user(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    @staticmethod
    def create_user(user_id, username, first_name, referral_code=None):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        referrer_id = None
        if referral_code:
            cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
            result = cursor.fetchone()
            if result:
                referrer_id = result[0]

        cursor.execute(
            """INSERT OR IGNORE INTO users
            (user_id, username, first_name, referral_code, balance, display_name,
             roulette_limit, daily_transfer_used, last_daily_reset, transfer_limit, added_users,
             is_muted, mute_until, mute_by, can_mute, can_ban)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, first_name, f"ref_{user_id}", INITIAL_BALANCE, first_name,
             ROULETTE_LIMIT, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), TRANSFER_DAILY_LIMIT, 0,
             0, None, None, 0, 0)
        )

        if referrer_id:
            cursor.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id = ?",
                         (REFERRAL_BONUS, referrer_id))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?",
                         (REFERRAL_BONUS, user_id))

            cursor.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
                (referrer_id, REFERRAL_BONUS, "ref_bonus", f"Реферальный бонус за {username}")
            )
            cursor.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
                (user_id, REFERRAL_BONUS, "ref_bonus", f"Реферальный бонус при регистрации")
            )

        conn.commit()
        conn.close()

    @staticmethod
    def update_balance(user_id, amount, description=""):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

        if amount < 0:
            cursor.execute("UPDATE users SET total_bet = total_bet + ? WHERE user_id = ?", (abs(amount), user_id))
            cursor.execute("UPDATE users SET max_bet = MAX(max_bet, ?) WHERE user_id = ?", (abs(amount), user_id))
            transaction_type = "bet"
        else:
            cursor.execute("UPDATE users SET total_win = total_win + ? WHERE user_id = ?", (amount, user_id))
            cursor.execute("UPDATE users SET max_win = MAX(max_win, ?) WHERE user_id = ?", (amount, user_id))
            transaction_type = "win"

        cursor.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, abs(amount), transaction_type, description)
        )

        conn.commit()
        conn.close()

    @staticmethod
    def update_added_users(user_id, count):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET added_users = added_users + ? WHERE user_id = ?", (count, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def get_added_users_in_chat(user_id, chat_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM added_users_history WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    @staticmethod
    def is_muted(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT is_muted, mute_until FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return False

        is_muted, mute_until = result
        if is_muted and mute_until:
            try:
                mute_time = datetime.strptime(mute_until, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > mute_time:
                    conn = sqlite3.connect(DATABASE_NAME)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET is_muted = 0, mute_until = NULL WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
                    return False
                return True
            except:
                return False
        return False

    @staticmethod
    def mute_user(user_id, hours, muted_by=None):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        mute_until = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE users SET is_muted = 1, mute_until = ?, mute_by = ? WHERE user_id = ?",
                      (mute_until, muted_by, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def unmute_user(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_muted = 0, mute_until = NULL, mute_by = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def block_user(user_id, reason, blocked_by):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO blocked_users (user_id, reason, blocked_by) VALUES (?, ?, ?)",
            (user_id, reason, blocked_by)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def is_blocked(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM blocked_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    @staticmethod
    def unblock_user(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def can_make_transfer(user_id, amount):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT transfer_limit, last_transfer, daily_transfer_used FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return False, "Пользователь не найден"

        transfer_limit, last_transfer_str, daily_used = result
        now = datetime.now()

        if daily_used + amount > transfer_limit:
            remaining = transfer_limit - daily_used
            conn.close()
            return False, f"Лимит на передачу {transfer_limit} монет за {TRANSFER_COOLDOWN_HOURS} часов. Вы еще можете передать: {remaining}"

        if last_transfer_str:
            try:
                last_transfer = datetime.strptime(last_transfer_str, "%Y-%m-%d %H:%M:%S")
                time_diff = (now - last_transfer).total_seconds() / 3600
                if time_diff < TRANSFER_COOLDOWN_HOURS:
                    pass
            except:
                pass

        if amount < 10:
            conn.close()
            return False, f"Минимальная сумма перевода: 10 монет"

        remaining = transfer_limit - daily_used

        conn.close()
        return True, f"Можно переводить. Доступно: {remaining}"

    @staticmethod
    def update_transfer_usage(user_id, amount):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("UPDATE users SET last_transfer = ?, daily_transfer_used = daily_transfer_used + ? WHERE user_id = ?",
                      (now, amount, user_id))

        conn.commit()
        conn.close()

    @staticmethod
    def reset_daily_limits():
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET daily_transfer_used = 0, last_daily_reset = ?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

        conn.commit()
        conn.close()

    @staticmethod
    def get_transaction_history(user_id, limit=10):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, amount, type, description FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, limit)
        )
        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def add_global_roulette_log(chat_id, result):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO global_roulette_logs (chat_id, result) VALUES (?, ?)",
            (chat_id, result)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_global_roulette_logs(chat_id, limit=10):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT result FROM global_roulette_logs WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit)
        )
        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def get_global_roulette_logs_all(chat_id, limit=21):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT result FROM global_roulette_logs WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit)
        )
        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def add_roulette_log(chat_id, user_id, result):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO roulette_logs (chat_id, user_id, result) VALUES (?, ?, ?)",
            (chat_id, user_id, result)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def grant_permission(chat_id, user_id, permission_type, granted_by):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        if permission_type == "mute":
            cursor.execute("UPDATE users SET can_mute = 1 WHERE user_id = ?", (user_id,))
            cursor.execute(
                "INSERT INTO admin_permissions (chat_id, user_id, can_mute, granted_by) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, 1, granted_by)
            )
        elif permission_type == "ban":
            cursor.execute("UPDATE users SET can_ban = 1 WHERE user_id = ?", (user_id,))
            cursor.execute(
                "INSERT INTO admin_permissions (chat_id, user_id, can_ban, granted_by) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, 1, granted_by)
            )
        elif permission_type == "all":
            cursor.execute("UPDATE users SET can_mute = 1, can_ban = 1 WHERE user_id = ?", (user_id,))
            cursor.execute(
                "INSERT INTO admin_permissions (chat_id, user_id, can_mute, can_ban, granted_by) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, 1, 1, granted_by)
            )

        conn.commit()
        conn.close()

    @staticmethod
    def revoke_permission(user_id, permission_type):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        if permission_type == "mute":
            cursor.execute("UPDATE users SET can_mute = 0 WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM admin_permissions WHERE user_id = ? AND can_mute = 1", (user_id,))
        elif permission_type == "ban":
            cursor.execute("UPDATE users SET can_ban = 0 WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM admin_permissions WHERE user_id = ? AND can_ban = 1", (user_id,))
        elif permission_type == "all":
            cursor.execute("UPDATE users SET can_mute = 0, can_ban = 0 WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM admin_permissions WHERE user_id = ?", (user_id,))

        conn.commit()
        conn.close()

    @staticmethod
    def has_permission(user_id, permission_type):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        if permission_type == "mute":
            cursor.execute("SELECT can_mute FROM users WHERE user_id = ?", (user_id,))
        elif permission_type == "ban":
            cursor.execute("SELECT can_ban FROM users WHERE user_id = ?", (user_id,))
        else:
            conn.close()
            return False

        result = cursor.fetchone()
        conn.close()

        if result and result[0] == 1:
            return True
        return False

    @staticmethod
    def get_chat_top_users(chat_id, limit=10):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_id, display_name, username, first_name, balance
            FROM users
            WHERE balance > 0
            ORDER BY balance DESC LIMIT ?
        """, (limit,))

        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def get_global_top_users(limit=10):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_id, display_name, username, first_name, balance
            FROM users
            WHERE balance > 0
            ORDER BY balance DESC LIMIT ?
        """, (limit,))

        result = cursor.fetchall()
        conn.close()
        return result

    @staticmethod
    def get_user_position_by_balance(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) + 1 as position
            FROM users u1
            WHERE balance > (SELECT balance FROM users WHERE user_id = ?)
        """, (user_id,))

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 1

    @staticmethod
    def update_chat_stats(chat_id, top_users_text):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO chat_stats (chat_id, top_users, last_update)
            VALUES (?, ?, ?)
        """, (chat_id, top_users_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        conn.close()

    @staticmethod
    def get_chat_stats(chat_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT top_users FROM chat_stats WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else None

    @staticmethod
    def set_display_name(user_id, display_name):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET display_name = ? WHERE user_id = ?", (display_name, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def add_coins_to_user(user_id, amount):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

        cursor.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, amount, "admin_add", f"Админ добавил {amount} монет")
        )

        conn.commit()
        conn.close()
        return True

    @staticmethod
    def remove_coins_from_user(user_id, amount):
        """Админ монета түшүрө алат"""
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, "Пользователь не найден"
            
        current_balance = result[0]
        
        if amount > current_balance:
            cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (user_id,))
            removed_amount = current_balance
        else:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            removed_amount = amount
            
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, -removed_amount, "admin_remove", f"Админ убрал {removed_amount} монет")
        )
        
        conn.commit()
        conn.close()
        return True, removed_amount

    @staticmethod
    def set_roulette_limit(user_id, limit):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET roulette_limit = ? WHERE user_id = ?", (limit, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def set_transfer_limit(user_id, limit):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET transfer_limit = ? WHERE user_id = ?", (limit, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def get_transfer_limit(user_id):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT transfer_limit FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            return result[0]
        return TRANSFER_DAILY_LIMIT

    @staticmethod
    def reduce_all_balances_to_100k():
        """Баардык колдонуучулардын балансын 100кга түшүрүү"""
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM users WHERE balance > 100000")
            users_count = cursor.fetchone()[0]
            
            affected_users = 0
            
            if users_count > 0:
                cursor.execute("UPDATE users SET balance = 100000 WHERE balance > 100000")
                affected_users = cursor.rowcount
            
            conn.commit()
            logger.info(f"Баланстары түшүрүлдү: {affected_users} колдонуучу")
            
            return affected_users
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Балансты түшүрүүдө ката: {e}")
            return 0
        finally:
            conn.close()

    @staticmethod
    def reduce_all_balances_above_limit(limit=100000):
        """Белгилүү чектен жогору баланстары бар колдонуучулардын балансын чекке чейин түшүрүү"""
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM users WHERE balance > ?", (limit,))
            users_count = cursor.fetchone()[0]
            
            affected_users = 0
            
            if users_count > 0:
                cursor.execute("UPDATE users SET balance = ? WHERE balance > ?", (limit, limit))
                affected_users = cursor.rowcount
            
            conn.commit()
            logger.info(f"Баланстары {limit:,}га түшүрүлдү: {affected_users} колдонуучу")
            
            return affected_users
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Балансты түшүрүүдө ката: {e}")
            return 0
        finally:
            conn.close()

chat_manager = ChatManager()

URL_PATTERNS = [
    r'https?://\S+',
    r't\.me/\S+',
    r'@\w+',
    r'telegram\.me/\S+',
    r'bit\.ly/\S+',
    r'tinyurl\.com/\S+'
]

def contains_url(text):
    if not text:
        return False

    text_lower = text.lower()

    for pattern in URL_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    return False

def calculate_next_result(logs, chat_id=None):
    if not logs:
        return "7🔴"

    if chat_id and chat_id in chat_manager.next_roulette_result:
        result = chat_manager.next_roulette_result[chat_id]
        if result and len(result) >= 2 and re.match(r'^\d+', result):
            return result
        else:
            del chat_manager.next_roulette_result[chat_id]

    last_results = logs[:10]

    red_count = 0
    black_count = 0
    green_count = 0

    for result in last_results:
        if result:
            if "🔴" in result:
                red_count += 1
            elif "⚫️" in result:
                black_count += 1
            elif "💚" in result:
                green_count += 1

    last_result = logs[0] if logs else "0💚"

    if red_count >= black_count and red_count >= green_count:
        black_numbers = ["2⚫️", "4⚫️", "6⚫️", "8⚫️", "10⚫️", "12⚫️"]
        filtered = [num for num in black_numbers if num != last_result]
        if filtered:
            result = random.choice(filtered)
        else:
            result = random.choice(black_numbers)

    elif black_count >= red_count and black_count >= green_count:
        red_numbers = ["1🔴", "3🔴", "5🔴", "7🔴", "9🔴", "11🔴"]
        filtered = [num for num in red_numbers if num != last_result]
        if filtered:
            result = random.choice(filtered)
        else:
            result = random.choice(red_numbers)

    else:
        if green_count > 0 and random.random() < 0.1:
            result = "0💚"
        else:
            all_numbers = [
                "0💚", "1🔴", "2⚫️", "3🔴", "4⚫️", "5🔴", "6⚫️",
                "7🔴", "8⚫️", "9🔴", "10⚫️", "11🔴", "12⚫️"
            ]
            possible_numbers = [num for num in all_numbers if num != last_result]
            if possible_numbers:
                result = random.choice(possible_numbers)
            else:
                result = "7🔴"

    if not result or not re.match(r'^\d+', result):
        result = "7🔴"

    if chat_id:
        chat_manager.next_roulette_result[chat_id] = result

    return result

async def handle_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['creator', 'administrator']:
            if not UserManager.has_permission(user_id, "ban") and user_id != ADMIN_ID:
                await update.message.reply_text("❌ У вас нет разрешения на бан!")
                return
    except:
        await update.message.reply_text("❌ Ошибка при проверке прав!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Кого забанить? Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id

    if target_user_id == user_id:
        await update.message.reply_text("❌ Вы не можете забанить себя!")
        return

    if target_user_id == context.bot.id:
        await update.message.reply_text("❌ Вы не можете забанить бота!")
        return

    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            until_date=datetime.now() + timedelta(days=30)
        )

        UserManager.block_user(target_user_id, f"Забанен в группе {chat_id}", user_id)

        target_name = target_user.first_name
        if target_user.username:
            target_name = target_user.username

        await update.message.reply_text(f"✅ Пользователь {target_name} забанен и удален из группы!")

    except Exception as e:
        logger.error(f"Ошибка при бане: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['creator', 'administrator']:
            if not UserManager.has_permission(user_id, "mute") and user_id != ADMIN_ID:
                await update.message.reply_text("❌ У вас нет разрешения на мут!")
                return
    except:
        await update.message.reply_text("❌ Ошибка при проверке прав!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Кого замутить? Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id

    if target_user_id == user_id:
        await update.message.reply_text("❌ Вы не можете замутить себя!")
        return

    if target_user_id == context.bot.id:
        await update.message.reply_text("❌ Вы не можете замутить бота!")
        return

    try:
        target_chat_member = await context.bot.get_chat_member(chat_id, target_user_id)
        if target_chat_member.status == 'creator':
            await update.message.reply_text("❌ Вы не можете замутить создателя группы!")
            return
    except:
        pass

    hours = 24
    message_text = update.message.text.lower()
    words = message_text.split()

    if len(words) > 1:
        try:
            hours = int(words[1])
            if hours < 1:
                hours = 1
            if hours > 720:
                hours = 720
        except ValueError:
            hours = 24

    UserManager.mute_user(target_user_id, hours, user_id)

    target_name = target_user.first_name
    if target_user.username:
        target_name = target_user.username

    await update.message.reply_text(
        f"🔇 Пользователь {target_name} замучен на {hours} часов!\n"
        f"Он не сможет писать в группу до окончания мута."
    )

async def handle_unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['creator', 'administrator']:
            if not UserManager.has_permission(user_id, "mute") and user_id != ADMIN_ID:
                await update.message.reply_text("❌ У вас нет разрешения на размут!")
                return
    except:
        await update.message.reply_text("❌ Ошибка при проверке прав!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Кого размутить? Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id

    UserManager.unmute_user(target_user_id)

    target_name = target_user.first_name
    if target_user.username:
        target_name = target_user.username

    await update.message.reply_text(
        f"🔊 Пользователь {target_name} размучен!\n"
        f"Теперь он может писать в группу."
    )

async def handle_permission_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status != 'creator':
            await update.message.reply_text("❌ Только создатель группы может выдавать разрешения!")
            return
    except:
        await update.message.reply_text("❌ Ошибка при проверке прав!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Кому выдать разрешение? Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id

    message_text = update.message.text.lower()
    words = message_text.split()

    if len(words) < 2:
        await update.message.reply_text("❌ Укажите тип разрешения: мут, бан или все")
        return

    permission_type = words[1]

    if permission_type not in ["мут", "бан", "все"]:
        await update.message.reply_text("❌ Неверный тип разрешения. Используйте: мут, бан или все")
        return

    UserManager.grant_permission(chat_id, target_user_id, permission_type, user_id)

    target_name = target_user.first_name
    if target_user.username:
        target_name = target_user.username

    permission_text = {
        "мут": "разрешение на мут",
        "бан": "разрешение на бан",
        "все": "разрешения на мут и бан"
    }

    await update.message.reply_text(
        f"✅ Пользователю {target_name} выдано {permission_text[permission_type]}!\n"
        f"Теперь он может использовать соответствующие команды."
    )

async def handle_revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status != 'creator':
            await update.message.reply_text("❌ Только создатель группы может отбирать разрешения!")
            return
    except:
        await update.message.reply_text("❌ Ошибка при проверке прав!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ У кого забрать разрешение? Ответьте на сообщение пользователя!")
        return

    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id

    message_text = update.message.text.lower()
    words = message_text.split()

    if len(words) < 2:
        await update.message.reply_text("❌ Укажите тип разрешения: мут, бан или все")
        return

    permission_type = words[1]

    if permission_type not in ["мут", "бан", "все"]:
        await update.message.reply_text("❌ Неверный тип разрешения. Используйте: мут, бан или все")
        return

    UserManager.revoke_permission(target_user_id, permission_type)

    target_name = target_user.first_name
    if target_user.username:
        target_name = target_user.username

    permission_text = {
        "мут": "разрешение на мут",
        "бан": "разрешение на бан",
        "все": "все разрешения"
    }

    await update.message.reply_text(
        f"✅ У пользователя {target_name} отозвано {permission_text[permission_type]}!"
    )

async def handle_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_name = target_user.first_name
        if target_user.username:
            target_name = target_user.username

        await update.message.reply_text(f"🆔 ID пользователя {target_name}: {target_user_id}")
    else:
        user = UserManager.get_user(user_id)
        if user and user[15]:
            display_name = user[15]
        elif user and user[1]:
            display_name = user[1]
        else:
            display_name = update.effective_user.first_name

        await update.message.reply_text(f"🆔 Ваш ID ({display_name}): {user_id}")

async def handle_setname_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 2:
        await update.message.reply_text("❌ Укажите новое имя! Пример: /setname НовоеИмя")
        return

    new_name = ' '.join(words[1:])

    if len(new_name) > 50:
        await update.message.reply_text("❌ Имя слишком длинное! Максимум 50 символов.")
        return

    UserManager.set_display_name(user_id, new_name)

    await update.message.reply_text(f"✅ Ваше отображаемое имя изменено на: {new_name}")

async def handle_addcoins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 3:
        await update.message.reply_text("❌ Формат команды: /addcoins <user_id> <amount>")
        return

    try:
        target_user_id = int(words[1])
        amount = int(words[2])

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return

        user = UserManager.get_user(target_user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден!")
            return

        UserManager.add_coins_to_user(target_user_id, amount)

        target_name = user[15] if user[15] else (user[1] if user[1] else user[2])
        await update.message.reply_text(f"✅ Пользователю {target_name} добавлено {amount} монет!\nНовый баланс: {user[3] + amount} 🪙")

    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Используйте: /addcoins <user_id> <amount>")

async def handle_removecoins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 3:
        await update.message.reply_text("❌ Формат команды: /removecoins <user_id> <amount>")
        return

    try:
        target_user_id = int(words[1])
        amount = int(words[2])

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return

        user = UserManager.get_user(target_user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден!")
            return

        success, removed_amount = UserManager.remove_coins_from_user(target_user_id, amount)
        
        if success:
            target_name = user[15] if user[15] else (user[1] if user[1] else user[2])
            await update.message.reply_text(f"✅ У пользователя {target_name} убрано {removed_amount} монет!\nНовый баланс: {max(0, user[3] - removed_amount)} 🪙")
        else:
            await update.message.reply_text("❌ Ошибка при удалении монет!")

    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Используйте: /removecoins <user_id> <amount>")

async def handle_setlimit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 4:
        await update.message.reply_text(
            "❌ Формат команды: /setlimit <user_id> <тип> <лимит>\n\n"
            "📋 Примеры:\n"
            "• /setlimit 123456789 transfer 50000 - установить лимит перевода 50000 монет\n"
            "• /setlimit 123456789 roulette 5000000 - установить лимит рулетки 5 млн\n\n"
            "💡 Можно установить очень большие значения:\n"
            "• /setlimit 123456789 transfer 999999999\n"
            "• /setlimit 123456789 roulette 999999999"
        )
        return

    try:
        target_user_id = int(words[1])
        limit_type = words[2].lower()
        limit = int(words[3])

        if limit <= 0:
            await update.message.reply_text("❌ Лимит должен быть положительным!")
            return

        user = UserManager.get_user(target_user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден!")
            return

        if limit_type == "roulette":
            UserManager.set_roulette_limit(target_user_id, limit)
            target_name = user[15] if user[15] else (user[1] if user[1] else user[2])
            await update.message.reply_text(
                f"✅ Лимит рулетки для пользователя {target_name} (ID: {target_user_id})\n"
                f"Установлен: {limit:,} монет 🪙\n\n"
                f"Теперь он может ставить до {limit:,} монет в рулетке!"
            )
        elif limit_type == "transfer":
            UserManager.set_transfer_limit(target_user_id, limit)
            target_name = user[15] if user[15] else (user[1] if user[1] else user[2])
            await update.message.reply_text(
                f"✅ Лимит перевода для пользователя {target_name} (ID: {target_user_id})\n"
                f"Установлен: {limit:,} монет 🪙 за {TRANSFER_COOLDOWN_HOURS} часов\n\n"
                f"Теперь он может переводить до {limit:,} монет каждые {TRANSFER_COOLDOWN_HOURS} часов!"
            )
        else:
            await update.message.reply_text("❌ Неверный тип лимита! Используйте: roulette или transfer")

    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Используйте числа для ID и лимита")

async def handle_limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 2:
        await update.message.reply_text("❌ Формат: /limits <user_id>")
        return

    try:
        target_user_id = int(words[1])
        user = UserManager.get_user(target_user_id)

        if not user:
            await update.message.reply_text("❌ Пользователь не найден!")
            return

        roulette_limit = user[14] if len(user) > 14 and user[14] else ROULETTE_LIMIT
        transfer_limit = user[21] if len(user) > 21 and user[21] else TRANSFER_DAILY_LIMIT

        target_name = user[15] if user[15] else (user[1] if user[1] else user[2])

        await update.message.reply_text(
            f"📊 Лимиты пользователя {target_name} (ID: {target_user_id}):\n\n"
            f"🎰 Лимит рулетки: {roulette_limit:,} монет 🪙\n"
            f"🔄 Лимит перевода: {transfer_limit:,} монет 🪙 за {TRANSFER_COOLDOWN_HOURS} ч.\n\n"
            f"💰 Баланс: {user[3]:,} 🪙"
        )

    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID!")

async def handle_resetbalances_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Баардык колдонуучулардын балансын 100кга түшүрүү командасы"""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    try:
        affected_users = UserManager.reduce_all_balances_to_100k()

        if affected_users > 0:
            await update.message.reply_text(
                f"✅ Баланстар түшүрүлдү!\n\n"
                f"📊 Натыйжалар:\n"
                f"• Түшүрүлгөн колдонуучулар: {affected_users}\n"
                f"• Жаңы баланс: 100,000 🪙 (же андан төмөн)\n\n"
                f"💎 Баардык колдонуучулардын балансы 100кга чейин түшүрүлдү.\n"
                f"📈 100кдан төмөн баланстары барлар өзгөрүлгөн жок."
            )
        else:
            await update.message.reply_text("✅ 100кдан жогору баланстары бар колдонуучулар жок!")

    except Exception as e:
        logger.error(f"Балансты түшүрүү командасында ката: {e}")
        await update.message.reply_text(f"❌ Ката: {e}")

async def handle_reducebalances_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Балансты түшүрүү командасы (каалаган чек менен)"""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return

    text = update.message.text.strip()
    words = text.split()

    if len(words) < 2:
        await update.message.reply_text(
            "❌ Формат: /reducebalances <чеки>\n\n"
            "📋 Мисалдар:\n"
            "• /reducebalances 100000 - 100кга чейин түшүрүү\n"
            "• /reducebalances 50000 - 50кга чейин түшүрүү\n"
            "• /reducebalances 5000 - 5кга чейин түшүрүү\n\n"
            "💡 Эскертүү: Балансы чекинен төмөн колдонуучулар өзгөрүлбөйт!"
        )
        return

    try:
        limit = int(words[1])

        if limit < 0:
            await update.message.reply_text("❌ Чек терс сан болбошу керек!")
            return

        affected_users = UserManager.reduce_all_balances_above_limit(limit)

        if affected_users > 0:
            await update.message.reply_text(
                f"✅ Баланстар түшүрүлдү!\n\n"
                f"📊 Натыйжалар:\n"
                f"• Түшүрүлгөн колдонуучулар: {affected_users}\n"
                f"• Жаңы баланс: {limit:,} 🪙 (же андан төмөн)\n\n"
                f"💎 {limit:,}дан жогору баланстары бар колдонуучулардын балансы түшүрүлдү.\n"
                f"📈 {limit:,}дан төмөн баланстары барлар өзгөрүлгөн жок."
            )
        else:
            await update.message.reply_text(f"✅ {limit:,}дан жогору баланстары бар колдонуучулар жок!")

    except ValueError:
        await update.message.reply_text("❌ Туура эмес формат! Сан киргизиңиз.")
    except Exception as e:
        logger.error(f"Балансты түшүрүү командасында ката: {e}")
        await update.message.reply_text(f"❌ Ката: {e}")

class Games:
    @staticmethod
    async def ruleka(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        keyboard = [
            [
                InlineKeyboardButton("1-3", callback_data="bet_1_3"),
                InlineKeyboardButton("4-6", callback_data="bet_4_6"),
                InlineKeyboardButton("7-9", callback_data="bet_7_9"),
                InlineKeyboardButton("10-12", callback_data="bet_10_12")
            ],
            [
                InlineKeyboardButton("1к🔴", callback_data="bet_red"),
                InlineKeyboardButton("1к⚫️", callback_data="bet_black"),
                InlineKeyboardButton("1к💚", callback_data="bet_zero")
            ],
            [
                InlineKeyboardButton("Повторить", callback_data="repeat_bet"),
                InlineKeyboardButton("Удвоить", callback_data="double_bet"),
                InlineKeyboardButton("Крутить", callback_data="spin_roulette")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        user = UserManager.get_user(user_id)
        if not user:
            return

        roulette_layout = (
            "Минирулетка\n"
            "Угадайте число из:\n"
            "0💚\n"
            "1🔴 2⚫️ 3🔴 4⚫️ 5🔴 6⚫️\n"
            "7🔴 8⚫️ 9🔴10⚫️11🔴12⚫️\n"
            "Ставки можно текстом\n"
            "1000 на красное | 5000 на 12"
        )

        await update.message.reply_text(roulette_layout, reply_markup=reply_markup)

    @staticmethod
    async def handle_roulette_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_type: str, bet_value: str, amount: int):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return False

        if amount <= 0:
            return False

        if amount < MIN_BET:
            return False

        if user[3] < amount:
            if user[15]:
                display_name = user[15]
            elif user[1]:
                display_name = user[1]
            else:
                display_name = user[2]

            keyboard = [
                [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"{display_name}, ставка не может превышать ваши средства\n\n",
                reply_markup=reply_markup
            )
            return False

        if user_id not in chat_manager.roulette_bets[chat_id]:
            chat_manager.roulette_bets[chat_id][user_id] = []

        if user[15]:
            username = user[15]
        elif user[1]:
            username = user[1]
        else:
            username = user[2]

        existing_bet = None
        for bet in chat_manager.roulette_bets[chat_id][user_id]:
            if bet['type'] == bet_type and bet['value'] == bet_value:
                existing_bet = bet
                break

        bet_description = ""
        if bet_type == 'number':
            bet_description = f"ставка на число {bet_value}"
        elif bet_type == 'color':
            color_names = {'red': 'красное', 'black': 'чёрное', 'zero': 'зеленое'}
            bet_description = f"ставка на {color_names.get(bet_value, bet_value)}"
        elif bet_type == 'range':
            range_names = {'1-3': '1-3', '4-6': '4-6', '7-9': '7-9', '10-12': '10-12'}
            bet_description = f"ставка на диапазон {range_names.get(bet_value, bet_value)}"

        if existing_bet:
            existing_bet['amount'] += amount
        else:
            chat_manager.roulette_bets[chat_id][user_id].append({
                'type': bet_type,
                'value': bet_value,
                'amount': amount,
                'username': username
            })

        UserManager.update_balance(user_id, -amount, f"Ставка в рулетку: {bet_description}")

        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO roulette_bets (user_id, bet_type, bet_value, amount) VALUES (?, ?, ?, ?)",
            (user_id, bet_type, bet_value, amount)
        )
        conn.commit()
        conn.close()

        chat_manager.last_bet_amounts[chat_id][user_id] = amount
        chat_manager.last_bet_types[chat_id][user_id] = (bet_type, bet_value, bet_description)

        return True

    @staticmethod
    async def spin_roulette_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        if chat_id in chat_manager.roulette_spinning and chat_manager.roulette_spinning[chat_id]:
            if update.callback_query:
                await update.callback_query.answer("Рулетка уже крутится!", show_alert=True)
            return

        if chat_id not in chat_manager.roulette_bets or not chat_manager.roulette_bets[chat_id]:
            if update.callback_query:
                await update.callback_query.answer("❌ Никто не сделал ставок! Сначала сделайте ставку.", show_alert=True)
            return

        chat_manager.roulette_spinning[chat_id] = True

        try:
            winning_number = 0
            winning_color = "💚"
            color_name = "зеленое"

            if chat_id in chat_manager.next_roulette_result and chat_manager.next_roulette_result[chat_id]:
                winning_result = chat_manager.next_roulette_result[chat_id]
                try:
                    if winning_result:
                        match = re.match(r'^(\d+)', winning_result)
                        if match:
                            winning_number = int(match.group(1))
                        else:
                            winning_number = random.randint(0, 12)

                        if "💚" in winning_result:
                            winning_color = "💚"
                            color_name = "зеленое"
                        elif "🔴" in winning_result:
                            winning_color = "🔴"
                            color_name = "красное"
                        elif "⚫️" in winning_result:
                            winning_color = "⚫️"
                            color_name = "чёрное"
                        else:
                            if winning_number == 0:
                                winning_color = "💚"
                                color_name = "зеленое"
                            elif winning_number % 2 == 1:
                                winning_color = "🔴"
                                color_name = "красное"
                            else:
                                winning_color = "⚫️"
                                color_name = "чёрное"
                    else:
                        winning_number = random.randint(0, 12)
                        if winning_number == 0:
                            winning_color = "💚"
                            color_name = "зеленое"
                        elif winning_number % 2 == 1:
                            winning_color = "🔴"
                            color_name = "красное"
                        else:
                            winning_color = "⚫️"
                            color_name = "чёрное"
                except (ValueError, AttributeError) as e:
                    logger.error(f"Ошибка обработки next_roulette_result: {e}")
                    winning_number = random.randint(0, 12)
                    if winning_number == 0:
                        winning_color = "💚"
                        color_name = "зеленое"
                    elif winning_number % 2 == 1:
                        winning_color = "🔴"
                        color_name = "красное"
                    else:
                        winning_color = "⚫️"
                        color_name = "чёрное"
            else:
                winning_number = random.randint(0, 12)
                if winning_number == 0:
                    winning_color = "💚"
                    color_name = "зеленое"
                elif winning_number % 2 == 1:
                    winning_color = "🔴"
                    color_name = "красное"
                else:
                    winning_color = "⚫️"
                    color_name = "чёрное"

            result_text = f"{winning_number}{winning_color}"

            UserManager.add_global_roulette_log(chat_id, result_text)

            if chat_id not in chat_manager.group_roulette_results:
                chat_manager.group_roulette_results[chat_id] = []

            chat_manager.group_roulette_results[chat_id].insert(0, result_text)
            if len(chat_manager.group_roulette_results[chat_id]) > 21:
                chat_manager.group_roulette_results[chat_id] = chat_manager.group_roulette_results[chat_id][:21]

            try:
                if os.path.exists(GIF_PATH):
                    with open(GIF_PATH, 'rb') as gif_file:
                        gif_message = await context.bot.send_animation(
                            chat_id=chat_id,
                            animation=gif_file,
                            caption="🎡 Рулетка вращается..."
                        )
                else:
                    gif_message = await context.bot.send_message(
                        chat_id=chat_id,
                        text="🎡 Рулетка вращается..."
                    )

                await asyncio.sleep(3)

                try:
                    await context.bot.delete_message(
                        chat_id=chat_id,
                        message_id=gif_message.message_id
                    )
                except:
                    pass

            except Exception as e:
                logger.error(f"Ошибка отправки GIF: {e}")

            if chat_manager.roulette_bets[chat_id]:
                for user_id in chat_manager.roulette_bets[chat_id]:
                    UserManager.add_roulette_log(chat_id, user_id, result_text)

            result_message = f"Рулетка: {winning_number}{winning_color}\n"

            all_bets = []

            if chat_manager.roulette_bets[chat_id]:
                for user_id, bet_info in chat_manager.roulette_bets[chat_id].items():
                    user = UserManager.get_user(user_id)
                    if not user:
                        continue

                    if user[15]:
                        username = user[15]
                    elif user[1]:
                        username = user[1]
                    else:
                        username = user[2]

                    for bet in bet_info:
                        bet_won = False
                        win_amount = 0
                        multiplier = 1

                        if bet['type'] == 'number':
                            if int(bet['value']) == winning_number:
                                bet_won = True
                                multiplier = 12
                                win_amount = bet['amount'] * multiplier

                        elif bet['type'] == 'color':
                            color_map = {'red': '🔴', 'black': '⚫️', 'zero': '💚'}
                            if bet['value'] in color_map and color_map[bet['value']] == winning_color:
                                bet_won = True
                                multiplier = 2
                                win_amount = bet['amount'] * multiplier

                        elif bet['type'] == 'range':
                            ranges = {
                                '1_3': (1, 3), '4_6': (4, 6),
                                '7_9': (7, 9), '10_12': (10, 12)
                            }
                            if bet['value'] in ranges:
                                start, end = ranges[bet['value']]
                                if start <= winning_number <= end:
                                    bet_won = True
                                    multiplier = 3
                                    win_amount = bet['amount'] * multiplier

                        if bet_won:
                            UserManager.update_balance(user_id, win_amount, f"Выигрыш в рулетку: +{win_amount}")
                            display_value = "⚫" if bet['value'] == "black" else "🔴" if bet['value'] == "red" else bet['value']
                            winning_bet = f"<a href='tg://user?id={user_id}'>{username}</a> выиграл {win_amount} на {display_value}"
                            all_bets.append((winning_bet, True, user_id))
                        else:
                            display_value = "чёрное" if bet['value'] == "black" else "красное" if bet['value'] == "red" else bet['value']
                            losing_bet = f"{username} {bet['amount']} на {display_value}"
                            all_bets.append((losing_bet, False, user_id))

            for bet_text, is_winning, bet_user_id in all_bets:
                if not is_winning:
                    result_message += f"{bet_text}\n"

            for bet_text, is_winning, bet_user_id in all_bets:
                if is_winning:
                    result_message += f"{bet_text}\n"

            if not all_bets:
                result_message += "Никто не сделал ставок\n"

            keyboard = [
                [
                    InlineKeyboardButton("1-3", callback_data="bet_1_3"),
                    InlineKeyboardButton("4-6", callback_data="bet_4_6"),
                    InlineKeyboardButton("7-9", callback_data="bet_7_9"),
                    InlineKeyboardButton("10-12", callback_data="bet_10_12")
                ],
                [
                    InlineKeyboardButton("1к🔴", callback_data="bet_red"),
                    InlineKeyboardButton("1к⚫️", callback_data="bet_black"),
                    InlineKeyboardButton("1к💚", callback_data="bet_zero")
                ],
                [
                    InlineKeyboardButton("Повторить", callback_data="repeat_bet"),
                    InlineKeyboardButton("Удвоить", callback_data="double_bet"),
                    InlineKeyboardButton("Крутить", callback_data="spin_roulette")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if update.callback_query:
                try:
                    await update.callback_query.message.edit_text(result_message, parse_mode='HTML')
                except:
                    pass
                await context.bot.send_message(chat_id=chat_id, text=result_message, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=chat_id, text=result_message, parse_mode='HTML')

        finally:
            if chat_id in chat_manager.roulette_bets:
                chat_manager.roulette_bets[chat_id] = {}
            chat_manager.roulette_spinning[chat_id] = False
            if chat_id in chat_manager.next_roulette_result:
                del chat_manager.next_roulette_result[chat_id]

    @staticmethod
    async def handle_bandit_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return False

        if amount < MIN_BET:
            return False

        if user[3] < amount:
            if user[15]:
                display_name = user[15]
            elif user[1]:
                display_name = user[1]
            else:
                display_name = user[2]

            keyboard = [[InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"{display_name}, недостаточно монет!\n\n",
                reply_markup=reply_markup
            )
            return False

        UserManager.update_balance(user_id, -amount, f"Ставка в бандитку: -{amount}")

        asyncio.create_task(Games._banditka_logic_with_amount(update, context, amount))
        return True

    @staticmethod
    async def banditka(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        if user[3] < MIN_BET:
            keyboard = [[InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Недостаточно монет\n\n", reply_markup=reply_markup)
            return

        amount = MIN_BET
        UserManager.update_balance(user_id, -amount, f"Ставка в бандитку: -{amount}")

        asyncio.create_task(Games._banditka_logic_with_amount(update, context, amount))

    @staticmethod
    async def _banditka_logic_with_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)
        first_name = update.effective_user.first_name

        symbols = ["♦️", "♣️", "♥️", "♠️", "🧧", "🎴", "🀄"]
        result = [random.choice(symbols) for _ in range(5)]

        message = await update.message.reply_text(f"{first_name}\n\n{result[0]}|■|■|■|■|")
        await asyncio.sleep(1.0)

        await message.edit_text(f"{first_name}\n\n{result[0]}{result[1]}|■|■|■|")
        await asyncio.sleep(1.0)

        await message.edit_text(f"{first_name}\n\n{result[0]}{result[1]}{result[2]}|■|■|")
        await asyncio.sleep(1.0)

        await message.edit_text(f"{first_name}\n\n{result[0]}{result[1]}{result[2]}{result[3]}|■|")
        await asyncio.sleep(1.0)

        final_result = "".join(result)
        unique = len(set(result))

        if unique == 1:
            win = random.randint(amount * 7, amount * 8)
        elif unique == 2:
            win = random.randint(amount * 4, amount * 5)
        elif unique == 3:
            win = random.randint(amount * 2, amount * 3)
        else:
            win = 0

        if win > 0:
            UserManager.update_balance(user_id, win, f"Выигрыш в бандитку: +{win}")
            final_message = f"{first_name}\n\n{final_result}\n\nВыигрыш: {win} 🪙"
        else:
            final_message = f"{first_name}\n\n{final_result}\n\nПроигрыш: {amount} 🪙"

        await message.edit_text(final_message)

async def handle_go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id in chat_manager.go_tasks and not chat_manager.go_tasks[chat_id].done():
        await update.message.reply_text("⏳ ГО уже запущен! Подождите завершения.")
        return

    task = asyncio.create_task(run_go_command(update, context, chat_id, user_id))
    chat_manager.go_tasks[chat_id] = task

    def cleanup(_):
        if chat_id in chat_manager.go_tasks:
            del chat_manager.go_tasks[chat_id]

    task.add_done_callback(cleanup)

async def run_go_command(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    user = UserManager.get_user(user_id)
    if not user:
        return

    if chat_id not in chat_manager.roulette_bets or not chat_manager.roulette_bets[chat_id]:
        await update.effective_chat.send_message("❌ Никто не сделал ставок! Сначала сделайте ставку.")
        return

    if user[15]:
        display_name = user[15]
    elif user[1]:
        display_name = user[1]
    else:
        display_name = user[2]

    random_wait = random.choice([3, 5, 10, 12, 15])

    time_message = await update.effective_chat.send_message(f"{display_name} крутит (через {random_wait} сек)..")

    await asyncio.sleep(random_wait)

    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=time_message.message_id
        )
    except Exception as e:
        logger.error(f"Ошибка удаления сообщения: {e}")

    try:
        if os.path.exists(GIF_PATH):
            with open(GIF_PATH, 'rb') as gif_file:
                gif_message = await update.effective_chat.send_animation(
                    animation=gif_file,
                    caption="🎡 Рулетка вращается..."
                )
        else:
            gif_message = await update.effective_chat.send_message(
                "🎡 Рулетка вращается..."
            )

        await asyncio.sleep(3)

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=gif_message.message_id
            )
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка отправки GIF: {e}")

    winning_number = 0
    winning_color = "💚"
    color_name = "зеленое"

    if chat_id in chat_manager.next_roulette_result and chat_manager.next_roulette_result[chat_id]:
        winning_result = chat_manager.next_roulette_result[chat_id]
        try:
            if winning_result:
                match = re.match(r'^(\d+)', winning_result)
                if match:
                    winning_number = int(match.group(1))
                else:
                    winning_number = random.randint(0, 12)

                if "💚" in winning_result:
                    winning_color = "💚"
                    color_name = "зеленое"
                elif "🔴" in winning_result:
                    winning_color = "🔴"
                    color_name = "красное"
                elif "⚫️" in winning_result:
                    winning_color = "⚫️"
                    color_name = "чёрное"
                else:
                    if winning_number == 0:
                        winning_color = "💚"
                        color_name = "зеленое"
                    elif winning_number % 2 == 1:
                        winning_color = "🔴"
                        color_name = "красное"
                    else:
                        winning_color = "⚫️"
                        color_name = "чёрное"
            else:
                winning_number = random.randint(0, 12)
                if winning_number == 0:
                    winning_color = "💚"
                    color_name = "зеленое"
                elif winning_number % 2 == 1:
                    winning_color = "🔴"
                    color_name = "красное"
                else:
                    winning_color = "⚫️"
                    color_name = "чёрное"
        except (ValueError, AttributeError) as e:
            logger.error(f"Ошибка обработки next_roulette_result: {e}")
            winning_number = random.randint(0, 12)
            if winning_number == 0:
                winning_color = "💚"
                color_name = "зеленое"
            elif winning_number % 2 == 1:
                winning_color = "🔴"
                color_name = "красное"
            else:
                winning_color = "⚫️"
                color_name = "чёрное"
    else:
        winning_number = random.randint(0, 12)
        if winning_number == 0:
            winning_color = "💚"
            color_name = "зеленое"
        elif winning_number % 2 == 1:
            winning_color = "🔴"
            color_name = "красное"
        else:
            winning_color = "⚫️"
            color_name = "чёрное"

    result_text = f"{winning_number}{winning_color}"

    UserManager.add_global_roulette_log(chat_id, result_text)

    if chat_id not in chat_manager.group_roulette_results:
        chat_manager.group_roulette_results[chat_id] = []

    chat_manager.group_roulette_results[chat_id].insert(0, result_text)
    if len(chat_manager.group_roulette_results[chat_id]) > 21:
        chat_manager.group_roulette_results[chat_id] = chat_manager.group_roulette_results[chat_id][:21]

    if chat_manager.roulette_bets[chat_id]:
        for user_id in chat_manager.roulette_bets[chat_id]:
            UserManager.add_roulette_log(chat_id, user_id, result_text)

    result_message = f"Рулетка: {winning_number}{winning_color}\n"

    all_bets = []

    if chat_manager.roulette_bets[chat_id]:
        for user_id, bet_info in chat_manager.roulette_bets[chat_id].items():
            user = UserManager.get_user(user_id)
            if not user:
                continue

            if user[15]:
                username = user[15]
            elif user[1]:
                username = user[1]
            else:
                username = user[2]

            for bet in bet_info:
                bet_won = False
                win_amount = 0
                multiplier = 1

                if bet['type'] == 'number':
                    if int(bet['value']) == winning_number:
                        bet_won = True
                        multiplier = 12
                        win_amount = bet['amount'] * multiplier

                elif bet['type'] == 'color':
                    color_map = {'red': '🔴', 'black': '⚫️', 'zero': '💚'}
                    if bet['value'] in color_map and color_map[bet['value']] == winning_color:
                        bet_won = True
                        multiplier = 2
                        win_amount = bet['amount'] * multiplier

                elif bet['type'] == 'range':
                    ranges = {
                        '1_3': (1, 3), '4_6': (4, 6),
                        '7_9': (7, 9), '10_12': (10, 12)
                    }
                    if bet['value'] in ranges:
                        start, end = ranges[bet['value']]
                        if start <= winning_number <= end:
                            bet_won = True
                            multiplier = 3
                            win_amount = bet['amount'] * multiplier

                if bet_won:
                    UserManager.update_balance(user_id, win_amount, f"Выигрыш в рулетку: +{win_amount}")
                    display_value = "⚫" if bet['value'] == "black" else "🔴" if bet['value'] == "red" else bet['value']
                    winning_bet = f"<a href='tg://user?id={user_id}'>{username}</a> выиграл {win_amount} на {display_value}"
                    all_bets.append((winning_bet, True, user_id))
                else:
                    display_value = "чёрное" if bet['value'] == "black" else "красное" if bet['value'] == "red" else bet['value']
                    losing_bet = f"{username} {bet['amount']} на {display_value}"
                    all_bets.append((losing_bet, False, user_id))

    for bet_text, is_winning, bet_user_id in all_bets:
        if not is_winning:
            result_message += f"{bet_text}\n"

    for bet_text, is_winning, bet_user_id in all_bets:
        if is_winning:
            result_message += f"{bet_text}\n"

    if not all_bets:
        result_message += "Никто не сделал ставок\n"

    await update.effective_chat.send_message(result_message, parse_mode='HTML')

    chat_manager.reset_chat_roulette(chat_id)

async def show_small_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user = UserManager.get_user(user_id)

    if not user:
        return

    logs_db = UserManager.get_global_roulette_logs(chat_id, 10)
    logs = [log[0] for log in logs_db] if logs_db else []

    if not logs:
        await update.message.reply_text("Лог пуст")
        return

    log_text = ""
    for i, log in enumerate(logs, 1):
        if log:
            log_text += f"{log}\n"

    if log_text.strip():
        await update.message.reply_text(log_text.strip())

        if user_id == ADMIN_ID:
            next_result = calculate_next_result(logs, chat_id)

            last_result = logs[0] if logs else "0💚"

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎯 АДМИНГЕ ЖЕКЕ МААЛЫМАТ:\n\n"
                         f"📊 Акыркы 10 натыйжа:\n{log_text.strip()}\n\n"
                         f"🔮 Кийинки болушу мүмкүн резултат: {next_result}\n"
                         f"📈 Акыркы резултат: {last_result}\n\n"
                         f"💎 Бул маалыматты ийгиликтуу пайдаланыңыз!"
                )
            except Exception as e:
                logger.error(f"Админге жеке кат жөнөтүүдө ката: {e}")

async def show_big_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user = UserManager.get_user(user_id)

    if not user:
        return

    logs_db = UserManager.get_global_roulette_logs_all(chat_id, 21)
    logs = [log[0] for log in logs_db] if logs_db else []

    if not logs:
        await update.message.reply_text("Лог пуст")
        return

    log_text = ""
    for i, log in enumerate(logs, 1):
        if log:
            log_text += f"{log}\n"

    if log_text.strip():
        await update.message.reply_text(log_text.strip())

        if user_id == ADMIN_ID:
            next_result = calculate_next_result(logs, chat_id)

            last_result = logs[0] if logs else "0💚"

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎯 АДМИНГЕ ЖЕКЕ МААЛЫМАТ (ДЛОГ):\n\n"
                         f"📊 Акыркы 21 натыйжа:\n{log_text.strip()}\n\n"
                         f"🔮 Кийинки болушу мүмкүн резултат: {next_result}\n"
                         f"📈 Акыркы резултат: {last_result}\n\n"
                         f"💎 Бул маалыматты ийгиликтуу пайдаланыңыз!"
                )
            except Exception as e:
                logger.error(f"Админге жеке кат жөнөтүүдө ката: {e}")

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if update.effective_chat.type in ['group', 'supergroup']:
        if UserManager.is_muted(user_id):
            try:
                await update.message.delete()
                return
            except Exception as e:
                logger.error(f"Ошибка при проверке мута: {e}")

        text = update.message.text or ""
        if contains_url(text):
            try:
                await update.message.delete()
                warning_msg = await update.effective_chat.send_message(
                    f"⚠️ {update.effective_user.first_name}, отправка ссылок запрещена в этой группе!"
                )
                await asyncio.sleep(10)
                try:
                    await context.bot.delete_message(
                        chat_id=chat_id,
                        message_id=warning_msg.message_id
                    )
                except:
                    pass
                return
            except Exception as e:
                logger.error(f"Ошибка при удалении ссылки: {e}")

    user = UserManager.get_user(user_id)
    if not user:
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        UserManager.create_user(user_id, username, first_name, None)
        user = UserManager.get_user(user_id)

    if not user:
        return

    text = update.message.text.strip()
    text_lower = text.lower()

    if text.upper() == "Б":
        if user[15]:
            display_name = user[15]
        elif user[1]:
            display_name = user[1]
        else:
            display_name = user[2]

        await update.message.reply_text(f"{display_name}\nМонеты: {user[3]}🪙")
        return

    if text.upper() == "ГО":
        await handle_go_command(update, context)
        return

    if text.upper() == "ЛОГ":
        await show_small_log(update, context)
        return

    if text.upper() == "ДЛОГ":
        await show_big_log(update, context)
        return

    if text.lower().strip() == "/my":
        return

    if text.lower().strip() == "/id":
        await handle_id_command(update, context)
        return

    if text.lower().startswith("/setname"):
        await handle_setname_command(update, context)
        return

    if text.lower().startswith("/addcoins"):
        await handle_addcoins_command(update, context)
        return

    if text.lower().startswith("/removecoins"):
        await handle_removecoins_command(update, context)
        return

    if text.lower().startswith("/setlimit"):
        await handle_setlimit_command(update, context)
        return

    if text.lower().startswith("/limits"):
        await handle_limits_command(update, context)
        return

    if text.lower().startswith("/resetbalances"):
        await handle_resetbalances_command(update, context)
        return

    if text.lower().startswith("/reducebalances"):
        await handle_reducebalances_command(update, context)
        return

    if text.upper() == "ТОП":
        current_user_id = update.effective_user.id
        current_user = UserManager.get_user(current_user_id)
        user_position = UserManager.get_user_position_by_balance(current_user_id)

        top_users = UserManager.get_global_top_users(10)

        if not top_users:
            top_text = "[ТОП 10 БОГАТЫХ]\n\nТоп пуст!\n\n"
            telegram_name = current_user[2] if current_user and current_user[2] else update.effective_user.first_name
            top_text += f"{telegram_name}: {user_position} место"
            await update.message.reply_text(top_text)
            return

        top_text = "[ТОП 10 БОГАТЫХ]\n\n"

        for i, (user_id, display_name, username, first_name, balance) in enumerate(top_users, 1):
            if display_name:
                name = display_name
            elif username:
                name = username
            else:
                name = first_name

            top_text += f"{i}. {name} [{balance}]\n"

        top_text += "¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯\n"
        telegram_name = current_user[2] if current_user and current_user[2] else update.effective_user.first_name
        top_text += f"{telegram_name}: {user_position} место"

        await update.message.reply_text(top_text)
        return

    if text.upper() == "ГТОП":
        current_user_id = update.effective_user.id
        current_user = UserManager.get_user(current_user_id)
        user_position = UserManager.get_user_position_by_balance(current_user_id)

        cached_top = UserManager.get_chat_stats(chat_id)

        if cached_top:
            lines = cached_top.split('\n')
            new_top_text = ""

            for line in lines:
                if "Сиздин баланс:" in line or "ТЕЛЕГРАМ АТЫ:" in line:
                    telegram_name = current_user[2] if current_user and current_user[2] else update.effective_user.first_name
                    new_top_text += f"{telegram_name}: {user_position} место\n"
                else:
                    new_top_text += line + "\n"

            await update.message.reply_text(new_top_text.strip())
            return

        top_users = UserManager.get_chat_top_users(chat_id, 10)

        if not top_users:
            top_text = "[ТОП 10 БОГАТЫХ]\n\nТоп пуст!\n\n"
            telegram_name = current_user[2] if current_user and current_user[2] else update.effective_user.first_name
            top_text += f"{telegram_name}: {user_position} место"
            await update.message.reply_text(top_text)
            return

        top_text = "[ТОП 10 БОГАТЫХ]\n\n"

        for i, (user_id, display_name, username, first_name, balance) in enumerate(top_users, 1):
            if display_name:
                name = display_name
            elif username:
                name = username
            else:
                name = first_name

            top_text += f"{i}. {name} [{balance}]\n"

        top_text += "¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯\n"
        telegram_name = current_user[2] if current_user and current_user[2] else update.effective_user.first_name
        top_text += f"{telegram_name}: {user_position} место"

        cache_text = top_text
        UserManager.update_chat_stats(chat_id, cache_text.strip())

        await update.message.reply_text(top_text)
        return

    if text.upper() in ["ДОНАТ", "ДОНАЦ", "DONATE"]:
        user = UserManager.get_user(user_id)

        if not user:
            return

        display_name = user[15] if len(user) > 15 and user[15] else (user[1] if user[1] else user[2])

        keyboard = [
            [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        donate_text = f"💰 ДОНАТ ДЛЯ {display_name}\n\n🆔 Ваш ID: {user_id}"
        await update.message.reply_text(donate_text, reply_markup=reply_markup)
        return

    if text.upper() in ["ССЫЛКИ", "СЫЛКО", "ССЫЛКА", "LINKS", "LINK"]:
        links_text = "🔗 КАНАЛЫ:\n" + "\n".join(CHANNELS)
        await update.message.reply_text(links_text)
        return

    if text.upper() in ["ПРОФИЛЬ", "ПРОФ", "PROFILE", "PROF"]:
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        if user[15]:
            display_name = user[15]
        elif user[1]:
            display_name = user[1]
        else:
            display_name = user[2]

        profile_text = (
            f"{display_name}: ♠️♥️\n"
            f"ID: {user_id}\n"
            f"Монеты: {user[3]}🪙\n"
            f"Выиграно: {user[8]}\n"
            f"Проиграно: {user[7]}\n"
            f"Макс. выигрыш: {user[10]}\n"
            f"Макс. ставка: {user[9]}"
        )

        await update.message.reply_text(profile_text)
        return

    if text.upper() in ["ИСТОРИЯ", "HISTORY", "ИСТ"]:
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        transactions = UserManager.get_transaction_history(user_id, 10)

        if not transactions:
            await update.message.reply_text("История транзакций пуста!")
            return

        history_text = "История транзакций\n\n"

        for date_str, amount, trans_type, description in transactions:
            time_str = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime("%H:%M:%S")

            if amount > 0:
                if "выигрыш" in description.lower():
                    history_text += f"[{time_str}] выигрыш в рулетку: +{amount}\n"
                elif "перевод от игрока" in description.lower():
                    player_name = description.split("перевод от игрока ")[-1]
                    history_text += f"[{time_str}] перевод от игрока {player_name}: +{amount}\n"
                elif "бандит" in description.lower():
                    history_text += f"[{time_str}] выигрыш в бандита: +{amount}\n"
                elif "донат" in description.lower():
                    history_text += f"[{time_str}] донат: +{amount}\n"
                else:
                    history_text += f"[{time_str}] +{amount}\n"
            else:
                if "проигрыш" in description.lower():
                    if "рулетк" in description.lower():
                        history_text += f"[{time_str}] проигрыш в рулетку: {amount}\n"
                    elif "бандит" in description.lower():
                        history_text += f"[{time_str}] проигрыш в бандита: {amount}\n"
                    else:
                        history_text += f"[{time_str}] проигрыш: {amount}\n"
                elif "ставка" in description.lower():
                    history_text += f"[{time_str}] ставка: {amount}\n"
                elif "перевод игроку" in description.lower():
                    player_name = description.split("перевод игроку ")[-1]
                    history_text += f"[{time_str}] перевод игроку {player_name}: {amount}\n"
                else:
                    history_text += f"[{time_str}] {amount}\n"

        await update.message.reply_text(history_text)
        return

    if text.lower().strip() == "бан":
        await handle_ban_command(update, context)
        return

    if text.lower().strip() == "мут":
        await handle_mute_command(update, context)
        return

    if text.lower().strip() == "размут":
        await handle_unmute_command(update, context)
        return

    if text.lower().startswith("разрешение"):
        await handle_permission_command(update, context)
        return

    if text.lower().startswith("отозвать"):
        await handle_revoke_command(update, context)
        return

    if text.upper() == "СТАВКИ":
        chat_id = update.effective_chat.id
        if chat_id in chat_manager.roulette_bets and user_id in chat_manager.roulette_bets[chat_id] and chat_manager.roulette_bets[chat_id][user_id]:
            if user[15]:
                display_name = user[15]
            elif user[1]:
                display_name = user[1]
            else:
                display_name = user[2]

            bets_text = f"Ставки {display_name}:\n"
            for bet in chat_manager.roulette_bets[chat_id][user_id]:
                display_value = "чёрное" if bet['value'] == "black" else "красное" if bet['value'] == "red" else bet['value']
                bets_text += f"{bet['amount']} на {display_value}\n"
            await update.message.reply_text(bets_text.strip())
        else:
            await update.message.reply_text("У вас нет активных ставок")
        return

    if text.upper() in ["УДВОИТЬ", "УДВОЙ", "DOUBLE", "D"]:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if chat_id in chat_manager.last_bet_amounts and user_id in chat_manager.last_bet_amounts[chat_id] and user_id in chat_manager.last_bet_types[chat_id]:
            last_amount = chat_manager.last_bet_amounts[chat_id][user_id]
            new_amount = last_amount * 2
            bet_type, bet_value, bet_description = chat_manager.last_bet_types[chat_id][user_id]

            user = UserManager.get_user(user_id)

            if user[3] >= new_amount:
                if new_amount < MIN_BET:
                    return
                else:
                    success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, new_amount)
                    if success:
                        user = UserManager.get_user(user_id)
                        if user[15]:
                            username = user[15]
                        elif user[1]:
                            username = user[1]
                        else:
                            username = user[2]
                        await update.message.reply_text(f"Ставка принята: <a href='tg://user?id={user_id}'>{username}</a> {new_amount} монет на {bet_description}", parse_mode='HTML')
            else:
                if user[15]:
                    display_name = user[15]
                elif user[1]:
                    display_name = user[1]
                else:
                    display_name = user[2]
                keyboard = [
                    [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"{display_name}, ставка не может превышать ваши средства\n\n",
                    reply_markup=reply_markup
                )
        else:
            await update.message.reply_text("Нет предыдущей ставки для удвоения!")
        return

    # ВА-БАНК командасы
    if text.upper().startswith("ВА-БАНК"):
        user_id = update.effective_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        total_amount = user[3]

        if total_amount < MIN_BET:
            keyboard = [
                [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Недостаточно монет для ставки!\n\n",
                reply_markup=reply_markup
            )
            return

        text_upper = text.upper().strip()
        
        if "-" in text_upper:
            import re
            range_match = re.search(r'ВА-БАНК\s*(\d+)-(\d+)', text_upper)
            if range_match:
                start_num = int(range_match.group(1))
                end_num = int(range_match.group(2))
                
                if 0 <= start_num <= 12 and 0 <= end_num <= 12:
                    numbers_count = abs(end_num - start_num) + 1
                    
                    amount_per_number = total_amount // numbers_count
                    
                    if amount_per_number < MIN_BET:
                        await update.message.reply_text(f"Минимальная ставка на каждое число: {MIN_BET}")
                        return
                    
                    successful_bets = 0
                    
                    for num in range(min(start_num, end_num), max(start_num, end_num) + 1):
                        success = await Games.handle_roulette_bet(update, context, "number", str(num), amount_per_number)
                        if success:
                            successful_bets += 1
                    
                    if successful_bets > 0:
                        if user[15]:
                            username = user[15]
                        elif user[1]:
                            username = user[1]
                        else:
                            username = user[2]
                        
                        await update.message.reply_text(
                            f"Cтавка принята: {username} {amount_per_number} на {min(start_num, end_num)}-{max(start_num, end_num)}"
                        )
                    return

        for num in range(0, 13):
            num_str = str(num)
            if text_upper == f"ВА-БАНК {num_str}" or text_upper == f"ВА-БАНК{num_str}":
                bet_type, bet_value, bet_description = "number", num_str, f"число {num_str}"
                success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, total_amount)
                if success:
                    if user[15]:
                        username = user[15]
                    elif user[1]:
                        username = user[1]
                    else:
                        username = user[2]
                    await update.message.reply_text(f"Cтавка принята: {username} {total_amount} на {num_str}")
                return

        if text_upper == "ВА-БАНК К" or text_upper == "ВА-БАНК КРАС":
            bet_type, bet_value, bet_description = "color", "red", "красное"
            success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, total_amount)
        elif text_upper == "ВА-БАНК Ч" or text_upper == "ВА-БАНК ЧЕР" or text_upper == "ВА-БАНК ЧЁР":
            bet_type, bet_value, bet_description = "color", "black", "чёрное"
            success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, total_amount)
        elif text_upper == "ВА-БАНК З" or text_upper == "ВА-БАНК ЗЕЛ" or text_upper == "ВА-БАНК 0":
            bet_type, bet_value, bet_description = "number", "0", "зеленое"
            success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, total_amount)
        else:
            words = text.split()
            if len(words) > 1:
                bet_word = words[1].lower()
                if bet_word in ["ч", "черное", "черный", "чёрное", "чёрный"]:
                    bet_type, bet_value, bet_description = "color", "black", "чёрное"
                elif bet_word in ["к", "красное", "красный"]:
                    bet_type, bet_value, bet_description = "color", "red", "красное"
                elif bet_word in ["з", "зеленое", "зеленый", "0"]:
                    bet_type, bet_value, bet_description = "number", "0", "зеленое"
                elif bet_word.isdigit() and 0 <= int(bet_word) <= 12:
                    num = int(bet_word)
                    bet_type, bet_value, bet_description = "number", str(num), f"число {num}"
                else:
                    await update.message.reply_text("Неверная команда! Используйте: Ва-банк <ставка> или Ва-банк <число-число>")
                    return

                success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, total_amount)
            else:
                await update.message.reply_text("Неверная команда! Используйте: Ва-банк <ставка>")
                return

        if success:
            if user[15]:
                username = user[15]
            elif user[1]:
                username = user[1]
            else:
                username = user[2]
            await update.message.reply_text(f"Cтавка принята: {username} {total_amount} на {bet_description}")
        return

    if text.upper() in ["ОТМЕНА", "ОТМЕНИТЬ", "CANCEL", "СТОПСТАВКА"]:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if chat_id in chat_manager.roulette_bets and user_id in chat_manager.roulette_bets[chat_id] and chat_manager.roulette_bets[chat_id][user_id]:
            total_amount = 0
            for bet in chat_manager.roulette_bets[chat_id][user_id]:
                total_amount += bet['amount']
                UserManager.update_balance(user_id, bet['amount'], f"Отмена ставки: +{bet['amount']}")

            chat_manager.roulette_bets[chat_id][user_id] = []
            await update.message.reply_text(f"Ставка отменена. Возвращено {total_amount} монет")
        else:
            await update.message.reply_text("Нет активных ставок для отмены")
        return

    if text.upper() in ["ПОВТОРИТЬ", "ПОВТОР", "REPEAT", "R"]:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if chat_id in chat_manager.last_bet_amounts and user_id in chat_manager.last_bet_amounts[chat_id] and user_id in chat_manager.last_bet_types[chat_id]:
            last_amount = chat_manager.last_bet_amounts[chat_id][user_id]
            bet_type, bet_value, bet_description = chat_manager.last_bet_types[chat_id][user_id]

            user = UserManager.get_user(user_id)
            if user[3] < last_amount:
                keyboard = [
                    [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Недостаточно монет!\n\n", reply_markup=reply_markup)
                return

            success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, last_amount)
            if success:
                user = UserManager.get_user(user_id)
                if user[15]:
                    username = user[15]
                elif user[1]:
                    username = user[1]
                else:
                    username = user[2]
                display_value = "чёрное" if bet_value == "black" else "красное" if bet_value == "red" else bet_value
                await update.message.reply_text(f"Ставка принята: {username} {last_amount} на {display_value}")
            else:
                keyboard = [
                    [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Недостаточно монет!\n\n", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Нет предыдущей ставки для повторения")
        return

    if text_lower.startswith("бандит"):
        words = text.split()
        
        if len(words) == 1:
            amount = MIN_BET
        elif len(words) == 2:
            try:
                amount = int(words[1])
                if amount < MIN_BET:
                    await update.message.reply_text(f"Минимальная ставка: {MIN_BET} монет!")
                    return
            except ValueError:
                amount = MIN_BET
        else:
            amount = MIN_BET

        if user[3] < amount:
            if user[15]:
                display_name = user[15]
            elif user[1]:
                display_name = user[1]
            else:
                display_name = user[2]
            
            keyboard = [[InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"{display_name}, недостаточно монет!\n\n",
                reply_markup=reply_markup
            )
            return

        UserManager.update_balance(user_id, -amount, f"Ставка в бандитку: -{amount}")
        asyncio.create_task(Games._banditka_logic_with_amount(update, context, amount))
        return

    words = text.split()
    if len(words) == 2:
        try:
            amount = int(words[0])
            if amount >= MIN_BET and words[1].lower() == "бандит":
                if user[3] < amount:
                    if user[15]:
                        display_name = user[15]
                    elif user[1]:
                        display_name = user[1]
                    else:
                        display_name = user[2]
                    
                    keyboard = [[InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        f"{display_name}, недостаточно монет!\n\n",
                        reply_markup=reply_markup
                    )
                    return

                UserManager.update_balance(user_id, -amount, f"Ставка в бандитку: -{amount}")
                asyncio.create_task(Games._banditka_logic_with_amount(update, context, amount))
                return
        except ValueError:
            pass

    game_handlers = {
        "РУЛЕТКА": Games.ruleka,
        "БАНДИТ": Games.banditka,
        "RULE": Games.ruleka,
        "ROULETTE": Games.ruleka,
    }

    handler = game_handlers.get(text.upper())
    if handler:
        await handler(update, context)
        return

    if len(words) >= 2:
        try:
            amount = int(words[0])

            if amount < MIN_BET:
                return

            if user[3] < amount:
                if user[15]:
                    display_name = user[15]
                elif user[1]:
                    display_name = user[1]
                else:
                    display_name = user[2]
                keyboard = [
                    [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"{display_name}, ставка не может превышать ваши средства\n\n",
                    reply_markup=reply_markup
                )
                return

            bet_part = ' '.join(words[1:]).lower()

            if "-" in bet_part:
                range_parts = bet_part.split("-")
                if len(range_parts) == 2:
                    try:
                        start_num = int(range_parts[0])
                        end_num = int(range_parts[1])
                        
                        if 0 <= start_num <= 12 and 0 <= end_num <= 12:
                            numbers_count = abs(end_num - start_num) + 1
                            
                            amount_per_number = amount // numbers_count
                            
                            if amount_per_number < MIN_BET:
                                await update.message.reply_text(f"Минимальная ставка на каждое число: {MIN_BET}")
                                return
                            
                            successful_bets = 0
                            
                            for num in range(min(start_num, end_num), max(start_num, end_num) + 1):
                                success = await Games.handle_roulette_bet(update, context, "number", str(num), amount_per_number)
                                if success:
                                    successful_bets += 1
                            
                            if successful_bets > 0:
                                user = UserManager.get_user(user_id)
                                if user[15]:
                                    username = user[15]
                                elif user[1]:
                                    username = user[1]
                                else:
                                    username = user[2]
                                
                                await update.message.reply_text(
                                    f"Cтавка принята: {username} {amount_per_number} на {min(start_num, end_num)}-{max(start_num, end_num)}"
                                )
                            return
                    except ValueError:
                        pass

            if bet_part.isdigit():
                num = int(bet_part)
                if 0 <= num <= 12:
                    success = await Games.handle_roulette_bet(update, context, "number", str(num), amount)
                    if success:
                        user = UserManager.get_user(user_id)
                        if user[15]:
                            username = user[15]
                        elif user[1]:
                            username = user[1]
                        else:
                            username = user[2]
                        await update.message.reply_text(f"Cтавка принята: {username} {amount} на {num}")
                    return

            if bet_part in ["ч", "черное", "черный", "чёрное", "чёрный"]:
                success = await Games.handle_roulette_bet(update, context, "color", "black", amount)
                if success:
                    user = UserManager.get_user(user_id)
                    if user[15]:
                        username = user[15]
                    elif user[1]:
                        username = user[1]
                    else:
                        username = user[2]
                    await update.message.reply_text(f"Cтавка принята: {username} {amount} на чёрное")
                return
            elif bet_part in ["к", "красное", "красный"]:
                success = await Games.handle_roulette_bet(update, context, "color", "red", amount)
                if success:
                    user = UserManager.get_user(user_id)
                    if user[15]:
                        username = user[15]
                    elif user[1]:
                        username = user[1]
                    else:
                        username = user[2]
                    await update.message.reply_text(f"Cтавка принята: {username} {amount} на красное")
                return
            elif bet_part in ["з", "зеленое", "зеленый", "zero", "зеро"]:
                success = await Games.handle_roulette_bet(update, context, "number", "0", amount)
                if success:
                    user = UserManager.get_user(user_id)
                    if user[15]:
                        username = user[15]
                    elif user[1]:
                        username = user[1]
                    else:
                        username = user[2]
                    await update.message.reply_text(f"Cтавка принята: {username} {amount} на зелёное")
                return

        except ValueError:
            pass

    if "+" in text:
        try:
            amount = int(text.replace("+", "").strip())
            if amount <= 0:
                await update.message.reply_text("Неверная сумма")
                return

            if user[3] < amount:
                await update.message.reply_text("Недостаточно монет")
                return

            can_transfer, message = UserManager.can_make_transfer(user_id, amount)
            if not can_transfer:
                await update.message.reply_text(f"{message}")
                return

            if update.message.reply_to_message:
                to_user_id = update.message.reply_to_message.from_user.id
                to_user = UserManager.get_user(to_user_id)

                if to_user:
                    to_display_name = to_user[15] if len(to_user) > 15 and to_user[15] else (to_user[1] if to_user[1] else to_user[2])
                    from_display_name = user[15] if len(user) > 15 and user[15] else (user[1] if user[1] else user[2])

                    if from_display_name:
                        from_name = from_display_name
                    elif user[1]:
                        from_name = user[1]
                    else:
                        from_name = user[2]

                    if to_display_name:
                        to_name = to_display_name
                    elif to_user[1]:
                        to_name = to_user[1]
                    else:
                        to_name = to_user[2]

                    UserManager.update_balance(user_id, -amount, f"Перевод игроку {to_display_name}: -{amount}")
                    UserManager.update_balance(to_user_id, amount, f"Перевод от игрока {from_display_name}: +{amount}")

                    UserManager.update_transfer_usage(user_id, amount)

                    await update.message.reply_text(f"<a href='tg://user?id={user_id}'>{from_name}</a> перевёл {amount}🪙 пользователю <a href='tg://user?id={to_user_id}'>{to_name}</a>", parse_mode='HTML')
                else:
                    await update.message.reply_text("Пользователь не найден")
            else:
                await update.message.reply_text("Ответьте на сообщение пользователя")

        except ValueError:
            return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if UserManager.is_blocked(user_id):
        return

    username = update.effective_user.username
    first_name = update.effective_user.first_name

    UserManager.create_user(user_id, username, first_name, None)

    keyboard = [
        [
            InlineKeyboardButton("💰 Баланс", callback_data="menu_balance"),
            InlineKeyboardButton("📊 Профиль", callback_data="menu_profile")
        ],
        [
            InlineKeyboardButton("🎰 Рулетка", callback_data="menu_roulette"),
            InlineKeyboardButton("🎴 Бандит", callback_data="menu_bandit")
        ],
        [
            InlineKeyboardButton("🏆 Топ", callback_data="menu_top"),
            InlineKeyboardButton("📈 История", callback_data="menu_history")
        ],
        [
            InlineKeyboardButton("🔗 Каналы", callback_data="menu_links"),
            InlineKeyboardButton("💎 Донат", callback_data="menu_donate")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 Привет, {first_name}!\n"
        f"🎮 Добро пожаловать в бота!\n\n"
        f"👇 Используйте кнопки ниже для навигации:"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = UserManager.get_user(user_id)

    if not user:
        return

    data = query.data

    if data == "menu_balance":
        if user[15]:
            display_name = user[15]
        elif user[1]:
            display_name = user[1]
        else:
            display_name = user[2]

        await query.message.reply_text(f"{display_name}\nМонеты: {user[3]}🪙")

    elif data == "menu_profile":
        if user[15]:
            display_name = user[15]
        elif user[1]:
            display_name = user[1]
        else:
            display_name = user[2]

        profile_text = (
            f"{display_name}: ♠️♥️\n"
            f"ID: {user_id}\n"
            f"Монеты: {user[3]}🪙\n"
            f"Выиграно: {user[8]}\n"
            f"Проиграно: {user[7]}\n"
            f"Макс. выигрыш: {user[10]}\n"
            f"Макс. ставка: {user[9]}"
        )

        await query.message.reply_text(profile_text)

    elif data == "menu_roulette":
        keyboard = [
            [
                InlineKeyboardButton("1-3", callback_data="bet_1_3"),
                InlineKeyboardButton("4-6", callback_data="bet_4_6"),
                InlineKeyboardButton("7-9", callback_data="bet_7_9"),
                InlineKeyboardButton("10-12", callback_data="bet_10_12")
            ],
            [
                InlineKeyboardButton("1к🔴", callback_data="bet_red"),
                InlineKeyboardButton("1к⚫️", callback_data="bet_black"),
                InlineKeyboardButton("1к💚", callback_data="bet_zero")
            ],
            [
                InlineKeyboardButton("Повторить", callback_data="repeat_bet"),
                InlineKeyboardButton("Удвоить", callback_data="double_bet"),
                InlineKeyboardButton("Крутить", callback_data="spin_roulette")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        roulette_layout = (
            "Минирулетка\n"
            "Угадайте число из:\n"
            "0💚\n"
            "1🔴 2⚫️ 3🔴 4⚫️ 5🔴 6⚫️\n"
            "7🔴 8⚫️ 9🔴10⚫️11🔴12⚫️\n"
            "Ставки можно текстом\n"
            "1000 на красное | 5000 на 12"
        )

        await query.message.reply_text(roulette_layout, reply_markup=reply_markup)

    elif data == "menu_bandit":
        user_id = query.from_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        if user[3] < MIN_BET:
            keyboard = [[InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Недостаточно монет\n\n", reply_markup=reply_markup)
            return

        amount = MIN_BET
        UserManager.update_balance(user_id, -amount, f"Ставка в бандитку: -{amount}")

        asyncio.create_task(Games._banditka_logic_with_amount(update, context, amount))

    elif data == "menu_top":
        current_user_id = query.from_user.id
        current_user = UserManager.get_user(current_user_id)
        user_position = UserManager.get_user_position_by_balance(current_user_id)

        top_users = UserManager.get_global_top_users(10)

        if not top_users:
            top_text = "[ТОП 10 БОГАТЫХ]\n\nТоп пуст!\n\n"
            telegram_name = current_user[2] if current_user and current_user[2] else query.from_user.first_name
            top_text += f"{telegram_name}: {user_position} место"
            await query.message.reply_text(top_text)
            return

        top_text = "[ТОП 10 БОГАТЫХ]\n\n"

        for i, (user_id, display_name, username, first_name, balance) in enumerate(top_users, 1):
            if display_name:
                name = display_name
            elif username:
                name = username
            else:
                name = first_name

            top_text += f"{i}. {name} [{balance}]\n"

        top_text += "¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯\n"
        telegram_name = current_user[2] if current_user and current_user[2] else query.from_user.first_name
        top_text += f"{telegram_name}: {user_position} место"

        await query.message.reply_text(top_text)

    elif data == "menu_history":
        user_id = query.from_user.id
        user = UserManager.get_user(user_id)

        if not user:
            return

        transactions = UserManager.get_transaction_history(user_id, 10)

        if not transactions:
            await query.message.reply_text("История транзакций пуста!")
            return

        history_text = "История транзакций\n\n"

        for date_str, amount, trans_type, description in transactions:
            time_str = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime("%H:%M:%S")

            if amount > 0:
                if "выигрыш" in description.lower():
                    history_text += f"[{time_str}] выигрыш в рулетку: +{amount}\n"
                elif "перевод от игрока" in description.lower():
                    player_name = description.split("перевод от игрока ")[-1]
                    history_text += f"[{time_str}] перевод от игрока {player_name}: +{amount}\n"
                elif "бандит" in description.lower():
                    history_text += f"[{time_str}] выигрыш в бандита: +{amount}\n"
                elif "донат" in description.lower():
                    history_text += f"[{time_str}] донат: +{amount}\n"
                else:
                    history_text += f"[{time_str}] +{amount}\n"
            else:
                if "проигрыш" in description.lower():
                    if "рулетк" in description.lower():
                        history_text += f"[{time_str}] проигрыш в рулетку: {amount}\n"
                    elif "бандит" in description.lower():
                        history_text += f"[{time_str}] проигрыш в бандита: {amount}\n"
                    else:
                        history_text += f"[{time_str}] проигрыш: {amount}\n"
                elif "ставка" in description.lower():
                    history_text += f"[{time_str}] ставка: {amount}\n"
                elif "перевод игроку" in description.lower():
                    player_name = description.split("перевод игроку ")[-1]
                    history_text += f"[{time_str}] перевод игроку {player_name}: {amount}\n"
                else:
                    history_text += f"[{time_str}] {amount}\n"

        await query.message.reply_text(history_text)

    elif data == "menu_links":
        links_text = "🔗 КАНАЛЫ:\n" + "\n".join(CHANNELS)
        await query.message.reply_text(links_text)

    elif data == "menu_donate":
        user = UserManager.get_user(user_id)

        if not user:
            return

        display_name = user[15] if len(user) > 15 and user[15] else (user[1] if user[1] else user[2])

        keyboard = [
            [InlineKeyboardButton("Пополнить баланс", url=DONATE_LINK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        donate_text = f"💰 ДОНАТ ДЛЯ {display_name}\n\n🆔 Ваш ID: {user_id}"
        await query.message.reply_text(donate_text, reply_markup=reply_markup)

async def reset_daily_limits_job(context: ContextTypes.DEFAULT_TYPE):
    UserManager.reset_daily_limits()
    logger.info("Лимиты сброшены")

async def check_muted_users_job(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, mute_until FROM users WHERE is_muted = 1 AND mute_until IS NOT NULL")
    muted_users = cursor.fetchall()

    now = datetime.now()

    for user_id, mute_until_str in muted_users:
        if mute_until_str:
            try:
                mute_until = datetime.strptime(mute_until_str, "%Y-%m-%d %H:%M:%S")
                if now > mute_until:
                    cursor.execute("UPDATE users SET is_muted = 0, mute_until = NULL, mute_by = NULL WHERE user_id = ?", (user_id,))
            except:
                pass

    conn.commit()
    conn.close()

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("menu_"):
        await handle_menu_callback(update, context)
        return

    if data == "spin_roulette":
        chat_id = query.message.chat_id
        await Games.spin_roulette_logic(update, context, chat_id)
    elif data.startswith("bet_"):
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        if data == "bet_red":
            bet_type, bet_value = "color", "red"
        elif data == "bet_black":
            bet_type, bet_value = "color", "black"
        elif data == "bet_zero":
            bet_type, bet_value = "number", "0"
        elif data == "bet_1_3":
            bet_type, bet_value = "range", "1_3"
        elif data == "bet_4_6":
            bet_type, bet_value = "range", "4_6"
        elif data == "bet_7_9":
            bet_type, bet_value = "range", "7_9"
        elif data == "bet_10_12":
            bet_type, bet_value = "range", "10_12"
        else:
            return

        await query.message.reply_text(f"Введите сумму ставки (мин. {MIN_BET}):")

        context.user_data['pending_bet'] = {
            'type': bet_type,
            'value': bet_value,
            'chat_id': chat_id
        }
    elif data == "repeat_bet":
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        if chat_id in chat_manager.last_bet_amounts and user_id in chat_manager.last_bet_amounts[chat_id] and user_id in chat_manager.last_bet_types[chat_id]:
            last_amount = chat_manager.last_bet_amounts[chat_id][user_id]
            bet_type, bet_value, bet_description = chat_manager.last_bet_types[chat_id][user_id]

            user = UserManager.get_user(user_id)
            if user and user[3] >= last_amount:
                success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, last_amount)
                if success:
                    await query.message.reply_text(f"Ставка повторена: {last_amount} монет")
                else:
                    await query.message.reply_text("Недостаточно монет!")
            else:
                await query.message.reply_text("Недостаточно монет!")
        else:
            await query.message.reply_text("Нет предыдущей ставки для повторения")
    elif data == "double_bet":
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        if chat_id in chat_manager.last_bet_amounts and user_id in chat_manager.last_bet_amounts[chat_id] and user_id in chat_manager.last_bet_types[chat_id]:
            last_amount = chat_manager.last_bet_amounts[chat_id][user_id]
            new_amount = last_amount * 2
            bet_type, bet_value, bet_description = chat_manager.last_bet_types[chat_id][user_id]

            user = UserManager.get_user(user_id)
            if user and user[3] >= new_amount:
                success = await Games.handle_roulette_bet(update, context, bet_type, bet_value, new_amount)
                if success:
                    await query.message.reply_text(f"Ставка удвоена: {new_amount} монет")
                else:
                    await query.message.reply_text("Недостаточно монет!")
            else:
                await query.message.reply_text("Недостаточно монет!")
        else:
            await query.message.reply_text("Нет предыдущей ставки для удвоения")

def main():
    # Жаңы Application түзүү
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(reset_daily_limits_job, interval=43200, first=10)
            job_queue.run_repeating(check_muted_users_job, interval=300, first=10)
    except Exception as e:
        logger.error(f"JobQueue иштөөдө ката: {e}")

    # Командаларды кошуу
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", handle_id_command))
    app.add_handler(CommandHandler("setname", handle_setname_command))
    app.add_handler(CommandHandler("addcoins", handle_addcoins_command))
    app.add_handler(CommandHandler("removecoins", handle_removecoins_command))
    app.add_handler(CommandHandler("setlimit", handle_setlimit_command))
    app.add_handler(CommandHandler("limits", handle_limits_command))
    app.add_handler(CommandHandler("resetbalances", handle_resetbalances_command))
    app.add_handler(CommandHandler("reducebalances", handle_reducebalances_command))
    app.add_handler(CommandHandler("ruleka", Games.ruleka))
    app.add_handler(CommandHandler("roulette", Games.ruleka))
    app.add_handler(CommandHandler("banditka", Games.banditka))
    app.add_handler(CommandHandler("bandit", Games.banditka))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_messages
    ))

    print("🤖 Бот запущен!")
    print("✅ '1000 1-12' → Cтавка принята: Имя 77 на 1-12")
    print("✅ 'Ва-банк 0-5' → Cтавка принята: Имя 16666 на 0-5")
    print("✅ Результат болгондо: Рулетка: 1🔴")
    print("✅ 7 кнопка менен меню иштейт")

    # Жаңы polling метод
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)def main():
    # Жаңы Application түзүү
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(reset_daily_limits_job, interval=43200, first=10)
            job_queue.run_repeating(check_muted_users_job, interval=300, first=10)
    except Exception as e:
        logger.error(f"JobQueue иштөөдө ката: {e}")

    # Командаларды кошуу
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", handle_id_command))
    app.add_handler(CommandHandler("setname", handle_setname_command))
    app.add_handler(CommandHandler("addcoins", handle_addcoins_command))
    app.add_handler(CommandHandler("removecoins", handle_removecoins_command))
    app.add_handler(CommandHandler("setlimit", handle_setlimit_command))
    app.add_handler(CommandHandler("limits", handle_limits_command))
    app.add_handler(CommandHandler("resetbalances", handle_resetbalances_command))
    app.add_handler(CommandHandler("reducebalances", handle_reducebalances_command))
    app.add_handler(CommandHandler("ruleka", Games.ruleka))
    app.add_handler(CommandHandler("roulette", Games.ruleka))
    app.add_handler(CommandHandler("banditka", Games.banditka))
    app.add_handler(CommandHandler("bandit", Games.banditka))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_messages
    ))

    print("🤖 Бот запущен!")
    print("✅ '1000 1-12' → Cтавка принята: Имя 77 на 1-12")
    print("✅ 'Ва-банк 0-5' → Cтавка принята: Имя 16666 на 0-5")
    print("✅ Результат болгондо: Рулетка: 1🔴")
    print("✅ 7 кнопка менен меню иштейт")

    # Жаңы polling метод
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)def main():
    # Жаңы Application түзүү
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(reset_daily_limits_job, interval=43200, first=10)
            job_queue.run_repeating(check_muted_users_job, interval=300, first=10)
    except Exception as e:
        logger.error(f"JobQueue иштөөдө ката: {e}")

    # Командаларды кошуу
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", handle_id_command))
    app.add_handler(CommandHandler("setname", handle_setname_command))
    app.add_handler(CommandHandler("addcoins", handle_addcoins_command))
    app.add_handler(CommandHandler("removecoins", handle_removecoins_command))
    app.add_handler(CommandHandler("setlimit", handle_setlimit_command))
    app.add_handler(CommandHandler("limits", handle_limits_command))
    app.add_handler(CommandHandler("resetbalances", handle_resetbalances_command))
    app.add_handler(CommandHandler("reducebalances", handle_reducebalances_command))
    app.add_handler(CommandHandler("ruleka", Games.ruleka))
    app.add_handler(CommandHandler("roulette", Games.ruleka))
    app.add_handler(CommandHandler("banditka", Games.banditka))
    app.add_handler(CommandHandler("bandit", Games.banditka))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_messages
    ))

    print("🤖 Бот запущен!")
    print("✅ '1000 1-12' → Cтавка принята: Имя 77 на 1-12")
    print("✅ 'Ва-банк 0-5' → Cтавка принята: Имя 16666 на 0-5")
    print("✅ Результат болгондо: Рулетка: 1🔴")
    print("✅ 7 кнопка менен меню иштейт")

    # Жаңы polling метод
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
if __name__ == "__main__":
    main()
