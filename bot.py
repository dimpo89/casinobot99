import os
import sys
import asyncio
import logging
import random
import string
import json
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web

# Загружаем переменные окружения
load_dotenv()

# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================
# ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================
print("\n" + "="*60)
print("🔍 ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ")
print("="*60)

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS_STR = os.getenv('ADMIN_IDS')

print(f"BOT_TOKEN exists: {'✅' if BOT_TOKEN else '❌'}")
if BOT_TOKEN:
    print(f"BOT_TOKEN length: {len(BOT_TOKEN)}")
    print(f"BOT_TOKEN starts with: {BOT_TOKEN[:10]}...")
else:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)

print(f"ADMIN_IDS string: {ADMIN_IDS_STR if ADMIN_IDS_STR else '❌ не найден'}")

ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',') if id.strip()]
        print(f"✅ ADMIN_IDS загружены: {ADMIN_IDS}")
    except Exception as e:
        print(f"❌ Ошибка парсинга ADMIN_IDS: {e}")
else:
    print("⚠️ ADMIN_IDS не заданы, админ-панель будет недоступна")

DATABASE_PATH = os.getenv('DATABASE_PATH', 'casino_bot.db')
RTP_DISPLAY = 98.2
RTP_ACTUAL = 76.82
JACKPOT_PERCENT = 0.05
MAX_BET = 1000000
MIN_BET = 1

print("="*60 + "\n")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================
# ЯЗЫКИ
# ============================================
LANGUAGES = {
    'ru': {
        'balance': '💰 Баланс',
        'games': '🎮 Игры',
        'settings': '⚙️ Настройки',
        'language': 'Язык',
        'vip_level': 'VIP уровень',
        'experience': 'Опыт',
        'win': 'Выигрыш',
        'loss': 'Проигрыш',
        'bet': 'Ставка',
        'jackpot': 'Джекпот',
        'not_enough': '❌ Недостаточно средств',
        'user_not_found': '❌ Пользователь не найден',
        'welcome': '🎰 Добро пожаловать в Mega Casino!',
        'rtp': 'RTP',
        'free_spins': '🎁 Фриспины!',
        'bonus_game': '🎮 Бонусная игра!',
        'error': '❌ Ошибка. Попробуйте снова.'
    },
    'en': {
        'balance': '💰 Balance',
        'games': '🎮 Games',
        'settings': '⚙️ Settings',
        'language': 'Language',
        'vip_level': 'VIP level',
        'experience': 'Experience',
        'win': 'Win',
        'loss': 'Loss',
        'bet': 'Bet',
        'jackpot': 'Jackpot',
        'not_enough': '❌ Insufficient funds',
        'user_not_found': '❌ User not found',
        'welcome': '🎰 Welcome to Mega Casino!',
        'rtp': 'RTP',
        'free_spins': '🎁 Free spins!',
        'bonus_game': '🎮 Bonus game!',
        'error': '❌ Error. Try again.'
    }
}

def get_text(key: str, lang: str = 'ru') -> str:
    return LANGUAGES.get(lang, LANGUAGES['ru']).get(key, key)

# ============================================
# СОСТОЯНИЯ FSM
# ============================================
class BetStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_withdrawal_amount = State()
    waiting_for_withdrawal_address = State()
    waiting_for_admin_action = State()
    waiting_for_rtp_change = State()
    waiting_for_bonus_code = State()
    waiting_for_bonus_code_amount = State()
    waiting_for_bonus_code_uses = State()
    waiting_for_bonus_code_expiry = State()
    waiting_for_user_id = State()
    waiting_for_balance_amount = State()
    waiting_for_broadcast_message = State()
    waiting_for_tournament_name = State()
    waiting_for_tournament_prize = State()
    waiting_for_tournament_duration = State()
    waiting_for_tournament_min_bet = State()
    waiting_for_deposit_amount = State()
    waiting_for_slot_edit = State()
    waiting_for_game_setting = State()

# ============================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ============================================
async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance INTEGER DEFAULT 0,
                total_bets INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,
                biggest_win INTEGER DEFAULT 0,
                biggest_loss INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                vip_level INTEGER DEFAULT 0,
                experience INTEGER DEFAULT 0,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT DEFAULT 'ru',
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        ''')
        
        # Таблица транзакций
        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                status TEXT,
                description TEXT,
                telegram_payment_id TEXT,
                wallet_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        # Таблица игр
        await db.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                user_id INTEGER,
                game_type TEXT,
                bet_amount INTEGER,
                win_amount INTEGER,
                profit INTEGER,
                game_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек RTP
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rtp_settings (
                game_type TEXT PRIMARY KEY,
                base_rtp REAL DEFAULT 76.82,
                current_rtp REAL DEFAULT 76.82,
                min_rtp REAL DEFAULT 70.0,
                max_rtp REAL DEFAULT 85.0,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_by INTEGER
            )
        ''')
        
        # Таблица джекпота
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jackpot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                amount INTEGER DEFAULT 0,
                last_win TIMESTAMP,
                last_winner INTEGER
            )
        ''')
        await db.execute('INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 1000)')
        
        # Таблица бонусных кодов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus_codes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                expires_at TIMESTAMP,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица использованных бонусов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица турниров
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tournaments (
                tournament_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                prize_pool INTEGER,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                game_type TEXT,
                min_bet INTEGER,
                status TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица участников турниров
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tournament_participants (
                tournament_id INTEGER,
                user_id INTEGER,
                score INTEGER DEFAULT 0,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tournament_id, user_id)
            )
        ''')
        
        # Таблица ежедневных наград
        await db.execute('''
            CREATE TABLE IF NOT EXISTS daily_rewards (
                user_id INTEGER,
                last_claim TIMESTAMP,
                streak INTEGER DEFAULT 0,
                PRIMARY KEY (user_id)
            )
        ''')
        
        # Таблица настроек
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Настройки по умолчанию
        default_settings = [
            ('faucet_amount', '10'),
            ('faucet_cooldown', '3600'),
            ('min_withdrawal', '100'),
            ('withdrawal_fee', '0'),
            ('welcome_bonus', '100'),
            ('referral_bonus', '50'),
            ('maintenance_mode', 'false')
        ]
        
        for key, value in default_settings:
            await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        # Таблица настроек игр (вероятности, множители)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS game_settings (
                game_type TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL
            )
        ''')

        # Вставляем настройки по умолчанию для слотов, если их нет
        default_slot_settings = {
            "symbols": ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐", "🎰"],
            "weights": [100, 80, 60, 40, 20, 10, 5, 2],
            "values": [2, 3, 4, 5, 8, 12, 20, 30],
            "wild": "⭐",
            "scatter": "🎰",
            "free_spins_mult": 10,
            "bonus_game_prob": 0.01,
            "rtp": 76.82
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "slot"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('slot', json.dumps(default_slot_settings)))

        # Настройки для нового слота "Звери"
        animal_slot_default = {
            "symbols": ["🐶", "🐱", "🦊", "🐼", "🐨", "🦁", "🐯", "🐸"],
            "weights": [100, 80, 60, 40, 20, 10, 5, 2],
            "values": [2, 3, 4, 5, 8, 12, 20, 30],
            "wild": "🦁",
            "scatter": "🐸",
            "free_spins_mult": 10,
            "bonus_game_prob": 0.02,
            "rtp": 76.82
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "animalslot"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('animalslot', json.dumps(animal_slot_default)))

        await db.commit()
    logger.info("✅ База данных инициализирована")

# ============================================
# КЛАСС ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ (ПОЛНЫЙ)
# ============================================
class Database:
    @staticmethod
    async def get_user(user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def get_user_by_username(username: str) -> Optional[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users WHERE username = ?', (username.replace('@', ''),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def create_user(user_id: int, username: str = None, first_name: str = None,
                         last_name: str = None, referred_by: int = None):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            exists = await cursor.fetchone()
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "welcome_bonus"')
            welcome_bonus = int((await cursor.fetchone())[0])
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "referral_bonus"')
            referral_bonus = int((await cursor.fetchone())[0])
            
            if exists:
                await db.execute('''
                    UPDATE users SET 
                        username = ?,
                        first_name = ?,
                        last_name = ?,
                        last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (username, first_name, last_name, user_id))
                logger.info(f"✅ Пользователь {user_id} обновлен")
                bonus = 0
            else:
                referral_code = Database.generate_referral_code()
                await db.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, referral_code, referred_by, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, referral_code, referred_by, welcome_bonus))
                logger.info(f"✅ Новый пользователь {user_id} создан с балансом {welcome_bonus} ⭐")
                bonus = welcome_bonus
                
                if referred_by:
                    await db.execute('''
                        UPDATE users SET balance = balance + ? WHERE user_id = ?
                    ''', (referral_bonus, referred_by))
                    await db.execute('''
                        INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (str(uuid.uuid4()), referred_by, referral_bonus, 'referral', 'completed', f'Реферальный бонус за пользователя {user_id}'))
                    logger.info(f"👥 Реферальный бонус {referral_bonus} ⭐ начислен пользователю {referred_by}")
            
            await db.commit()
            return bonus

    @staticmethod
    def generate_referral_code(length: int = 8) -> str:
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))

    @staticmethod
    async def update_balance(user_id: int, amount: int, description: str = "") -> bool:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = await cursor.fetchone()
            if not result:
                return False
            current_balance = result[0]
            new_balance = current_balance + amount
            if new_balance < 0:
                return False
            await db.execute('UPDATE users SET balance = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?',
                           (new_balance, user_id))
            if description:
                tx_type = 'admin' if amount > 0 else 'admin_withdraw'
                await db.execute('''
                    INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), user_id, amount, tx_type, 'completed', description))
            await db.commit()
            logger.info(f"💰 Баланс пользователя {user_id} изменен на {amount} (новый баланс: {new_balance})")
            return True

    @staticmethod
    async def add_game_history(user_id: int, game_type: str, bet_amount: int,
                              win_amount: int, game_data: Dict):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            game_id = str(uuid.uuid4())
            profit = win_amount - bet_amount
            await db.execute('''
                INSERT INTO games (game_id, user_id, game_type, bet_amount, win_amount, profit, game_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, user_id, game_type, bet_amount, win_amount, profit, json.dumps(game_data)))
            await db.execute('''
                UPDATE users SET 
                    total_bets = total_bets + 1,
                    total_wins = total_wins + ?,
                    total_losses = total_losses + ?,
                    biggest_win = MAX(biggest_win, ?),
                    biggest_loss = MIN(biggest_loss, ?),
                    experience = experience + 10
                WHERE user_id = ?
            ''', (1 if win_amount > 0 else 0,
                  1 if win_amount == 0 else 0,
                  win_amount,
                  bet_amount if win_amount == 0 else 0,
                  user_id))
            await db.commit()
            await Database.update_tournament_scores(user_id, game_type, bet_amount, win_amount)

    @staticmethod
    async def get_rtp_settings(game_type: str = None) -> Dict:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            if game_type:
                cursor = await db.execute('SELECT * FROM rtp_settings WHERE game_type = ?', (game_type,))
                row = await cursor.fetchone()
                return dict(row) if row else {'game_type': game_type, 'current_rtp': RTP_ACTUAL}
            else:
                cursor = await db.execute('SELECT * FROM rtp_settings')
                rows = await cursor.fetchall()
                return {row['game_type']: dict(row) for row in rows}

    @staticmethod
    async def update_rtp_settings(game_type: str, new_rtp: float, admin_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO rtp_settings (game_type, base_rtp, current_rtp, modified_by, last_modified)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (game_type, RTP_ACTUAL, new_rtp, admin_id))
            await db.commit()
            logger.info(f"🎮 RTP для {game_type} изменен на {new_rtp}% админом {admin_id}")

    @staticmethod
    async def update_jackpot(amount: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('UPDATE jackpot SET amount = amount + ? WHERE id = 1', (amount,))
            await db.commit()

    @staticmethod
    async def get_jackpot() -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT amount FROM jackpot WHERE id = 1')
            result = await cursor.fetchone()
            return result[0] if result else 1000

    @staticmethod
    async def reset_jackpot(winner_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE jackpot SET 
                    amount = 1000,
                    last_win = CURRENT_TIMESTAMP,
                    last_winner = ?
                WHERE id = 1
            ''', (winner_id,))
            await db.commit()
            logger.info(f"💰 Джекпот сброшен победителем {winner_id}")

    @staticmethod
    async def get_all_users(limit: int = 100, offset: int = 0) -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT user_id, username, balance, total_bets, total_wins,
                       vip_level, join_date, is_banned
                FROM users
                ORDER BY join_date DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def get_users_count() -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            return (await cursor.fetchone())[0]

    @staticmethod
    async def get_top_players(limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT user_id, username, balance, total_wins, total_bets,
                       CAST(total_wins AS FLOAT) / total_bets * 100 as win_rate
                FROM users
                WHERE total_bets > 0
                ORDER BY total_wins DESC
                LIMIT ?
            ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def get_top_players_by_balance(limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT user_id, username, balance, vip_level
                FROM users
                ORDER BY balance DESC
                LIMIT ?
            ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def get_transactions(user_id: int = None, limit: int = 20) -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            if user_id:
                cursor = await db.execute('''
                    SELECT * FROM transactions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (user_id, limit))
            else:
                cursor = await db.execute('''
                    SELECT * FROM transactions
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def add_transaction(user_id: int, amount: int, tx_type: str,
                              status: str, description: str, wallet_address: str = None) -> str:
        transaction_id = str(uuid.uuid4())
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT INTO transactions (transaction_id, user_id, amount, type, status, description, wallet_address)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, user_id, amount, tx_type, status, description, wallet_address))
            await db.commit()
        return transaction_id

    @staticmethod
    async def update_transaction_status(transaction_id: str, status: str):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE transactions SET status = ?, completed_at = CURRENT_TIMESTAMP
                WHERE transaction_id = ?
            ''', (status, transaction_id))
            await db.commit()

    @staticmethod
    async def create_bonus_code(code: str, amount: int, max_uses: int,
                                 expires_at: datetime, created_by: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT INTO bonus_codes (code, amount, max_uses, expires_at, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, amount, max_uses, expires_at, created_by))
            await db.commit()
            logger.info(f"🎁 Бонус код {code} создан админом {created_by}")

    @staticmethod
    async def get_bonus_codes() -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM bonus_codes
                ORDER BY created_at DESC
            ''')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def use_bonus_code(code: str, user_id: int) -> Optional[int]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT * FROM bonus_codes
                WHERE code = ? AND used_count < max_uses
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ''', (code,))
            row = await cursor.fetchone()
            if not row:
                return None
            cursor = await db.execute('''
                SELECT * FROM bonus_uses WHERE code = ? AND user_id = ?
            ''', (code, user_id))
            if await cursor.fetchone():
                return -1
            amount = row[1]
            await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            await db.execute('UPDATE bonus_codes SET used_count = used_count + 1 WHERE code = ?', (code,))
            await db.execute('INSERT INTO bonus_uses (code, user_id) VALUES (?, ?)', (code, user_id))
            await db.execute('''
                INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(uuid.uuid4()), user_id, amount, 'bonus', 'completed', f'Бонус код: {code}'))
            await db.commit()
            return amount

    @staticmethod
    async def create_tournament(name: str, prize_pool: int, game_type: str,
                                 duration_hours: int, min_bet: int, created_by: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            start_date = datetime.now()
            end_date = start_date + timedelta(hours=duration_hours)
            cursor = await db.execute('''
                INSERT INTO tournaments (name, prize_pool, start_date, end_date, game_type, min_bet, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                RETURNING tournament_id
            ''', (name, prize_pool, start_date, end_date, game_type, min_bet, created_by))
            row = await cursor.fetchone()
            tournament_id = row[0] if row else None
            await db.commit()
            logger.info(f"🏆 Турнир {name} создан админом {created_by}")
            return tournament_id

    @staticmethod
    async def get_active_tournaments() -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            now = datetime.now()
            cursor = await db.execute('''
                SELECT * FROM tournaments
                WHERE status = 'active' AND end_date > ?
                ORDER BY prize_pool DESC
            ''', (now,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def get_all_tournaments() -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM tournaments
                ORDER BY created_at DESC
            ''')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def update_tournament_scores(user_id: int, game_type: str, bet: int, win: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            now = datetime.now()
            cursor = await db.execute('''
                SELECT tournament_id FROM tournaments
                WHERE game_type = ? AND status = 'active'
                AND start_date <= ? AND end_date >= ?
            ''', (game_type, now, now))
            tournaments = await cursor.fetchall()
            for (tournament_id,) in tournaments:
                score = win * 10 + bet
                await db.execute('''
                    INSERT INTO tournament_participants (tournament_id, user_id, score)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tournament_id, user_id)
                    DO UPDATE SET score = score + ?, last_update = CURRENT_TIMESTAMP
                ''', (tournament_id, user_id, score, score))
            await db.commit()

    @staticmethod
    async def get_tournament_leaderboard(tournament_id: int, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT tp.user_id, u.username, tp.score
                FROM tournament_participants tp
                JOIN users u ON tp.user_id = u.user_id
                WHERE tp.tournament_id = ?
                ORDER BY tp.score DESC
                LIMIT ?
            ''', (tournament_id, limit))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    async def end_tournament(tournament_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT * FROM tournaments WHERE tournament_id = ?', (tournament_id,))
            tournament = await cursor.fetchone()
            if not tournament:
                return None
            leaderboard = await Database.get_tournament_leaderboard(tournament_id, 3)
            if leaderboard:
                prizes = [0.5, 0.3, 0.2]
                for i, player in enumerate(leaderboard):
                    if i < len(prizes):
                        prize = int(tournament[2] * prizes[i])
                        await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?',
                                       (prize, player['user_id']))
                        await db.execute('''
                            INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (str(uuid.uuid4()), player['user_id'], prize, 'tournament', 'completed',
                              f'Приз за турнир #{tournament_id}: {tournament[1]}'))
            await db.execute('UPDATE tournaments SET status = "ended" WHERE tournament_id = ?', (tournament_id,))
            await db.commit()
            logger.info(f"🏆 Турнир #{tournament_id} завершен")
            return leaderboard

    @staticmethod
    async def check_expired_tournaments():
        async with aiosqlite.connect(DATABASE_PATH) as db:
            now = datetime.now()
            cursor = await db.execute('''
                SELECT tournament_id FROM tournaments
                WHERE status = 'active' AND end_date < ?
            ''', (now,))
            tournaments = await cursor.fetchall()
            for (tournament_id,) in tournaments:
                await Database.end_tournament(tournament_id)

    @staticmethod
    async def get_setting(key: str) -> str:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = await cursor.fetchone()
            return result[0] if result else ''

    @staticmethod
    async def update_setting(key: str, value: str):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key))
            await db.commit()

    @staticmethod
    async def get_daily_reward(user_id: int) -> Tuple[bool, int, int]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT last_claim, streak FROM daily_rewards WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()
            now = datetime.now()
            if result:
                last_claim = datetime.fromisoformat(result[0])
                streak = result[1]
                if last_claim.date() == now.date():
                    return False, streak, 0
                if (now.date() - last_claim.date()).days == 1:
                    streak += 1
                else:
                    streak = 1
            else:
                streak = 1
            base_bonus = 100
            bonus = int(base_bonus * (1 + (streak - 1) * 0.1))
            await db.execute('''
                INSERT INTO daily_rewards (user_id, last_claim, streak)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_claim = ?,
                    streak = ?
            ''', (user_id, now, streak, now, streak))
            await db.commit()
            return True, streak, bonus

    @staticmethod
    async def get_game_settings(game_type: str) -> Dict:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT settings_json FROM game_settings WHERE game_type = ?', (game_type,))
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return {}

    @staticmethod
    async def update_game_settings(game_type: str, settings: Dict):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('INSERT OR REPLACE INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             (game_type, json.dumps(settings)))
            await db.commit()

# ============================================
# БАЗОВЫЙ КЛАСС ДЛЯ ИГР
# ============================================
class BaseGame:
    def __init__(self, game_type: str):
        self.game_type = game_type
        self.settings = {}

    async def load_settings(self):
        self.settings = await Database.get_game_settings(self.game_type)

    async def get_rtp(self) -> float:
        return self.settings.get('rtp', RTP_ACTUAL)

    def calculate_win(self, bet: int, result: Dict) -> int:
        raise NotImplementedError

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        raise NotImplementedError

    def get_provably_fair_seed(self, server_seed: str, client_seed: str, nonce: int) -> str:
        combined = f"{server_seed}:{client_seed}:{nonce}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get_random_number(self, min_val: int, max_val: int, seed: str) -> int:
        hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        return min_val + (hash_val % (max_val - min_val + 1))

# ============================================
# УЛУЧШЕННЫЙ КЛАСС ДЛЯ СЛОТОВ
# ============================================
class SlotGame(BaseGame):
    def __init__(self, game_type="slot"):
        super().__init__(game_type)

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "symbols": ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐", "🎰"],
                "weights": [100, 80, 60, 40, 20, 10, 5, 2],
                "values": [2, 3, 4, 5, 8, 12, 20, 30],
                "wild": "⭐",
                "scatter": "🎰",
                "free_spins_mult": 10,
                "bonus_game_prob": 0.01,
                "rtp": RTP_ACTUAL
            }
        cum = 0
        self.cum_weights = []
        for w in self.settings['weights']:
            cum += w
            self.cum_weights.append(cum)
        self.total_weight = cum

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)

        matrix = []
        for i in range(3):
            row = []
            for j in range(5):
                seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i*5 + j)
                r = self.get_random_number(1, self.total_weight, seed)
                for idx, cw in enumerate(self.cum_weights):
                    if r <= cw:
                        symbol_index = idx
                        break
                row.append(self.settings['symbols'][symbol_index])
            matrix.append(row)

        win = self.calculate_win(bet, {"matrix": matrix, "user_id": user_id})
        scatter_count = sum(row.count(self.settings['scatter']) for row in matrix)
        free_spins = scatter_count * self.settings['free_spins_mult'] if scatter_count >= 3 else 0
        bonus_game = random.random() < self.settings.get('bonus_game_prob', 0.01)

        return {
            "matrix": matrix,
            "win_amount": win,
            "free_spins": free_spins,
            "bonus_game": bonus_game,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def calculate_win(self, bet: int, result: Dict) -> int:
        matrix = result["matrix"]
        win = 0
        paylines = self.get_paylines()
        wild = self.settings['wild']
        values = self.settings['values']
        symbols = self.settings['symbols']

        for payline in paylines:
            line_symbols = [matrix[row][col] for col, row in enumerate(payline)]
            if all(s == line_symbols[0] or s == wild for s in line_symbols):
                main = next(s for s in line_symbols if s != wild) if any(s != wild for s in line_symbols) else wild
                idx = symbols.index(main)
                mult = values[idx]
                win += bet * mult

        rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
        win = int(win * rtp_factor)

        if random.random() < 0.001:
            jackpot = asyncio.run(Database.get_jackpot())
            win += jackpot
            if win > 0 and result.get("user_id"):
                asyncio.create_task(Database.reset_jackpot(result["user_id"]))

        return win

    def get_paylines(self) -> List[List[int]]:
        return [
            [0,0,0,0,0], [1,1,1,1,1], [2,2,2,2,2],
            [0,1,2,1,0], [2,1,0,1,2], [0,0,1,2,2],
            [2,2,1,0,0], [1,0,1,2,1], [1,2,1,0,1],
            [0,1,1,1,0]
        ]

# ============================================
# НОВЫЙ СЛОТ "ЗВЕРИ"
# ============================================
class AnimalSlotGame(SlotGame):
    def __init__(self):
        super().__init__("animalslot")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "symbols": ["🐶", "🐱", "🦊", "🐼", "🐨", "🦁", "🐯", "🐸"],
                "weights": [100, 80, 60, 40, 20, 10, 5, 2],
                "values": [2, 3, 4, 5, 8, 12, 20, 30],
                "wild": "🦁",
                "scatter": "🐸",
                "free_spins_mult": 10,
                "bonus_game_prob": 0.02,
                "rtp": RTP_ACTUAL
            }
        cum = 0
        self.cum_weights = []
        for w in self.settings['weights']:
            cum += w
            self.cum_weights.append(cum)
        self.total_weight = cum

    def bonus_game(self, user_id: int) -> int:
        choices = ["🐶", "🐱", "🦊"]
        mults = [2, 3, 5]
        idx = random.randint(0,2)
        return mults[idx]

# ============================================
# УЛУЧШЕННЫЙ КЛАСС КОСТЕЙ
# ============================================
class DiceGame(BaseGame):
    def __init__(self):
        super().__init__("dice")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "single": {1:6, 2:3, 3:2, 4:1.5, 5:1.2, 6:1},
                "double": {2:12,3:6,4:4,5:3,6:2,7:1.5,8:2,9:3,10:4,11:6,12:12},
                "rtp": RTP_ACTUAL
            }

    def generate_result(self, bet: int, user_id: int = None, mode: str = "single") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        if mode == "single":
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce)
            result = self.get_random_number(1, 6, seed)
            mult = self.settings['single'][result]
        else:
            seed1 = self.get_provably_fair_seed(server_seed, client_seed, nonce)
            seed2 = self.get_provably_fair_seed(server_seed, client_seed, nonce+1)
            d1 = self.get_random_number(1, 6, seed1)
            d2 = self.get_random_number(1, 6, seed2)
            result = d1 + d2
            mult = self.settings['double'][result]
        rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
        return {
            "result": result,
            "multiplier": mult * rtp_factor,
            "mode": mode,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def calculate_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["multiplier"])

# ============================================
# УЛУЧШЕННЫЙ КЛАСС РУЛЕТКИ
# ============================================
class RouletteGame(BaseGame):
    def __init__(self):
        super().__init__("roulette")
        self.numbers = list(range(0, 37))
        self.colors = {0: "green"}
        for i in range(1, 37):
            if i in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]:
                self.colors[i] = "red"
            else:
                self.colors[i] = "black"

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "straight": 36,
                "red": 2, "black": 2, "even": 2, "odd": 2, "low": 2, "high": 2,
                "dozen": 3, "column": 3,
                "rtp": RTP_ACTUAL
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        seed = self.get_provably_fair_seed(server_seed, client_seed, nonce)
        number = self.get_random_number(0, 36, seed)
        return {
            "number": number,
            "color": self.colors[number],
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": seed
        }

    def calculate_win(self, bet: int, result: Dict, bet_type: str, bet_number: int = None) -> int:
        num = result["number"]
        if bet_type == "straight" and bet_number == num:
            mult = self.settings.get('straight', 36)
        elif bet_type == "red" and result["color"] == "red":
            mult = self.settings.get('red', 2)
        elif bet_type == "black" and result["color"] == "black":
            mult = self.settings.get('black', 2)
        elif bet_type == "even" and num > 0 and num % 2 == 0:
            mult = self.settings.get('even', 2)
        elif bet_type == "odd" and num % 2 == 1:
            mult = self.settings.get('odd', 2)
        elif bet_type == "low" and 1 <= num <= 18:
            mult = self.settings.get('low', 2)
        elif bet_type == "high" and 19 <= num <= 36:
            mult = self.settings.get('high', 2)
        elif bet_type == "dozen1" and 1 <= num <= 12:
            mult = self.settings.get('dozen', 3)
        elif bet_type == "dozen2" and 13 <= num <= 24:
            mult = self.settings.get('dozen', 3)
        elif bet_type == "dozen3" and 25 <= num <= 36:
            mult = self.settings.get('dozen', 3)
        elif bet_type == "column1" and num in [1,4,7,10,13,16,19,22,25,28,31,34]:
            mult = self.settings.get('column', 3)
        elif bet_type == "column2" and num in [2,5,8,11,14,17,20,23,26,29,32,35]:
            mult = self.settings.get('column', 3)
        elif bet_type == "column3" and num in [3,6,9,12,15,18,21,24,27,30,33,36]:
            mult = self.settings.get('column', 3)
        else:
            return 0
        rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
        return int(bet * mult * rtp_factor)

# ============================================
# УЛУЧШЕННЫЙ КЛАСС БЛЭКДЖЕКА
# ============================================
class BlackjackGame(BaseGame):
    def __init__(self):
        super().__init__("blackjack")
        self.suits = ["♠", "♥", "♦", "♣"]
        self.ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        self.values = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":10,"Q":10,"K":10,"A":11}

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {"rtp": RTP_ACTUAL}

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        deck = [(rank, suit) for suit in self.suits for rank in self.ranks] * 4
        shuffled = self.shuffle_deck(deck, server_seed, client_seed, nonce)
        player_hand = [shuffled[0], shuffled[2]]
        dealer_hand = [shuffled[1], shuffled[3]]
        remaining = shuffled[4:]
        player_score = self.hand_score(player_hand)
        dealer_up = dealer_hand[0]
        return {
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "deck": remaining,
            "player_score": player_score,
            "dealer_upcard": dealer_up,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def shuffle_deck(self, deck, server_seed, client_seed, nonce):
        shuffled = deck.copy()
        for i in range(len(shuffled)-1, 0, -1):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            j = self.get_random_number(0, i, seed)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled

    def hand_score(self, hand):
        score = 0
        aces = 0
        for rank,_ in hand:
            if rank == "A":
                aces += 1
                score += 11
            else:
                score += self.values[rank]
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    def dealer_play(self, dealer_hand, deck):
        score = self.hand_score(dealer_hand)
        while score < 17 and deck:
            dealer_hand.append(deck.pop(0))
            score = self.hand_score(dealer_hand)
        return dealer_hand

    def calculate_win(self, bet: int, player_hand, dealer_hand) -> int:
        player_score = self.hand_score(player_hand)
        dealer_score = self.hand_score(dealer_hand)
        if player_score > 21:
            return 0
        if dealer_score > 21:
            return bet * 2
        if player_score > dealer_score:
            return bet * 2
        if player_score == dealer_score:
            return bet
        return 0

# ============================================
# PLINKO
# ============================================
class PlinkoGame(BaseGame):
    def __init__(self):
        super().__init__("plinko")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "low": [16,9,2,1.4,1.2,1.1,1,0.5,0.5,1,1.1,1.2,1.4,2,9,16],
                "medium": [22,12,3,1.8,1.4,1.2,0.8,0.3,0.3,0.8,1.2,1.4,1.8,3,12,22],
                "high": [33,18,5,2.5,1.8,1.3,0.5,0.2,0.2,0.5,1.3,1.8,2.5,5,18,33],
                "rtp": RTP_ACTUAL
            }

    def generate_result(self, bet: int, user_id: int = None, risk: str = "medium") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        rows = 16
        pos = rows / 2
        for step in range(rows):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + step)
            r = self.get_random_number(0, 99, seed)
            if r < 50:
                pos -= 0.5
            else:
                pos += 0.5
        final = int(round(pos))
        final = max(0, min(rows-1, final))
        mult = self.settings[risk][final]
        rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
        return {
            "final_position": final,
            "multiplier": mult * rtp_factor,
            "risk": risk,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def calculate_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["multiplier"])

# ============================================
# MINES
# ============================================
class MinesGame(BaseGame):
    def __init__(self):
        super().__init__("mines")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {"rtp": RTP_ACTUAL, "gold_bonus": 0.1}

    def generate_result(self, bet: int, user_id: int = None, mines: int = 3, difficulty: str = "medium") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        all_cells = list(range(25))
        mine_positions = []
        for i in range(mines):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            idx = self.get_random_number(0, len(all_cells)-1, seed)
            mine_positions.append(all_cells.pop(idx))
        gold_positions = []
        for i in range(2):
            if all_cells:
                seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + mines + i)
                idx = self.get_random_number(0, len(all_cells)-1, seed)
                gold_positions.append(all_cells.pop(idx))
        return {
            "mine_positions": mine_positions,
            "gold_positions": gold_positions,
            "mines": mines,
            "difficulty": difficulty,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def calculate_win(self, bet: int, result: Dict, revealed: List[int]) -> int:
        if not revealed:
            return 0
        for cell in revealed:
            if cell in result["mine_positions"]:
                return 0
        safe = 25 - result["mines"]
        mult = safe / (safe - len(revealed) + 1)
        gold_bonus = 1 + self.settings.get('gold_bonus',0.1) * sum(1 for c in revealed if c in result["gold_positions"])
        rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
        return int(bet * mult * gold_bonus * rtp_factor)

# ============================================
# КЕНО
# ============================================
class KenoGame(BaseGame):
    def __init__(self):
        super().__init__("keno")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "payouts": {
                    1: {1:3},
                    2: {2:12,1:1},
                    3: {3:42,2:2,1:1},
                    4: {4:150,3:5,2:1},
                    5: {5:500,4:15,3:2},
                    6: {6:1500,5:50,4:5,3:1},
                    7: {7:5000,6:150,5:15,4:2},
                    8: {8:15000,7:500,6:50,5:5,4:1}
                },
                "rtp": RTP_ACTUAL
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        nums = list(range(1,81))
        winning = []
        for i in range(20):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            idx = self.get_random_number(0, len(nums)-1, seed)
            winning.append(nums.pop(idx))
        return {
            "winning": winning,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }

    def calculate_win(self, bet: int, result: Dict, picks: List[int]) -> int:
        winning = result["winning"]
        matches = sum(1 for p in picks if p in winning)
        cnt = len(picks)
        payouts = self.settings['payouts']
        if cnt in payouts and matches in payouts[cnt]:
            mult = payouts[cnt][matches]
            rtp_factor = self.settings.get('rtp', RTP_ACTUAL) / 100.0
            return int(bet * mult * rtp_factor)
        return 0
# ============================================
# ОСНОВНОЙ КЛАСС БОТА
# ============================================
class CasinoBot:
    def __init__(self):
        self.games = {
            "slot": SlotGame(),
            "animalslot": AnimalSlotGame(),
            "dice": DiceGame(),
            "roulette": RouletteGame(),
            "blackjack": BlackjackGame(),
            "plinko": PlinkoGame(),
            "mines": MinesGame(),
            "keno": KenoGame()
        }
        self.active_games = {}      # для mines
        self.blackjack_games = {}   # активные игры блэкджек
        self.free_spins = {}         # фриспины для слотов
        self.pending_withdrawals = {}
        logger.info(f"✅ Игры загружены: {list(self.games.keys())}")

    # ---- методы клавиатур ----
    def get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        lang = 'en'  # можно будет получать из профиля, пока заглушка
        buttons = [
            [InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slot"),
             InlineKeyboardButton(text="🦁 Слот Звери", callback_data="game_animalslot")],
            [InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice"),
             InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
            [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_blackjack"),
             InlineKeyboardButton(text="📌 Plinko", callback_data="game_plinko")],
            [InlineKeyboardButton(text="💣 Mines", callback_data="game_mines"),
             InlineKeyboardButton(text="🎯 Кено", callback_data="game_keno")],
            [InlineKeyboardButton(text=get_text('balance', lang), callback_data="balance"),
             InlineKeyboardButton(text=get_text('settings', lang), callback_data="settings")],
            [InlineKeyboardButton(text="🏆 Турниры", callback_data="tournaments"),
             InlineKeyboardButton(text="🎁 Бонусы", callback_data="bonuses")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
             InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
            [InlineKeyboardButton(text="📜 История", callback_data="history")]
        ]
        if user_id in ADMIN_IDS:
            buttons.append([InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def get_game_keyboard(self, game_type: str, game_state: Dict = None) -> InlineKeyboardMarkup:
        buttons = []
        if game_type in ["slot", "animalslot"]:
            buttons = [
                [InlineKeyboardButton(text="🎰 10 ⭐", callback_data=f"play_{game_type}_10"),
                 InlineKeyboardButton(text="🎰 50 ⭐", callback_data=f"play_{game_type}_50")],
                [InlineKeyboardButton(text="🎰 100 ⭐", callback_data=f"play_{game_type}_100"),
                 InlineKeyboardButton(text="🎰 500 ⭐", callback_data=f"play_{game_type}_500")],
                [InlineKeyboardButton(text="💰 Своя ставка", callback_data=f"custom_bet_{game_type}")]
            ]
        elif game_type == "dice":
            buttons = [
                [InlineKeyboardButton(text="🎲 1 кубик", callback_data="dice_single"),
                 InlineKeyboardButton(text="🎲🎲 2 кубика", callback_data="dice_double")],
                [InlineKeyboardButton(text="10 ⭐", callback_data="play_dice_10"),
                 InlineKeyboardButton(text="50 ⭐", callback_data="play_dice_50")],
                [InlineKeyboardButton(text="100 ⭐", callback_data="play_dice_100"),
                 InlineKeyboardButton(text="500 ⭐", callback_data="play_dice_500")],
                [InlineKeyboardButton(text="💰 Своя ставка", callback_data="custom_bet_dice")]
            ]
        elif game_type == "roulette":
            buttons = [
                [InlineKeyboardButton(text="🔴 Красное", callback_data="roulette_red"),
                 InlineKeyboardButton(text="⚫ Черное", callback_data="roulette_black")],
                [InlineKeyboardButton(text="👤 Четное", callback_data="roulette_even"),
                 InlineKeyboardButton(text="👥 Нечетное", callback_data="roulette_odd")],
                [InlineKeyboardButton(text="1️⃣ 1-12", callback_data="roulette_dozen1"),
                 InlineKeyboardButton(text="2️⃣ 13-24", callback_data="roulette_dozen2")],
                [InlineKeyboardButton(text="3️⃣ 25-36", callback_data="roulette_dozen3"),
                 InlineKeyboardButton(text="📊 Колонки", callback_data="roulette_columns")],
                [InlineKeyboardButton(text="🎯 Число", callback_data="roulette_number"),
                 InlineKeyboardButton(text="💰 Ставка", callback_data="roulette_bet")]
            ]
        elif game_type == "blackjack":
            if game_state and game_state.get("active"):
                buttons = [
                    [InlineKeyboardButton(text="🃏 Еще карту", callback_data="blackjack_hit"),
                     InlineKeyboardButton(text="⏹ Хватит", callback_data="blackjack_stand")],
                    [InlineKeyboardButton(text="💰 Удвоить", callback_data="blackjack_double"),
                     InlineKeyboardButton(text="🤝 Страховка", callback_data="blackjack_insurance")],
                    [InlineKeyboardButton(text="🔄 Новая игра", callback_data="blackjack_new")]
                ]
            else:
                buttons = [
                    [InlineKeyboardButton(text="🃏 10 ⭐", callback_data="play_blackjack_10"),
                     InlineKeyboardButton(text="🃏 50 ⭐", callback_data="play_blackjack_50")],
                    [InlineKeyboardButton(text="🃏 100 ⭐", callback_data="play_blackjack_100"),
                     InlineKeyboardButton(text="🃏 500 ⭐", callback_data="play_blackjack_500")],
                    [InlineKeyboardButton(text="💰 Своя ставка", callback_data="custom_bet_blackjack")]
                ]
        elif game_type == "plinko":
            buttons = [
                [InlineKeyboardButton(text="📌 Низкий риск", callback_data="plinko_low"),
                 InlineKeyboardButton(text="📌 Средний риск", callback_data="plinko_medium")],
                [InlineKeyboardButton(text="📌 Высокий риск", callback_data="plinko_high"),
                 InlineKeyboardButton(text="💰 Ставка", callback_data="plinko_bet")]
            ]
        elif game_type == "mines":
            if game_state and game_state.get("active"):
                grid_buttons = []
                revealed = game_state.get("revealed", [])
                mines = game_state.get("mine_positions", [])
                gold = game_state.get("gold_positions", [])
                for i in range(5):
                    row = []
                    for j in range(5):
                        cell = i*5 + j
                        if cell in revealed:
                            if cell in mines:
                                text = "💥"
                            elif cell in gold:
                                text = "💰"
                            else:
                                text = "✅"
                        else:
                            text = "⬜"
                        row.append(InlineKeyboardButton(text=text, callback_data=f"mine_cell_{cell}"))
                    grid_buttons.append(row)
                buttons = grid_buttons + [
                    [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="mines_cashout")],
                    [InlineKeyboardButton(text="🔄 Новая игра", callback_data="mines_new")]
                ]
            else:
                buttons = [
                    [InlineKeyboardButton(text="💣 3 мины (легко)", callback_data="mines_easy_3"),
                     InlineKeyboardButton(text="💣 5 мин (средне)", callback_data="mines_medium_5")],
                    [InlineKeyboardButton(text="💣 10 мин (сложно)", callback_data="mines_hard_10"),
                     InlineKeyboardButton(text="💰 Ставка", callback_data="mines_bet")]
                ]
        elif game_type == "keno":
            buttons = [
                [InlineKeyboardButton(text="🎯 1 число", callback_data="keno_pick1"),
                 InlineKeyboardButton(text="🎯 3 числа", callback_data="keno_pick3")],
                [InlineKeyboardButton(text="🎯 5 чисел", callback_data="keno_pick5"),
                 InlineKeyboardButton(text="🎯 8 чисел", callback_data="keno_pick8")],
                [InlineKeyboardButton(text="💰 Ставка", callback_data="keno_bet")]
            ]
        buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def get_admin_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats"),
             InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users_menu")],
            [InlineKeyboardButton(text="💰 Управление балансом", callback_data="admin_balance"),
             InlineKeyboardButton(text="🎮 Настройки RTP", callback_data="admin_rtp")],
            [InlineKeyboardButton(text="🎰 Редактор слотов", callback_data="admin_slot_edit"),
             InlineKeyboardButton(text="🏆 Управление турнирами", callback_data="admin_tournaments_menu")],
            [InlineKeyboardButton(text="🎁 Бонус коды", callback_data="admin_bonuses_menu"),
             InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin_withdrawals")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
             InlineKeyboardButton(text="⚙️ Настройки казино", callback_data="admin_settings")],
            [InlineKeyboardButton(text="📥 Скачать БД", callback_data="admin_download_db"),
             InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    # ---- команды и обработчики ----
    async def cmd_start(self, message: Message):
        user_id = message.from_user.id
        await Database.create_user(user_id, message.from_user.username,
                                   message.from_user.first_name, message.from_user.last_name)
        user = await Database.get_user(user_id)
        lang = user.get('language', 'ru')
        text = get_text('welcome', lang) + f"\n{get_text('balance', lang)}: {user['balance']} ⭐"
        await message.answer(text, reply_markup=self.get_main_keyboard(user_id))

    async def cmd_balance(self, user_id: int, message: Message):
        user = await Database.get_user(user_id)
        if not user:
            await message.answer(get_text('user_not_found'))
            return
        lang = user.get('language', 'ru')
        text = f"{get_text('balance', lang)}: **{user['balance']} ⭐**\n{get_text('vip_level', lang)}: {user['vip_level']} ({get_text('experience', lang)}: {user['experience']})"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
             InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(text, reply_markup=kb)

    # ========== ОСНОВНОЙ CALLBACK ==========
    async def callback_handler(self, callback: CallbackQuery, state: FSMContext):
        data = callback.data
        user_id = callback.from_user.id

        # ---- главное меню ----
        if data == "main_menu":
            await callback.message.edit_text("🎰 **ГЛАВНОЕ МЕНЮ**", reply_markup=self.get_main_keyboard(user_id))

        # ---- баланс, пополнение, вывод ----
        elif data == "balance":
            await self.cmd_balance(user_id, callback.message)

        elif data == "deposit":
            await state.set_state(BetStates.waiting_for_deposit_amount)
            await callback.message.edit_text(
                "💳 Введите сумму в ⭐ (от 10 до 10000):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
                ])
            )

        elif data == "withdraw":
            user = await Database.get_user(user_id)
            min_wd = int(await Database.get_setting('min_withdrawal'))
            if user['balance'] < min_wd:
                await callback.answer(f"❌ Минимальная сумма вывода {min_wd} ⭐", show_alert=True)
                return
            await state.set_state(BetStates.waiting_for_withdrawal_amount)
            await callback.message.edit_text(
                f"💸 Введите сумму (баланс: {user['balance']} ⭐):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
                ])
            )

        # ---- игры ----
        elif data.startswith("game_"):
            game = data.replace("game_", "")
            if game in self.games:
                await callback.message.edit_text(
                    f"🎮 **{game.upper()}**\nВыберите параметры:",
                    reply_markup=self.get_game_keyboard(game)
                )
            else:
                await callback.answer("❌ Игра недоступна", show_alert=True)

        elif data.startswith("play_"):
            parts = data.split("_")
            if len(parts) < 3:
                await callback.answer("❌ Ошибка", show_alert=True)
                return
            game = parts[1]
            try:
                bet = int(parts[2])
            except:
                await callback.answer("❌ Неверная сумма", show_alert=True)
                return
            await self.play_game(callback, game, bet)

        elif data.startswith("custom_bet_"):
            game = data.replace("custom_bet_", "")
            await state.update_data(game_type=game)
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text(
                f"💰 Введите сумму ставки (от {MIN_BET} до {MAX_BET}):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"game_{game}")]
                ])
            )

        # ---- кости ----
        elif data == "dice_single":
            await state.update_data(game_type="dice", mode="single")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲 Введите сумму:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]]))

        elif data == "dice_double":
            await state.update_data(game_type="dice", mode="double")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲🎲 Введите сумму:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]]))

        # ---- рулетка ----
        elif data.startswith("roulette_"):
            bt = data.replace("roulette_", "")
            if bt == "number":
                await state.update_data(game_type="roulette", bet_type="straight")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("🎯 Введите число и сумму через пробел (например 7 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]]))
            elif bt == "columns":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="1 колонка", callback_data="roulette_column1"),
                     InlineKeyboardButton(text="2 колонка", callback_data="roulette_column2")],
                    [InlineKeyboardButton(text="3 колонка", callback_data="roulette_column3")],
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="game_roulette")]
                ])
                await callback.message.edit_text("📊 Выберите колонку:", reply_markup=kb)
            elif bt in ["red","black","even","odd","low","high","dozen1","dozen2","dozen3","column1","column2","column3"]:
                await state.update_data(game_type="roulette", bet_type=bt)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎡 Введите сумму ставки на {bt}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]]))

        # ---- plinko ----
        elif data.startswith("plinko_"):
            risk = data.replace("plinko_", "")
            if risk in ["low","medium","high"]:
                await state.update_data(game_type="plinko", risk=risk)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"📌 Введите сумму (риск {risk}):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]]))
            elif risk == "bet":
                await state.update_data(game_type="plinko", risk="medium")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("📌 Введите сумму (средний риск):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]]))

        # ---- mines ----
        elif data.startswith("mines_"):
            parts = data.split("_")
            if len(parts) == 3 and parts[1] in ["easy","medium","hard"]:
                difficulty = parts[1]
                mines = int(parts[2])
                await state.update_data(game_type="mines", mines=mines, difficulty=difficulty)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"💣 Введите сумму ({difficulty}, {mines} мин):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]]))
            elif data == "mines_bet":
                await state.update_data(game_type="mines", mines=5, difficulty="medium")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("💣 Введите сумму (5 мин, средний риск):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]]))
            elif data == "mines_cashout":
                if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game = self.active_games[user_id]
                win = self.games["mines"].calculate_win(game["bet"], game["result"], game["revealed"])
                await Database.update_balance(user_id, win, "Выигрыш Mines")
                await Database.add_game_history(user_id, "mines", game["bet"], win, game["result"])
                await Database.update_jackpot(int(game["bet"]*JACKPOT_PERCENT))
                del self.active_games[user_id]
                jackpot = await Database.get_jackpot()
                await callback.message.edit_text(f"✅ Вы выиграли {win} ⭐!\n💰 Джекпот: {jackpot} ⭐", reply_markup=self.get_game_keyboard("mines"))
            elif data == "mines_new":
                if user_id in self.active_games:
                    del self.active_games[user_id]
                await callback.message.edit_text("💣 Mines", reply_markup=self.get_game_keyboard("mines"))
            elif data.startswith("mine_cell_"):
                cell = int(data.replace("mine_cell_",""))
                if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game = self.active_games[user_id]
                if cell in game["revealed"]:
                    await callback.answer("Уже открыто", show_alert=True)
                    return
                game["revealed"].append(cell)
                if cell in game["result"]["mine_positions"]:
                    del self.active_games[user_id]
                    await Database.update_jackpot(int(game["bet"]*JACKPOT_PERCENT))
                    await Database.add_game_history(user_id, "mines", game["bet"], 0, game["result"])
                    await callback.message.edit_text("💥 **БАБАХ!** Вы проиграли.", reply_markup=self.get_game_keyboard("mines"))
                else:
                    self.active_games[user_id] = game
                    cur_win = self.games["mines"].calculate_win(game["bet"], game["result"], game["revealed"])
                    await callback.message.edit_text(
                        f"✅ Безопасно! Текущий выигрыш: {cur_win} ⭐",
                        reply_markup=self.get_game_keyboard("mines", game)
                    )

        # ---- кено ----
        elif data.startswith("keno_"):
            pk = data.replace("keno_pick","")
            if pk.isdigit():
                picks = int(pk)
                await state.update_data(game_type="keno", picks=picks)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎯 Введите {picks} чисел от 1 до 80 через пробел и сумму (пример: 5 12 33 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]]))
            elif data == "keno_bet":
                await state.update_data(game_type="keno", picks=5)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("🎯 Введите 5 чисел и сумму (пример: 5 12 33 45 78 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]]))

        # ---- блэкджек ----
        elif data == "blackjack_hit":
            if user_id not in self.blackjack_games:
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game = self.blackjack_games[user_id]
            if not game["deck"]:
                await callback.answer("Колода пуста", show_alert=True)
                return
            new_card = game["deck"].pop(0)
            game["player_hand"].append(new_card)
            game["player_score"] = self.games["blackjack"].hand_score(game["player_hand"])
            if game["player_score"] > 21:
                await Database.add_game_history(user_id, "blackjack", game["bet"], 0, {"final":"bust"})
                del self.blackjack_games[user_id]
                await callback.message.edit_text(f"❌ **ПЕРЕБОР!** Вы проиграли.", reply_markup=self.get_game_keyboard("blackjack"))
            else:
                self.blackjack_games[user_id] = game
                await callback.message.edit_text(
                    self.format_hand(game["player_hand"]) + f" (очков: {game['player_score']})",
                    reply_markup=self.get_game_keyboard("blackjack", {"active":True})
                )

        elif data == "blackjack_stand":
            if user_id not in self.blackjack_games:
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game = self.blackjack_games[user_id]
            dealer_hand = game["dealer_hand"]
            deck = game["deck"]
            dealer_score = self.games["blackjack"].hand_score(dealer_hand)
            while dealer_score < 17 and deck:
                dealer_hand.append(deck.pop(0))
                dealer_score = self.games["blackjack"].hand_score(dealer_hand)
            win = self.games["blackjack"].calculate_win(game["bet"], game["player_hand"], dealer_hand)
            profit = win - game["bet"]
            if win > 0:
                await Database.update_balance(user_id, profit, "Выигрыш блэкджек")
            await Database.add_game_history(user_id, "blackjack", game["bet"], win, {"player":game["player_hand"],"dealer":dealer_hand})
            del self.blackjack_games[user_id]
            await Database.update_jackpot(int(game["bet"]*JACKPOT_PERCENT))
            jackpot = await Database.get_jackpot()
            await callback.message.edit_text(
                f"🃏 Результат:\nВаши: {self.format_hand(game['player_hand'])} ({game['player_score']})\nДилер: {self.format_hand(dealer_hand)} ({dealer_score})\n\n{'✅' if win>0 else '❌'} Выигрыш: {win} ⭐\n💰 Джекпот: {jackpot} ⭐",
                reply_markup=self.get_game_keyboard("blackjack")
            )

        elif data == "blackjack_double":
            if user_id not in self.blackjack_games:
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game = self.blackjack_games[user_id]
            user = await Database.get_user(user_id)
            if user['balance'] < game['bet']:
                await callback.answer("❌ Недостаточно для удвоения", show_alert=True)
                return
            await Database.update_balance(user_id, -game['bet'], "Удвоение")
            game['bet'] *= 2
            new_card = game["deck"].pop(0)
            game["player_hand"].append(new_card)
            game["player_score"] = self.games["blackjack"].hand_score(game["player_hand"])
            if game["player_score"] > 21:
                await Database.add_game_history(user_id, "blackjack", game["bet"], 0, {"final":"bust"})
                del self.blackjack_games[user_id]
                await callback.message.edit_text("❌ Перебор! Вы проиграли.", reply_markup=self.get_game_keyboard("blackjack"))
            else:
                dealer_hand = game["dealer_hand"]
                deck = game["deck"]
                dealer_score = self.games["blackjack"].hand_score(dealer_hand)
                while dealer_score < 17 and deck:
                    dealer_hand.append(deck.pop(0))
                    dealer_score = self.games["blackjack"].hand_score(dealer_hand)
                win = self.games["blackjack"].calculate_win(game["bet"], game["player_hand"], dealer_hand)
                profit = win - game["bet"]
                if win > 0:
                    await Database.update_balance(user_id, profit, "Выигрыш блэкджек")
                await Database.add_game_history(user_id, "blackjack", game["bet"], win, {"player":game["player_hand"],"dealer":dealer_hand})
                del self.blackjack_games[user_id]
                await Database.update_jackpot(int(game["bet"]*JACKPOT_PERCENT))
                jackpot = await Database.get_jackpot()
                await callback.message.edit_text(
                    f"🃏 Результат (удвоение):\nВаши: {self.format_hand(game['player_hand'])} ({game['player_score']})\nДилер: {self.format_hand(dealer_hand)} ({dealer_score})\n\n{'✅' if win>0 else '❌'} Выигрыш: {win} ⭐\n💰 Джекпот: {jackpot} ⭐",
                    reply_markup=self.get_game_keyboard("blackjack")
                )

        elif data == "blackjack_insurance":
            if user_id not in self.blackjack_games:
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game = self.blackjack_games[user_id]
            user = await Database.get_user(user_id)
            insurance_cost = game['bet'] // 2
            if user['balance'] < insurance_cost:
                await callback.answer("❌ Недостаточно для страховки", show_alert=True)
                return
            await Database.update_balance(user_id, -insurance_cost, "Страховка")
            dealer_hand = game["dealer_hand"]
            dealer_score = self.games["blackjack"].hand_score(dealer_hand)
            if dealer_score == 21 and len(dealer_hand) == 2:
                win = insurance_cost * 2
                await Database.update_balance(user_id, win, "Выигрыш страховки")
                await callback.answer(f"✅ Страховка сработала! Выигрыш {win} ⭐", show_alert=True)
                del self.blackjack_games[user_id]
                await callback.message.edit_text("🤝 Страховка сыграла.", reply_markup=self.get_game_keyboard("blackjack"))
            else:
                await callback.answer("❌ У дилера нет блэкджека, страховка проиграла", show_alert=True)

        elif data == "blackjack_new":
            if user_id in self.blackjack_games:
                del self.blackjack_games[user_id]
            await callback.message.edit_text("🃏 Блэкджек", reply_markup=self.get_game_keyboard("blackjack"))

        # ---- турниры, бонусы, статистика, рефералы, настройки, история ----
        elif data == "tournaments":
            await self.show_tournaments(callback)

        elif data == "bonuses":
            await self.show_bonuses(callback)

        elif data == "claim_daily":
            await self.claim_daily(callback)

        elif data == "claim_faucet":
            await self.claim_faucet(callback)

        elif data == "activate_bonus":
            await state.set_state(BetStates.waiting_for_bonus_code)
            await callback.message.edit_text(
                "🎫 Введите бонус код:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="bonuses")]
                ])
            )

        elif data == "stats":
            await self.show_stats(callback)

        elif data == "referrals":
            await self.show_referrals(callback)

        elif data == "settings":
            await self.show_settings(callback)

        elif data == "change_language":
            await self.change_language(callback)

        elif data == "provably_fair_info":
            await self.provably_fair_info(callback)

        elif data == "history":
            await self.show_history(callback)

        # ---- АДМИНКА ----
        elif data == "admin_panel":
            if user_id not in ADMIN_IDS:
                await callback.answer("❌ Доступ запрещен", show_alert=True)
                return
            users = await Database.get_users_count()
            jack = await Database.get_jackpot()
            text = f"👑 **Админ панель**\n\nПользователей: {users}\nДжекпот: {jack} ⭐"
            await callback.message.edit_text(text, reply_markup=self.get_admin_keyboard())

        elif data == "admin_stats":
            if user_id not in ADMIN_IDS:
                return
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT COUNT(*) FROM users')
                users = (await cursor.fetchone())[0]
                cursor = await db.execute('SELECT COUNT(*), SUM(bet_amount), SUM(profit) FROM games')
                r = await cursor.fetchone()
                games, bets, prof = r[0] or 0, r[1] or 0, r[2] or 0
            jack = await Database.get_jackpot()
            text = f"📊 **Статистика бота**\n\nПользователей: {users}\nИгр: {games}\nСтавок: {bets} ⭐\nПрофит казино: {prof} ⭐\nДжекпот: {jack} ⭐"
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]]))

        elif data == "admin_users_menu":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список", callback_data="admin_users_list"),
                 InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admin_user_search")],
                [InlineKeyboardButton(text="🔍 По username", callback_data="admin_user_search_username")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("👥 Управление пользователями", reply_markup=kb)

        elif data == "admin_users_list":
            if user_id not in ADMIN_IDS:
                return
            users = await Database.get_all_users(limit=10, offset=0)
            total = await Database.get_users_count()
            text = f"👥 **Пользователи** (1-10 из {total})\n\n"
            for u in users:
                text += f"ID: {u['user_id']} @{u['username']} баланс {u['balance']} ⭐ VIP{u['vip_level']}\n"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="▶️ След.", callback_data="admin_users_page_1")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
            ])
            await callback.message.edit_text(text, reply_markup=kb)

        elif data.startswith("admin_users_page_"):
            if user_id not in ADMIN_IDS:
                return
            page = int(data.replace("admin_users_page_", ""))
            users = await Database.get_all_users(limit=10, offset=page*10)
            total = await Database.get_users_count()
            text = f"👥 **Пользователи** (стр.{page+1})\n\n"
            for u in users:
                text += f"ID: {u['user_id']} @{u['username']} баланс {u['balance']} ⭐ VIP{u['vip_level']}\n"
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(text="◀️ Пред.", callback_data=f"admin_users_page_{page-1}"))
            if (page+1)*10 < total:
                nav.append(InlineKeyboardButton(text="▶️ След.", callback_data=f"admin_users_page_{page+1}"))
            kb = InlineKeyboardMarkup(inline_keyboard=[nav, [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]])
            await callback.message.edit_text(text, reply_markup=kb)

        elif data == "admin_user_search":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="search_user")
            await callback.message.edit_text("🔍 Введите ID пользователя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]]))

        elif data == "admin_user_search_username":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="search_username")
            await callback.message.edit_text("🔍 Введите username (без @):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]]))

        elif data == "admin_balance":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="balance_change")
            await callback.message.edit_text("💰 Введите ID пользователя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]]))

        elif data == "admin_rtp":
            if user_id not in ADMIN_IDS:
                return
            settings = await Database.get_rtp_settings()
            text = "🎮 **Настройки RTP**\n\n"
            btns = []
            for g in self.games:
                cur = settings.get(g, {}).get('current_rtp', RTP_ACTUAL)
                text += f"{g}: {cur:.2f}%\n"
                btns.append([InlineKeyboardButton(text=f"Изменить {g}", callback_data=f"admin_rtp_{g}")])
            btns.append([InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

        elif data.startswith("admin_rtp_"):
            if user_id not in ADMIN_IDS:
                return
            game = data.replace("admin_rtp_", "")
            await state.set_state(BetStates.waiting_for_rtp_change)
            await state.update_data(game_type=game)
            await callback.message.edit_text(f"🎮 Введите новое RTP для {game} (0-200%):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_rtp")]]))

        elif data == "admin_slot_edit":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎰 Обычный слот", callback_data="admin_edit_slot"),
                 InlineKeyboardButton(text="🦁 Слот Звери", callback_data="admin_edit_animalslot")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("🎰 Выберите слот для редактирования:", reply_markup=kb)

        elif data == "admin_edit_slot":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_slot_edit)
            await state.update_data(slot_type="slot")
            await self.ask_slot_edit(callback, state)

        elif data == "admin_edit_animalslot":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_slot_edit)
            await state.update_data(slot_type="animalslot")
            await self.ask_slot_edit(callback, state)

        elif data == "admin_tournaments_menu":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать", callback_data="admin_tournament_create"),
                 InlineKeyboardButton(text="📋 Список", callback_data="admin_tournaments_list")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("🏆 Управление турнирами", reply_markup=kb)

        elif data == "admin_tournament_create":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_tournament_name)
            await callback.message.edit_text("🏆 Введите название турнира:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_tournaments_menu")]]))

        elif data == "admin_tournaments_list":
            if user_id not in ADMIN_IDS:
                return
            tours = await Database.get_all_tournaments()
            text = "🏆 **Турниры**\n\n"
            for t in tours:
                text += f"#{t['tournament_id']} {t['name']} - {t['status']} - приз {t['prize_pool']}\n"
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="admin_tournaments_menu")]]))

        elif data == "admin_bonuses_menu":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать код", callback_data="admin_bonus_create"),
                 InlineKeyboardButton(text="📋 Список", callback_data="admin_bonuses_list")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("🎁 Управление бонус кодами", reply_markup=kb)

        elif data == "admin_bonus_create":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_bonus_code)
            await state.update_data(admin_action="create_bonus")
            await callback.message.edit_text("🎁 Введите код (например BONUS100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonuses_menu")]]))

        elif data == "admin_bonuses_list":
            if user_id not in ADMIN_IDS:
                return
            codes = await Database.get_bonus_codes()
            text = "🎁 **Бонус коды**\n\n"
            for c in codes:
                text += f"`{c['code']}`: {c['amount']}⭐ использовано {c['used_count']}/{c['max_uses']}\n"
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="admin_bonuses_menu")]]))

        elif data == "admin_withdrawals":
            if user_id not in ADMIN_IDS:
                return
            txs = await Database.get_transactions(limit=50)
            pending = [t for t in txs if t['type']=='withdrawal' and t['status']=='pending']
            text = "💸 **Заявки на вывод**\n\n"
            if not pending:
                text += "Нет заявок"
            else:
                for p in pending:
                    text += f"ID: `{p['transaction_id']}`\nПользователь: {p['user_id']}\nСумма: {p['amount']}⭐\nКошелек: {p['wallet_address']}\n\n"
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]]))

        elif data == "admin_broadcast":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_broadcast_message)
            await callback.message.edit_text("📢 Введите сообщение для рассылки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]]))

        elif data == "admin_settings":
            if user_id not in ADMIN_IDS:
                return
            s = await Database.get_setting
            text = "⚙️ **Настройки казино**\n\n"
            keys = ['min_withdrawal','withdrawal_fee','welcome_bonus','referral_bonus','faucet_amount','faucet_cooldown']
            for k in keys:
                val = await Database.get_setting(k)
                text += f"{k}: {val}\n"
            btns = [
                [InlineKeyboardButton(text="Мин.вывод", callback_data="admin_setting_min_withdrawal"),
                 InlineKeyboardButton(text="Комиссия", callback_data="admin_setting_withdrawal_fee")],
                [InlineKeyboardButton(text="Приветственный", callback_data="admin_setting_welcome_bonus"),
                 InlineKeyboardButton(text="Реферальный", callback_data="admin_setting_referral_bonus")],
                [InlineKeyboardButton(text="Сумма крана", callback_data="admin_setting_faucet_amount"),
                 InlineKeyboardButton(text="Перезарядка", callback_data="admin_setting_faucet_cooldown")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ]
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

        elif data.startswith("admin_setting_"):
            if user_id not in ADMIN_IDS:
                return
            setting = data.replace("admin_setting_", "")
            await state.set_state(BetStates.waiting_for_admin_action)
            await state.update_data(admin_action=f"setting_{setting}")
            desc = {
                "min_withdrawal": "Введите мин. сумму вывода:",
                "withdrawal_fee": "Введите комиссию (%):",
                "welcome_bonus": "Введите приветственный бонус:",
                "referral_bonus": "Введите реферальный бонус:",
                "faucet_amount": "Введите сумму крана:",
                "faucet_cooldown": "Введите перезарядку (минуты):"
            }
            await callback.message.edit_text(desc.get(setting, "Введите значение:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings")]]))

        elif data == "admin_download_db":
            if user_id not in ADMIN_IDS:
                return
            await callback.message.answer_document(types.FSInputFile(DATABASE_PATH), caption="📦 Бэкап БД")

        else:
            await callback.answer()

    # ---- вспомогательные методы ----
    def format_hand(self, hand):
        return " ".join([f"{r}{s}" for r,s in hand])

    async def play_game(self, callback: CallbackQuery, game_type: str, bet: int, **kwargs):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        if not user:
            await callback.answer(get_text('user_not_found'), show_alert=True)
            return
        if user['balance'] < bet:
            await callback.answer(get_text('not_enough'), show_alert=True)
            return

        game = self.games.get(game_type)
        if not game:
            await callback.answer("❌ Игра недоступна", show_alert=True)
            return
        await game.load_settings()

        need_deduct = True
        mult = 1
        if game_type in ["slot","animalslot"] and user_id in self.free_spins and self.free_spins[user_id]['spins'] > 0:
            need_deduct = False
            fs = self.free_spins[user_id]
            fs['spins'] -= 1
            if fs['spins'] == 0:
                del self.free_spins[user_id]
            mult = fs.get('multiplier', 1)
            await callback.answer(f"🎁 Фриспин! Осталось {fs['spins']}", show_alert=False)

        if need_deduct:
            if not await Database.update_balance(user_id, -bet, f'Ставка в {game_type}'):
                await callback.answer("❌ Ошибка списания", show_alert=True)
                return

        if game_type == "roulette":
            result = game.generate_result(bet, user_id)
            win = game.calculate_win(bet, result, kwargs.get("bet_type", "red"), kwargs.get("bet_number"))
        elif game_type == "dice":
            result = game.generate_result(bet, user_id, kwargs.get("mode", "single"))
            win = game.calculate_win(bet, result)
        elif game_type == "plinko":
            result = game.generate_result(bet, user_id, kwargs.get("risk", "medium"))
            win = game.calculate_win(bet, result)
        elif game_type == "mines":
            result = game.generate_result(bet, user_id, kwargs.get("mines",5), kwargs.get("difficulty","medium"))
            self.active_games[user_id] = {
                "game": "mines",
                "result": result,
                "bet": bet,
                "revealed": [],
                "mine_positions": result["mine_positions"],
                "gold_positions": result["gold_positions"]
            }
            win = 0
        elif game_type == "keno":
            picks = kwargs.get("picks", [])
            result = game.generate_result(bet, user_id)
            win = game.calculate_win(bet, result, picks)
        elif game_type == "blackjack":
            result = game.generate_result(bet, user_id)
            self.blackjack_games[user_id] = {
                "player_hand": result["player_hand"],
                "dealer_hand": result["dealer_hand"],
                "deck": result["deck"],
                "bet": bet,
                "player_score": result["player_score"],
                "dealer_upcard": result["dealer_upcard"],
                "active": True
            }
            win = 0
        else:  # slot, animalslot
            result = game.generate_result(bet, user_id)
            win = game.calculate_win(bet, result) * mult
            if result.get("free_spins", 0) > 0:
                self.free_spins[user_id] = {"spins": result["free_spins"], "multiplier": 2}
                await callback.message.answer(f"🎉 ФРИСПИНЫ! {result['free_spins']} вращений с x2!")
            if result.get("bonus_game"):
                bonus_mult = game.bonus_game(user_id) if hasattr(game, 'bonus_game') else 2
                win *= bonus_mult
                await callback.message.answer(f"🎮 Бонусная игра! Множитель x{bonus_mult}")

        if win > 0 and game_type not in ["mines","blackjack"]:
            await Database.update_balance(user_id, win, f'Выигрыш в {game_type}')
            await Database.add_game_history(user_id, game_type, bet, win, result)

        if game_type not in ["mines","blackjack"]:
            await Database.update_jackpot(int(bet * JACKPOT_PERCENT))

        jackpot = await Database.get_jackpot()
        text = self.format_game_result(game_type, result, bet, win)
        text += f"\n\n💰 Джекпот: **{jackpot} ⭐**"

        if game_type == "blackjack":
            await callback.message.edit_text(
                text,
                reply_markup=self.get_game_keyboard(game_type, {"active": True})
            )
        elif game_type == "mines":
            await callback.message.edit_text(
                text,
                reply_markup=self.get_game_keyboard(game_type, self.active_games.get(user_id))
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=self.get_game_keyboard(game_type)
            )

    def format_game_result(self, game_type: str, result: Dict, bet: int, win: int) -> str:
        if game_type == "slot" or game_type == "animalslot":
            matrix = result["matrix"]
            s = f"🎰 **{game_type.upper()}**\n\n"
            for row in matrix:
                s += " | ".join(row) + "\n"
        elif game_type == "dice":
            s = f"🎲 **КОСТИ**\n\nРезультат: {result['result']}\nМножитель: x{result['multiplier']:.2f}\n"
        elif game_type == "roulette":
            s = f"🎡 **РУЛЕТКА**\n\nВыпало: {result['number']} {result['color']}\n"
        elif game_type == "blackjack":
            s = f"🃏 **БЛЭКДЖЕК**\n\nВаши карты: {self.format_hand(result['player_hand'])} ({result['player_score']})\nДилер: {self.format_hand(result['dealer_hand'][:1])} + ?\n"
        elif game_type == "plinko":
            s = f"📌 **PLINKO**\n\nПозиция: {result['final_position']}\nМножитель: x{result['multiplier']:.2f}\n"
        elif game_type == "mines":
            s = f"💣 **MINES**\n\nМин: {result['mines']}\n"
        elif game_type == "keno":
            s = f"🎯 **КЕНО**\n\nВыигрышные числа: {result['winning'][:10]}...\n"
        else:
            s = ""
        s += f"\nСтавка: **{bet} ⭐**\n"
        if win > 0:
            s += f"✅ Выигрыш: **{win} ⭐** (Профит: **+{win-bet} ⭐**)"
        elif win == 0 and game_type not in ["mines","blackjack"]:
            s += f"❌ Проигрыш"
        if "hash" in result:
            s += f"\n\n🔐 Provably Fair: `{result['hash'][:16]}...`"
        return s

    # ---- турниры, бонусы, статистика и т.д. ----
    async def show_tournaments(self, callback: CallbackQuery):
        tours = await Database.get_active_tournaments()
        if not tours:
            text = "🏆 Нет активных турниров"
        else:
            text = "🏆 **Активные турниры**\n\n"
            for t in tours:
                end = datetime.fromisoformat(t['end_date'])
                left = end - datetime.now()
                hours = left.seconds // 3600
                minutes = (left.seconds // 60) % 60
                text += f"**{t['name']}**\nПриз: {t['prize_pool']} ⭐\nИгра: {t['game_type']}\nОсталось: {hours}ч {minutes}м\n\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    async def show_bonuses(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        can, streak, bonus = await Database.get_daily_reward(user_id)
        faucet = int(await Database.get_setting('faucet_amount'))
        cooldown = int(await Database.get_setting('faucet_cooldown')) // 60
        text = (
            f"🎁 **Бонусы**\n\n"
            f"📅 Ежедневный бонус: {bonus} ⭐ (серия {streak})\n"
            f"💧 Кран: {faucet} ⭐ каждые {cooldown} мин\n\n"
            f"Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Забрать ежедневный", callback_data="claim_daily"),
             InlineKeyboardButton(text="💧 Забрать кран", callback_data="claim_faucet")],
            [InlineKeyboardButton(text="🎫 Активировать код", callback_data="activate_bonus")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)

    async def claim_daily(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        can, streak, bonus = await Database.get_daily_reward(user_id)
        if not can:
            await callback.answer("❌ Вы уже получили сегодня", show_alert=True)
            return
        await Database.update_balance(user_id, bonus, "Ежедневный бонус")
        await callback.answer(f"✅ Получено {bonus} ⭐! Серия {streak}", show_alert=True)
        await self.show_bonuses(callback)

    async def claim_faucet(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cooldown = int((await db.execute('SELECT value FROM settings WHERE key="faucet_cooldown"')).fetchone()[0])
            cursor = await db.execute('SELECT created_at FROM transactions WHERE user_id=? AND type="faucet" ORDER BY created_at DESC LIMIT 1', (user_id,))
            last = await cursor.fetchone()
            now = datetime.now()
            if last:
                last_time = datetime.fromisoformat(last[0])
                if (now - last_time).total_seconds() < cooldown:
                    left = cooldown - (now - last_time).total_seconds()
                    await callback.answer(f"❌ Подождите {int(left//60)} мин", show_alert=True)
                    return
            amount = int((await db.execute('SELECT value FROM settings WHERE key="faucet_amount"')).fetchone()[0])
            await db.execute('UPDATE users SET balance = balance + ? WHERE user_id=?', (amount, user_id))
            await db.execute('INSERT INTO transactions (transaction_id, user_id, amount, type, status, description) VALUES (?,?,?,?,?,?)',
                           (str(uuid.uuid4()), user_id, amount, 'faucet', 'completed', 'Кран'))
            await db.commit()
        await callback.answer(f"✅ Получено {amount} ⭐!", show_alert=True)
        await self.show_bonuses(callback)

    async def show_stats(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        top = await Database.get_top_players(5)
        text = f"📊 **Статистика**\n\nВаша:\nИгр: {user['total_bets']}\nПобед: {user['total_wins']}\nПрофит: ...\n\nТоп-5:\n"
        for i,p in enumerate(top,1):
            text += f"{i}. {p['username'] or 'Аноним'}: {p['total_wins']} побед\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    async def show_referrals(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        bot_user = await bot.me()
        link = f"https://t.me/{bot_user.username}?start={user['referral_code']}"
        text = f"👥 **Рефералы**\n\nВаша ссылка:\n`{link}`\n\nПриглашайте друзей и получайте бонусы!"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    async def show_settings(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        lang = user.get('language', 'ru')
        text = f"⚙️ **Настройки**\n\nЯзык: {'🇷🇺 Русский' if lang=='ru' else '🇬🇧 English'}\nVIP уровень: {user['vip_level']} (опыт {user['experience']})\n\nИграйте больше, чтобы повысить VIP!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Сменить язык", callback_data="change_language")],
            [InlineKeyboardButton(text="🔐 Provably Fair", callback_data="provably_fair_info")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)

    async def change_language(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        new_lang = 'en' if user['language'] == 'ru' else 'ru'
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('UPDATE users SET language = ? WHERE user_id = ?', (new_lang, user_id))
            await db.commit()
        await callback.answer(f"Язык изменен на {'English' if new_lang=='en' else 'Русский'}", show_alert=True)
        await self.show_settings(callback)

    async def provably_fair_info(self, callback: CallbackQuery):
        text = "🔐 **Provably Fair**\n\nВсе игры используют криптографическую систему, позволяющую проверить честность каждого раунда. Хеш результата отображается в конце игры."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="settings")]]))

    async def show_history(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM games WHERE user_id = ? ORDER BY created_at DESC LIMIT 10', (user_id,))
            games = await cursor.fetchall()
        text = "📜 **История игр**\n\n"
        if not games:
            text += "Пусто"
        else:
            for g in games:
                g = dict(g)
                em = "✅" if g['profit']>0 else "❌" if g['profit']<0 else "🔄"
                text += f"{em} {g['game_type']}: {g['bet_amount']} ⭐ → {g['win_amount']} ⭐ (профит {g['profit']})\n{g['created_at']}\n\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    # ---- методы для редактирования слотов ----
    async def ask_slot_edit(self, callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        slot_type = data.get("slot_type")
        settings = await Database.get_game_settings(slot_type)
        text = (
            f"🎰 Редактирование {slot_type}\n\n"
            f"Текущие настройки:\n"
            f"Символы: {settings['symbols']}\n"
            f"Веса: {settings['weights']}\n"
            f"Значения: {settings['values']}\n"
            f"Wild: {settings['wild']}\n"
            f"Scatter: {settings['scatter']}\n"
            f"Множитель фриспинов: {settings['free_spins_mult']}\n"
            f"Вероятность бонус-игры: {settings['bonus_game_prob']}\n"
            f"RTP: {settings['rtp']}\n\n"
            f"Введите новые настройки в формате JSON или измените отдельные параметры через команды."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изменить RTP", callback_data=f"edit_{slot_type}_rtp"),
             InlineKeyboardButton(text="Изменить веса", callback_data=f"edit_{slot_type}_weights")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_slot_edit")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)

# ============================================
# СОЗДАНИЕ ЭКЗЕМПЛЯРА
# ============================================
casino_bot = CasinoBot()

# ============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================
@dp.message(CommandStart())
async def start_command(message: Message):
    await casino_bot.cmd_start(message)

@dp.message(Command("balance"))
async def balance_command(message: Message):
    await casino_bot.cmd_balance(message.from_user.id, message)

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    await casino_bot.callback_handler(callback, state)

# ---- обработчики ввода ----
@dp.message(BetStates.waiting_for_deposit_amount)
async def handle_deposit(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount < 10 or amount > 10000:
            await message.answer("❌ Сумма от 10 до 10000")
            return
        prices = [LabeledPrice(label="Пополнение", amount=amount)]
        await bot.send_invoice(
            chat_id=message.chat.id,
            title="Пополнение баланса",
            description=f"Пополнение на {amount} ⭐",
            payload=f"deposit_{amount}",
            provider_token="",
            currency="XTR",
            prices=prices
        )
        await state.clear()
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_withdrawal_amount)
async def handle_withdrawal_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        user_id = message.from_user.id
        user = await Database.get_user(user_id)
        min_wd = int(await Database.get_setting('min_withdrawal'))
        if amount < min_wd:
            await message.answer(f"❌ Минимальная сумма {min_wd} ⭐")
            return
        if amount > user['balance']:
            await message.answer("❌ Недостаточно средств")
            return
        await state.update_data(withdrawal_amount=amount)
        await state.set_state(BetStates.waiting_for_withdrawal_address)
        await message.answer("💸 Введите адрес кошелька для вывода:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]]))
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_withdrawal_address)
async def handle_withdrawal_address(message: Message, state: FSMContext):
    address = message.text
    user_id = message.from_user.id
    data = await state.get_data()
    amount = data.get('withdrawal_amount')
    tx_id = await Database.add_transaction(user_id, amount, 'withdrawal', 'pending', f'Вывод на {address}', address)
    await Database.update_balance(user_id, -amount, f'Заявка на вывод {amount}')
    await state.clear()
    await message.answer(f"✅ Заявка создана, ID: {tx_id}")
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, f"💰 Новая заявка на вывод: {user_id} – {amount} ⭐")
        except:
            pass

@dp.message(BetStates.waiting_for_bet)
async def handle_custom_bet(message: Message, state: FSMContext):
    data = await state.get_data()
    game_type = data.get('game_type')
    bet_type = data.get('bet_type')
    mode = data.get('mode')
    risk = data.get('risk')
    mines = data.get('mines', 5)
    difficulty = data.get('difficulty', 'medium')
    picks = data.get('picks', 5)

    text = message.text.strip()
    if game_type == "roulette" and bet_type == "straight":
        parts = text.split()
        if len(parts) != 2:
            await message.answer("❌ Введите число и сумму через пробел")
            return
        try:
            num = int(parts[0])
            bet = int(parts[1])
            if num < 0 or num > 36:
                await message.answer("❌ Число от 0 до 36")
                return
        except:
            await message.answer("❌ Ошибка ввода")
            return
        kwargs = {"bet_type": "straight", "bet_number": num}
    elif game_type == "keno":
        parts = text.split()
        if len(parts) < picks + 1:
            await message.answer(f"❌ Введите {picks} чисел и сумму")
            return
        try:
            nums = [int(x) for x in parts[:picks]]
            bet = int(parts[picks])
            if any(n < 1 or n > 80 for n in nums):
                await message.answer("❌ Числа от 1 до 80")
                return
            if len(set(nums)) != len(nums):
                await message.answer("❌ Числа не должны повторяться")
                return
        except:
            await message.answer("❌ Ошибка ввода")
            return
        kwargs = {"picks": nums}
    else:
        try:
            bet = int(text)
        except:
            await message.answer("❌ Введите число")
            return
        kwargs = {}

    if bet < MIN_BET or bet > MAX_BET:
        await message.answer(f"❌ Ставка от {MIN_BET} до {MAX_BET}")
        return

    await state.clear()

    user = await Database.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден. /start")
        return
    if user['balance'] < bet:
        await message.answer(f"❌ Недостаточно средств. Баланс: {user['balance']} ⭐")
        return

    if game_type == "dice":
        kwargs["mode"] = mode or "single"
    elif game_type == "plinko":
        kwargs["risk"] = risk or "medium"
    elif game_type == "mines":
        kwargs["mines"] = mines
        kwargs["difficulty"] = difficulty

    await casino_bot.play_game(
        CallbackQuery(id='', from_user=message.from_user, message=message, data=f'play_{game_type}_{bet}'),
        game_type, bet, **kwargs
    )

@dp.message(BetStates.waiting_for_bonus_code)
async def handle_bonus_code(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get('admin_action') == "create_bonus":
        code = message.text.upper()
        await state.update_data(bonus_code=code)
        await state.set_state(BetStates.waiting_for_bonus_code_amount)
        await message.answer("🎁 Введите сумму бонуса:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonuses_menu")]]))
    else:
        code = message.text.upper()
        res = await Database.use_bonus_code(code, message.from_user.id)
        if res is None:
            await message.answer("❌ Неверный код")
        elif res == -1:
            await message.answer("❌ Код уже использован")
        else:
            await message.answer(f"✅ Получено {res} ⭐!")
        await state.clear()

@dp.message(BetStates.waiting_for_bonus_code_amount)
async def handle_bonus_code_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        await state.update_data(bonus_amount=amount)
        await state.set_state(BetStates.waiting_for_bonus_code_uses)
        await message.answer("🎁 Введите макс. количество использований (0 безлимит):")
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_bonus_code_uses)
async def handle_bonus_code_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text)
        if uses < 0:
            await message.answer("❌ Не может быть отрицательным")
            return
        await state.update_data(bonus_uses=uses)
        await state.set_state(BetStates.waiting_for_bonus_code_expiry)
        await message.answer("🎁 Введите срок действия в часах (0 бессрочно):")
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_bonus_code_expiry)
async def handle_bonus_code_expiry(message: Message, state: FSMContext):
    try:
        hours = int(message.text)
        data = await state.get_data()
        code = data['bonus_code']
        amount = data['bonus_amount']
        uses = data['bonus_uses']
        expiry = None
        if hours > 0:
            expiry = datetime.now() + timedelta(hours=hours)
        await Database.create_bonus_code(code, amount, uses, expiry, message.from_user.id)
        await state.clear()
        await message.answer(f"✅ Код {code} создан")
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_user_id)
async def handle_user_id(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get('admin_action')
    if action == "search_user":
        try:
            uid = int(message.text)
            user = await Database.get_user(uid)
            if not user:
                await message.answer("❌ Не найден")
            else:
                text = f"ID: {uid}\nUsername: @{user['username']}\nБаланс: {user['balance']}\nVIP: {user['vip_level']}\nБан: {user['is_banned']}"
                await message.answer(text)
        except:
            await message.answer("❌ Введите ID")
    elif action == "search_username":
        user = await Database.get_user_by_username(message.text)
        if not user:
            await message.answer("❌ Не найден")
        else:
            await message.answer(f"ID: {user['user_id']}, баланс: {user['balance']}")
    elif action == "balance_change":
        try:
            uid = int(message.text)
            await state.update_data(target_user=uid)
            await state.set_state(BetStates.waiting_for_balance_amount)
            await message.answer("💰 Введите сумму (может быть отрицательной):")
        except:
            await message.answer("❌ Введите ID")
    else:
        await state.clear()
        await message.answer("❌ Неизвестное действие")

@dp.message(BetStates.waiting_for_balance_amount)
async def handle_balance_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['target_user']
        if await Database.update_balance(uid, amount, f"Админ {message.from_user.id}"):
            await message.answer(f"✅ Баланс {uid} изменен на {amount}")
        else:
            await message.answer("❌ Ошибка")
    except:
        await message.answer("❌ Введите число")
    await state.clear()

@dp.message(BetStates.waiting_for_rtp_change)
async def handle_rtp_change(message: Message, state: FSMContext):
    try:
        rtp = float(message.text)
        if rtp < 0 or rtp > 200:
            await message.answer("❌ RTP от 0 до 200%")
            return
        data = await state.get_data()
        game = data['game_type']
        await Database.update_rtp_settings(game, rtp, message.from_user.id)
        await message.answer(f"✅ RTP для {game} = {rtp}%")
    except:
        await message.answer("❌ Введите число")
    await state.clear()

@dp.message(BetStates.waiting_for_tournament_name)
async def handle_tournament_name(message: Message, state: FSMContext):
    await state.update_data(tname=message.text)
    await state.set_state(BetStates.waiting_for_tournament_prize)
    await message.answer("🏆 Введите призовой фонд:")

@dp.message(BetStates.waiting_for_tournament_prize)
async def handle_tournament_prize(message: Message, state: FSMContext):
    try:
        prize = int(message.text)
        await state.update_data(prize=prize)
        await state.set_state(BetStates.waiting_for_tournament_duration)
        await message.answer("🏆 Введите длительность (часы):")
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_tournament_duration)
async def handle_tournament_duration(message: Message, state: FSMContext):
    try:
        hours = int(message.text)
        await state.update_data(duration=hours)
        await state.set_state(BetStates.waiting_for_tournament_min_bet)
        await message.answer("🏆 Введите минимальную ставку:")
    except:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_tournament_min_bet)
async def handle_tournament_min_bet(message: Message, state: FSMContext):
    try:
        minbet = int(message.text)
        data = await state.get_data()
        tid = await Database.create_tournament(
            data['tname'], data['prize'], "any",
            data['duration'], minbet, message.from_user.id
        )
        await message.answer(f"✅ Турнир {tid} создан")
    except:
        await message.answer("❌ Ошибка")
    await state.clear()

@dp.message(BetStates.waiting_for_broadcast_message)
async def handle_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = message.text
    users = await Database.get_all_users(limit=10000)
    success = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Разослано {success} пользователям")
    await state.clear()

@dp.message(BetStates.waiting_for_admin_action)
async def handle_admin_setting(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get('admin_action')
    if action and action.startswith("setting_"):
        setting = action.replace("setting_", "")
        try:
            val = message.text
            if setting == "faucet_cooldown":
                val = str(int(val)*60)
            await Database.update_setting(setting, val)
            await message.answer(f"✅ {setting} обновлен")
        except:
            await message.answer("❌ Ошибка")
    await state.clear()

# ============================================
# ПЛАТЕЖИ
# ============================================
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    amount = message.successful_payment.total_amount
    await Database.update_balance(message.from_user.id, amount, "Пополнение Stars")
    await message.answer(f"✅ Пополнено {amount} ⭐")

# ============================================
# ФОНОВЫЕ ЗАДАЧИ
# ============================================
async def check_tournaments_background():
    while True:
        await Database.check_expired_tournaments()
        await asyncio.sleep(600)

async def backup_database_background():
    while True:
        await asyncio.sleep(21600)
        if os.path.exists(DATABASE_PATH):
            import shutil
            shutil.copy2(DATABASE_PATH, f"/tmp/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            logger.info("Бэкап создан")

async def cleanup_old_games_background():
    while True:
        await asyncio.sleep(86400)
        month_ago = datetime.now() - timedelta(days=30)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('DELETE FROM games WHERE created_at < ?', (month_ago,))
            await db.commit()

async def update_vip_status_background():
    while True:
        await asyncio.sleep(86400)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE users SET vip_level = CASE
                    WHEN experience >= 10000 THEN 5
                    WHEN experience >= 5000 THEN 4
                    WHEN experience >= 2000 THEN 3
                    WHEN experience >= 500 THEN 2
                    WHEN experience >= 100 THEN 1
                    ELSE 0
                END
            ''')
            await db.commit()

# ============================================
# HTTP-СЕРВЕР ДЛЯ RENDER
# ============================================
async def run_http_server():
    app = web.Application()
    async def handle(request):
        return web.Response(text="Mega Casino Bot is running")
    app.router.add_get('/', handle)
    app.router.add_get('/health', handle)
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"HTTP сервер на порту {port}")

# ============================================
# ЗАПУСК
# ============================================
async def main():
    await init_db()
    asyncio.create_task(run_http_server())
    asyncio.create_task(check_tournaments_background())
    asyncio.create_task(backup_database_background())
    asyncio.create_task(cleanup_old_games_background())
    asyncio.create_task(update_vip_status_background())
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
