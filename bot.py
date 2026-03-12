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
import math
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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
MAX_WIN_MULTIPLIER = 10000  # максимальный выигрыш в x от ставки

print("="*60 + "\n")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

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
        'error': '❌ Ошибка. Попробуйте снова.',
        'buy_bonus': '💰 Купить бонусную игру',
        'spins_left': 'Осталось спинов',
        'total_win': 'Общий выигрыш',
        'wild_multiplier': 'Множитель Wild',
        'confirm': '✅ Подтвердить',
        'reject': '❌ Отклонить',
        'withdrawal_request': '💸 Заявка на вывод',
        'faucet_claimed': '✅ Звёзды получены',
        'provably_fair': '🔐 Provably Fair',
        'disable_pf': 'Отключить Provably Fair',
        'wager_required': '🎯 Требуется отыгрыш',
        'wager_progress': 'Прогресс отыгрыша'
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
        'error': '❌ Error. Try again.',
        'buy_bonus': '💰 Buy bonus game',
        'spins_left': 'Spins left',
        'total_win': 'Total win',
        'wild_multiplier': 'Wild multiplier',
        'confirm': '✅ Confirm',
        'reject': '❌ Reject',
        'withdrawal_request': '💸 Withdrawal request',
        'faucet_claimed': '✅ Stars claimed',
        'provably_fair': '🔐 Provably Fair',
        'disable_pf': 'Disable Provably Fair',
        'wager_required': '🎯 Wagering required',
        'wager_progress': 'Wagering progress'
    }
}

def get_text(key: str, lang: str = 'ru') -> str:
    return LANGUAGES.get(lang, LANGUAGES['ru']).get(key, key)

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
    waiting_for_bonus_price = State()
    waiting_for_bonus_prob = State()
    waiting_for_wager_multiplier = State()
    waiting_for_blackjack_action = State()

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance INTEGER DEFAULT 0,
                bonus_balance INTEGER DEFAULT 0,
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
                is_admin INTEGER DEFAULT 0,
                pf_enabled INTEGER DEFAULT 1
            )
        ''')
        
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
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rtp_settings (
                game_type TEXT PRIMARY KEY,
                base_rtp REAL DEFAULT 76.82,
                current_rtp REAL DEFAULT 76.82,
                min_rtp REAL DEFAULT 0.0,
                max_rtp REAL DEFAULT 200.0,
                volatility REAL DEFAULT 0.15,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_by INTEGER
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS jackpot (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                amount INTEGER DEFAULT 0,
                last_win TIMESTAMP,
                last_winner INTEGER
            )
        ''')
        await db.execute('INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 1000)')
        
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
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
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
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tournament_participants (
                tournament_id INTEGER,
                user_id INTEGER,
                score INTEGER DEFAULT 0,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tournament_id, user_id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS daily_rewards (
                user_id INTEGER,
                last_claim TIMESTAMP,
                streak INTEGER DEFAULT 0,
                PRIMARY KEY (user_id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        default_settings = [
            ('faucet_amount', '10'),
            ('faucet_cooldown', '3600'),
            ('min_withdrawal', '100'),
            ('withdrawal_fee', '0'),
            ('welcome_bonus', '100'),
            ('referral_bonus', '50'),
            ('maintenance_mode', 'false'),
            ('wager_multiplier', '35'),
            ('wager_games', 'dice,roulette,mines,plinko,keno,doghouse,sugarrush,blackjack')
        ]
        
        for key, value in default_settings:
            await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS game_settings (
                game_type TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL
            )
        ''')

        default_slot_settings = {
            "symbols": ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐", "🎰"],
            "weights": [100, 80, 60, 40, 20, 10, 5, 2],
            "values": [2, 3, 4, 5, 8, 12, 20, 30],
            "wild": "⭐",
            "scatter": "🎰",
            "free_spins_mult": 10,
            "bonus_game_prob": 0.01,
            "wild_multipliers": [2, 3, 4, 5],
            "rtp": RTP_ACTUAL,
            "volatility": 0.15,
            "max_mult": 1000
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "slot"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('slot', json.dumps(default_slot_settings)))

        doghouse_settings = {
            "reels": 5,
            "rows": 3,
            "symbols": ["🐶", "🐩", "🐕", "🏠", "💎", "7️⃣", "⭐", "🎰"],
            "weights": [100, 80, 60, 40, 20, 10, 5, 2],
            "values": [2, 3, 4, 5, 8, 12, 20, 30],
            "wild": "⭐",
            "scatter": "🏠",
            "free_spins_mult": 10,
            "bonus_game": "sticky_wild",
            "wild_multipliers": [2, 3, 4, 5],
            "rtp": RTP_ACTUAL,
            "volatility": 0.2,
            "max_mult": 500
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "doghouse"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('doghouse', json.dumps(doghouse_settings)))

        sugarrush_settings = {
            "reels": 7,
            "rows": 7,
            "symbols": ["🍬", "🍭", "🍫", "🍩", "🍪", "🧁", "🍰", "🎂"],
            "weights": [100, 80, 60, 40, 20, 10, 5, 2],
            "values": [2, 3, 4, 5, 8, 12, 20, 30],
            "wild": "🍬",
            "scatter": "🍭",
            "free_spins_mult": 10,
            "bonus_game": "cascade",
            "cascade_multiplier": 1.5,
            "rtp": RTP_ACTUAL,
            "volatility": 0.25,
            "max_mult": 2000
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "sugarrush"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('sugarrush', json.dumps(sugarrush_settings)))

        blackjack_settings = {
            "decks": 4,
            "blackjack_payout": 1.5,
            "rtp": RTP_ACTUAL,
            "volatility": 0.1,
            "max_mult": 3
        }
        cursor = await db.execute('SELECT 1 FROM game_settings WHERE game_type = "blackjack"')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO game_settings (game_type, settings_json) VALUES (?, ?)',
                             ('blackjack', json.dumps(blackjack_settings)))

        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus_shop (
                game_type TEXT PRIMARY KEY,
                price INTEGER DEFAULT 100,
                enabled INTEGER DEFAULT 1
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus_wilds (
                user_id INTEGER,
                game_type TEXT,
                multiplier REAL DEFAULT 1.0,
                spins_left INTEGER DEFAULT 0,
                total_win INTEGER DEFAULT 0,
                sticky_positions TEXT,
                PRIMARY KEY (user_id, game_type)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS wager_requirements (
                wager_id TEXT PRIMARY KEY,
                user_id INTEGER,
                bonus_amount INTEGER,
                total_to_wager INTEGER,
                wagered_amount INTEGER DEFAULT 0,
                eligible_games TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS blackjack_sessions (
                user_id INTEGER PRIMARY KEY,
                game_data TEXT,
                bet INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.commit()
    logger.info("✅ База данных инициализирована")

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
                    (user_id, username, first_name, last_name, referral_code, referred_by, balance, pf_enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
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

    @staticmethod
    async def get_bonus_price(game_type: str) -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT price FROM bonus_shop WHERE game_type = ?', (game_type,))
            row = await cursor.fetchone()
            return row[0] if row else 100

    @staticmethod
    async def set_bonus_price(game_type: str, price: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('INSERT OR REPLACE INTO bonus_shop (game_type, price, enabled) VALUES (?, ?, 1)',
                             (game_type, price))
            await db.commit()

    @staticmethod
    async def get_bonus_wild(user_id: int, game_type: str) -> Dict:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM bonus_wilds WHERE user_id = ? AND game_type = ?',
                                      (user_id, game_type))
            row = await cursor.fetchone()
            return dict(row) if row else {'multiplier': 1.0, 'spins_left': 0, 'total_win': 0, 'sticky_positions': '[]'}

    @staticmethod
    async def update_bonus_wild(user_id: int, game_type: str, multiplier: float, spins_left: int, total_win: int, sticky_positions: List = None):
        sticky_json = json.dumps(sticky_positions) if sticky_positions else '[]'
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bonus_wilds (user_id, game_type, multiplier, spins_left, total_win, sticky_positions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, game_type, multiplier, spins_left, total_win, sticky_json))
            await db.commit()

    @staticmethod
    async def clear_bonus_wild(user_id: int, game_type: str):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('DELETE FROM bonus_wilds WHERE user_id = ? AND game_type = ?', (user_id, game_type))
            await db.commit()

    @staticmethod
    async def save_blackjack_session(user_id: int, game_data: Dict, bet: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO blackjack_sessions (user_id, game_data, bet, created_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, json.dumps(game_data), bet, datetime.now()))
            await db.commit()

    @staticmethod
    async def get_blackjack_session(user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM blackjack_sessions WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if row:
                return {'game_data': json.loads(row['game_data']), 'bet': row['bet']}
            return None

    @staticmethod
    async def delete_blackjack_session(user_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('DELETE FROM blackjack_sessions WHERE user_id = ?', (user_id,))
            await db.commit()

class RTPManager:
    """Управление возвратом игроку с учётом истории и ограничений"""
    
    @staticmethod
    async def calculate_win(game_type: str, base_win: int, bet: int, user_id: int, max_mult: int) -> int:
        # Получаем настройки RTP
        settings = await Database.get_rtp_settings(game_type)
        target_rtp = settings.get('current_rtp', RTP_ACTUAL) / 100.0
        volatility = settings.get('volatility', 0.15)

        # Получаем историю пользователя по этой игре
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT COUNT(*), SUM(win_amount) FROM games
                WHERE user_id = ? AND game_type = ?
            ''', (user_id, game_type))
            row = await cursor.fetchone()
            total_bets = row[0] or 0
            total_wins = row[1] or 0

        # Генерация нормального распределения
        u1 = random.random()
        u2 = random.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        rtp_factor = target_rtp + volatility * z
        rtp_factor = max(0.3, min(2.5, rtp_factor))

        # Коррекция на основе истории (чтобы на дистанции сходилось к target_rtp)
        if total_bets > 10:
            current_rtp = total_wins / total_bets if total_bets > 0 else 0
            deviation = target_rtp - current_rtp
            correction = 1.0 + (deviation * 0.3)
            rtp_factor *= correction

        # Применяем ограничение максимального множителя
        final_win = int(base_win * rtp_factor)
        max_allowed = bet * max_mult
        if final_win > max_allowed:
            final_win = max_allowed

        logger.info(f"RTP {game_type}: base={base_win}, factor={rtp_factor:.3f}, final={final_win}, max={max_allowed}")
        return final_win

class WagerManager:
    @staticmethod
    async def add_bonus(user_id: int, amount: int, description: str = ""):
        wager_mult = int(await Database.get_setting('wager_multiplier') or 35)
        eligible_games = await Database.get_setting('wager_games') or 'dice,roulette,mines,plinko,keno,doghouse,sugarrush,blackjack'

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('UPDATE users SET bonus_balance = bonus_balance + ? WHERE user_id = ?', (amount, user_id))
            wager_id = str(uuid.uuid4())
            total_to_wager = amount * wager_mult
            await db.execute('''
                INSERT INTO wager_requirements (wager_id, user_id, bonus_amount, total_to_wager, eligible_games, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            ''', (wager_id, user_id, amount, total_to_wager, eligible_games))
            await db.commit()

        logger.info(f"➕ Бонус {amount} для {user_id}, требуется отыграть {total_to_wager}")

    @staticmethod
    async def process_bet(user_id: int, game_type: str, bet_amount: int) -> Tuple[int, int]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT balance, bonus_balance FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if not row:
                return 0, 0
            balance, bonus_balance = row

            bet_from_bonus = min(bet_amount, bonus_balance)
            bet_from_real = bet_amount - bet_from_bonus

            if bet_from_real > balance:
                return 0, 0

            new_bonus = bonus_balance - bet_from_bonus
            new_balance = balance - bet_from_real
            await db.execute('UPDATE users SET bonus_balance = ?, balance = ? WHERE user_id = ?',
                           (new_bonus, new_balance, user_id))

            if bet_from_bonus > 0:
                await WagerManager._update_progress(db, user_id, game_type, bet_from_bonus)

            await db.commit()
            return bet_from_bonus, bet_from_real

    @staticmethod
    async def _update_progress(db, user_id: int, game_type: str, bet_amount: int):
        eligible_games = await Database.get_setting('wager_games')
        if game_type not in eligible_games.split(','):
            return

        cursor = await db.execute('''
            SELECT wager_id, total_to_wager, wagered_amount FROM wager_requirements
            WHERE user_id = ? AND status = 'active'
        ''', (user_id,))
        rows = await cursor.fetchall()
        for wager_id, total, wagered in rows:
            new_wagered = wagered + bet_amount
            if new_wagered >= total:
                await db.execute("UPDATE wager_requirements SET status = 'completed', completed_at = ? WHERE wager_id = ?",
                               (datetime.now(), wager_id))
                cursor2 = await db.execute('SELECT bonus_balance FROM users WHERE user_id = ?', (user_id,))
                bonus_left = (await cursor2.fetchone())[0]
                await db.execute('UPDATE users SET balance = balance + ?, bonus_balance = 0 WHERE user_id = ?',
                               (bonus_left, user_id))
            else:
                await db.execute('UPDATE wager_requirements SET wagered_amount = ? WHERE wager_id = ?',
                               (new_wagered, wager_id))

    @staticmethod
    async def get_status(user_id: int) -> Dict:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT bonus_amount, total_to_wager, wagered_amount FROM wager_requirements
                WHERE user_id = ? AND status = 'active'
            ''', (user_id,))
            rows = await cursor.fetchall()
            if not rows:
                return {}
            bonus, total, wagered = rows[0]
            return {
                'bonus': bonus,
                'total': total,
                'wagered': wagered,
                'remaining': total - wagered,
                'progress': round(wagered / total * 100, 1)
            }

class ProvablyFair:
    @staticmethod
    def generate_seeds() -> Tuple[str, str]:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        return server_seed, client_seed

    @staticmethod
    def get_hash(server_seed: str, client_seed: str, nonce: int) -> str:
        combined = f"{server_seed}:{client_seed}:{nonce}"
        return hashlib.sha256(combined.encode()).hexdigest()

    @staticmethod
    def get_random_number(seed: str, min_val: int, max_val: int) -> int:
        hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        return min_val + (hash_val % (max_val - min_val + 1))

class BaseGame:
    def __init__(self, game_type: str):
        self.game_type = game_type
        self.settings = {}

    async def load_settings(self):
        self.settings = await Database.get_game_settings(self.game_type)

    async def get_max_mult(self) -> int:
        return self.settings.get('max_mult', 1000)

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        raise NotImplementedError

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        raise NotImplementedError

    async def calculate_win(self, bet: int, result: Dict, user_id: int) -> int:
        base_win = self.calculate_base_win(bet, result)
        max_mult = await self.get_max_mult()
        return await RTPManager.calculate_win(self.game_type, base_win, bet, user_id, max_mult)

class DiceGame(BaseGame):
    def __init__(self):
        super().__init__("dice")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "single": {1:6, 2:3, 3:2, 4:1.5, 5:1.2, 6:1},
                "double": {2:12,3:6,4:4,5:3,6:2,7:1.5,8:2,9:3,10:4,11:6,12:12},
                "max_mult": 12
            }

    def generate_result(self, bet: int, user_id: int = None, mode: str = "single") -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        if mode == "single":
            seed = ProvablyFair.get_hash(server_seed, client_seed, nonce)
            result = ProvablyFair.get_random_number(seed, 1, 6)
            base_mult = self.settings['single'][result]
        else:
            seed1 = ProvablyFair.get_hash(server_seed, client_seed, nonce)
            seed2 = ProvablyFair.get_hash(server_seed, client_seed, nonce+1)
            d1 = ProvablyFair.get_random_number(seed1, 1, 6)
            d2 = ProvablyFair.get_random_number(seed2, 1, 6)
            result = d1 + d2
            base_mult = self.settings['double'][result]

        return {
            "result": result,
            "base_mult": base_mult,
            "mode": mode,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["base_mult"])

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
                "split": 18,
                "street": 12,
                "corner": 9,
                "sixline": 6,
                "column": 3,
                "dozen": 3,
                "red": 2,
                "black": 2,
                "even": 2,
                "odd": 2,
                "low": 2,
                "high": 2,
                "max_mult": 36
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)
        seed = ProvablyFair.get_hash(server_seed, client_seed, nonce)
        number = ProvablyFair.get_random_number(seed, 0, 36)
        return {
            "number": number,
            "color": self.colors[number],
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": seed
        }

    def calculate_base_win(self, bet: int, result: Dict, bet_type: str, bet_number: int = None) -> int:
        num = result["number"]
        if bet_type == "straight" and bet_number == num:
            mult = self.settings['straight']
        elif bet_type == "split" and bet_number:
            if abs(bet_number - num) in [1, 3]:
                mult = self.settings['split']
            else:
                return 0
        elif bet_type == "street" and bet_number:
            if (num - 1) // 3 == (bet_number - 1) // 3:
                mult = self.settings['street']
            else:
                return 0
        elif bet_type == "corner" and bet_number:
            if num in [bet_number, bet_number+1, bet_number+3, bet_number+4]:
                mult = self.settings['corner']
            else:
                return 0
        elif bet_type == "sixline" and bet_number:
            if (num - 1) // 3 in [bet_number, bet_number+1]:
                mult = self.settings['sixline']
            else:
                return 0
        elif bet_type == "column" and bet_number:
            columns = {
                1: [1,4,7,10,13,16,19,22,25,28,31,34],
                2: [2,5,8,11,14,17,20,23,26,29,32,35],
                3: [3,6,9,12,15,18,21,24,27,30,33,36]
            }
            if num in columns.get(bet_number, []):
                mult = self.settings['column']
            else:
                return 0
        elif bet_type == "dozen" and bet_number:
            dozens = {1: range(1,13), 2: range(13,25), 3: range(25,37)}
            if num in dozens.get(bet_number, []):
                mult = self.settings['dozen']
            else:
                return 0
        elif bet_type == "red" and result["color"] == "red":
            mult = self.settings['red']
        elif bet_type == "black" and result["color"] == "black":
            mult = self.settings['black']
        elif bet_type == "even" and num > 0 and num % 2 == 0:
            mult = self.settings['even']
        elif bet_type == "odd" and num % 2 == 1:
            mult = self.settings['odd']
        elif bet_type == "low" and 1 <= num <= 18:
            mult = self.settings['low']
        elif bet_type == "high" and 19 <= num <= 36:
            mult = self.settings['high']
        else:
            return 0

        return bet * mult

class MinesGame(BaseGame):
    def __init__(self):
        super().__init__("mines")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "gold_bonus": 0.1,
                "difficulty_mult": {"easy": 0.8, "medium": 1.0, "hard": 1.2, "extreme": 1.5},
                "max_mult": 1000
            }

    def generate_result(self, bet: int, user_id: int = None, mines: int = 3, difficulty: str = "medium") -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        total_cells = 25
        all_cells = list(range(total_cells))
        mine_positions = []
        for i in range(mines):
            seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i)
            idx = ProvablyFair.get_random_number(seed, 0, len(all_cells)-1)
            mine_positions.append(all_cells.pop(idx))

        gold_positions = []
        for i in range(2):
            if all_cells:
                seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + mines + i)
                idx = ProvablyFair.get_random_number(seed, 0, len(all_cells)-1)
                gold_positions.append(all_cells.pop(idx))

        return {
            "mine_positions": mine_positions,
            "gold_positions": gold_positions,
            "mines": mines,
            "difficulty": difficulty,
            "difficulty_mult": self.settings['difficulty_mult'].get(difficulty, 1.0),
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict, revealed: List[int]) -> int:
        if not revealed:
            return 0
        for cell in revealed:
            if cell in result["mine_positions"]:
                return 0

        total_cells = 25
        mines = result["mines"]
        safe = total_cells - mines
        base_mult = safe / (safe - len(revealed) + 1)
        gold_bonus = 1 + self.settings.get('gold_bonus', 0.1) * sum(1 for c in revealed if c in result["gold_positions"])
        diff_mult = result["difficulty_mult"]
        return int(bet * base_mult * gold_bonus * diff_mult)

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
                "max_mult": 33
            }

    def generate_result(self, bet: int, user_id: int = None, risk: str = "medium") -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        rows = 16
        pos = rows / 2
        for step in range(rows):
            seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + step)
            direction = ProvablyFair.get_random_number(seed, 0, 1)
            if direction == 0:
                pos -= 0.5
            else:
                pos += 0.5

        final = int(round(pos))
        final = max(0, min(rows-1, final))
        base_mult = self.settings[risk][final]

        return {
            "final_position": final,
            "base_mult": base_mult,
            "risk": risk,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["base_mult"])

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
                "max_mult": 15000
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        nums = list(range(1,81))
        winning = []
        for i in range(20):
            seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i)
            idx = ProvablyFair.get_random_number(seed, 0, len(nums)-1)
            winning.append(nums.pop(idx))

        return {
            "winning": winning,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict, picks: List[int]) -> int:
        winning = result["winning"]
        matches = sum(1 for p in picks if p in winning)
        cnt = len(picks)
        payouts = self.settings['payouts']
        if cnt in payouts and matches in payouts[cnt]:
            mult = payouts[cnt][matches]
            return bet * mult
        return 0

class BlackjackGame(BaseGame):
    def __init__(self):
        super().__init__("blackjack")
        self.suits = ["♠", "♥", "♦", "♣"]
        self.ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        self.values = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":10,"Q":10,"K":10,"A":11}

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "decks": 4,
                "blackjack_payout": 1.5,
                "max_mult": 3
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)
        deck = [(rank, suit) for suit in self.suits for rank in self.ranks] * self.settings['decks']
        shuffled = self._shuffle_deck(deck, server_seed, client_seed, nonce)
        player_hand = [shuffled[0], shuffled[2]]
        dealer_hand = [shuffled[1], shuffled[3]]
        remaining = shuffled[4:]
        player_score = self._hand_score(player_hand)
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
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def _shuffle_deck(self, deck, server_seed, client_seed, nonce):
        shuffled = deck.copy()
        for i in range(len(shuffled)-1, 0, -1):
            seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i)
            j = ProvablyFair.get_random_number(seed, 0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled

    def _hand_score(self, hand):
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
        score = self._hand_score(dealer_hand)
        while score < 17 and deck:
            dealer_hand.append(deck.pop(0))
            score = self._hand_score(dealer_hand)
        return dealer_hand

    def calculate_base_win(self, bet: int, player_hand, dealer_hand) -> int:
        player_score = self._hand_score(player_hand)
        dealer_score = self._hand_score(dealer_hand)
        if player_score > 21:
            return 0
        if dealer_score > 21:
            return bet * 2
        if player_score > dealer_score:
            return bet * 2
        if player_score == dealer_score:
            return bet
        return 0

class DogHouseGame(BaseGame):
    def __init__(self):
        super().__init__("doghouse")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "reels": 5,
                "rows": 3,
                "symbols": ["🐶", "🐩", "🐕", "🏠", "💎", "7️⃣", "⭐", "🎰"],
                "weights": [100, 80, 60, 40, 20, 10, 5, 2],
                "values": [2, 3, 4, 5, 8, 12, 20, 30],
                "wild": "⭐",
                "scatter": "🏠",
                "free_spins_mult": 10,
                "bonus_game": "sticky_wild",
                "wild_multipliers": [2, 3, 4, 5],
                "max_mult": 500
            }
        cum = 0
        self.cum_weights = []
        for w in self.settings['weights']:
            cum += w
            self.cum_weights.append(cum)
        self.total_weight = cum

    def generate_result(self, bet: int, user_id: int = None, force_bonus: bool = False) -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        rows, cols = self.settings['rows'], self.settings['reels']
        matrix = []
        for i in range(rows):
            row = []
            for j in range(cols):
                seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i*cols + j)
                r = ProvablyFair.get_random_number(seed, 1, self.total_weight)
                for idx, cw in enumerate(self.cum_weights):
                    if r <= cw:
                        symbol_index = idx
                        break
                row.append(self.settings['symbols'][symbol_index])
            matrix.append(row)

        scatter = self.settings['scatter']
        scatter_count = sum(row.count(scatter) for row in matrix)
        bonus_triggered = force_bonus or (scatter_count >= 3)

        return {
            "matrix": matrix,
            "bonus_triggered": bonus_triggered,
            "scatter_count": scatter_count,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        matrix = result["matrix"]
        wild = self.settings['wild']
        values = self.settings['values']
        symbols = self.settings['symbols']
        win = 0
        for row in matrix:
            if all(s == row[0] or s == wild for s in row):
                main = next(s for s in row if s != wild) if any(s != wild for s in row) else wild
                idx = symbols.index(main)
                mult = values[idx]
                win += bet * mult
        return win

    async def play_bonus_game(self, user_id: int, bet: int) -> int:
        spins = 10
        sticky_positions = []
        total_win = 0
        wild = self.settings['wild']
        rows, cols = self.settings['rows'], self.settings['reels']

        for spin in range(spins):
            server_seed, client_seed = ProvablyFair.generate_seeds()
            nonce = secrets.randbelow(1000000)

            matrix = []
            for i in range(rows):
                row = []
                for j in range(cols):
                    if (i, j) in sticky_positions:
                        row.append(wild)
                    else:
                        seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i*cols + j)
                        r = ProvablyFair.get_random_number(seed, 1, self.total_weight)
                        for idx, cw in enumerate(self.cum_weights):
                            if r <= cw:
                                symbol_index = idx
                                break
                        row.append(self.settings['symbols'][symbol_index])
                matrix.append(row)

            for i in range(rows):
                for j in range(cols):
                    if matrix[i][j] == wild and (i, j) not in sticky_positions:
                        sticky_positions.append((i, j))

            spin_win = 0
            for i in range(rows):
                if all(matrix[i][j] == wild or matrix[i][j] == matrix[i][0] for j in range(cols)):
                    main = next((matrix[i][j] for j in range(cols) if matrix[i][j] != wild), wild)
                    idx = self.settings['symbols'].index(main) if main in self.settings['symbols'] else 0
                    mult = self.settings['values'][idx]
                    spin_win += bet * mult

            sticky_mult = 1 + len(sticky_positions) * 0.2
            if sticky_mult > 3.0:
                sticky_mult = 3.0
            spin_win = int(spin_win * sticky_mult)
            total_win += spin_win

        return total_win

class SugarRushGame(BaseGame):
    def __init__(self):
        super().__init__("sugarrush")

    async def load_settings(self):
        await super().load_settings()
        if not self.settings:
            self.settings = {
                "reels": 7,
                "rows": 7,
                "symbols": ["🍬", "🍭", "🍫", "🍩", "🍪", "🧁", "🍰", "🎂"],
                "weights": [100, 80, 60, 40, 20, 10, 5, 2],
                "values": [2, 3, 4, 5, 8, 12, 20, 30],
                "wild": "🍬",
                "scatter": "🍭",
                "cascade_multiplier": 1.5,
                "max_mult": 2000
            }
        cum = 0
        self.cum_weights = []
        for w in self.settings['weights']:
            cum += w
            self.cum_weights.append(cum)
        self.total_weight = cum

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed, client_seed = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        matrix = self._generate_matrix(server_seed, client_seed, nonce)
        total_win, cascade_count = self._cascade(matrix, bet, server_seed, client_seed, nonce)

        scatter = self.settings['scatter']
        scatter_count = sum(row.count(scatter) for row in matrix)

        return {
            "total_win": total_win,
            "cascade_count": cascade_count,
            "scatter_count": scatter_count,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server_seed, client_seed, nonce)
        }

    def _generate_matrix(self, server_seed, client_seed, nonce):
        rows, cols = self.settings['rows'], self.settings['reels']
        matrix = []
        for i in range(rows):
            row = []
            for j in range(cols):
                seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i*cols + j)
                r = ProvablyFair.get_random_number(seed, 1, self.total_weight)
                for idx, cw in enumerate(self.cum_weights):
                    if r <= cw:
                        symbol_index = idx
                        break
                row.append(self.settings['symbols'][symbol_index])
            matrix.append(row)
        return matrix

    def _find_clusters(self, matrix):
        rows, cols = len(matrix), len(matrix[0])
        visited = [[False]*cols for _ in range(rows)]
        clusters = []
        for i in range(rows):
            for j in range(cols):
                if matrix[i][j] is None or visited[i][j]:
                    continue
                symbol = matrix[i][j]
                if symbol == self.settings['wild']:
                    continue
                queue = [(i,j)]
                cluster = []
                while queue:
                    r,c = queue.pop(0)
                    if visited[r][c]:
                        continue
                    visited[r][c] = True
                    if matrix[r][c] == symbol:
                        cluster.append((r,c))
                        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nr, nc = r+dr, c+dc
                            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc] and matrix[nr][nc] == symbol:
                                queue.append((nr,nc))
                if len(cluster) >= 3:
                    clusters.append(cluster)
        return clusters

    def _apply_gravity(self, matrix):
        rows, cols = len(matrix), len(matrix[0])
        for j in range(cols):
            column = [matrix[i][j] for i in range(rows) if matrix[i][j] is not None]
            column = [None] * (rows - len(column)) + column
            for i in range(rows):
                matrix[i][j] = column[i]
        return matrix

    def _fill_empty(self, matrix, server_seed, client_seed, nonce):
        rows, cols = len(matrix), len(matrix[0])
        for i in range(rows):
            for j in range(cols):
                if matrix[i][j] is None:
                    seed = ProvablyFair.get_hash(server_seed, client_seed, nonce + i*cols + j)
                    r = ProvablyFair.get_random_number(seed, 1, self.total_weight)
                    for idx, cw in enumerate(self.cum_weights):
                        if r <= cw:
                            symbol_index = idx
                            break
                    matrix[i][j] = self.settings['symbols'][symbol_index]

    def _cascade(self, matrix, bet, server_seed, client_seed, nonce):
        total_win = 0
        cascade_count = 0
        multiplier = 1.0

        while True:
            clusters = self._find_clusters(matrix)
            if not clusters:
                break

            cluster_win = 0
            for cluster in clusters:
                symbol = matrix[cluster[0][0]][cluster[0][1]]
                idx = self.settings['symbols'].index(symbol)
                value = self.settings['values'][idx]
                cluster_win += len(cluster) * value * bet

            total_win += int(cluster_win * multiplier)

            for cluster in clusters:
                for (r,c) in cluster:
                    matrix[r][c] = None

            matrix = self._apply_gravity(matrix)
            self._fill_empty(matrix, server_seed, client_seed, nonce + cascade_count)

            multiplier *= self.settings['cascade_multiplier']
            cascade_count += 1

        return total_win, cascade_count

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return result["total_win"]

# ============================================
# ОСНОВНОЙ КЛАСС БОТА
# ============================================
class CasinoBot:
    def __init__(self):
        self.games = {
            "dice": DiceGame(),
            "roulette": RouletteGame(),
            "mines": MinesGame(),
            "plinko": PlinkoGame(),
            "keno": KenoGame(),
            "doghouse": DogHouseGame(),
            "sugarrush": SugarRushGame(),
            "blackjack": BlackjackGame()
        }
        self.active_games = {}      # для mines
        self.bonus_sessions = {}    # для бонусных игр
        logger.info(f"✅ Игры загружены: {list(self.games.keys())}")

    def get_main_keyboard(self, lang: str, user_id: int) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice"),
             InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette")],
            [InlineKeyboardButton(text="💣 Mines", callback_data="game_mines"),
             InlineKeyboardButton(text="📌 Plinko", callback_data="game_plinko")],
            [InlineKeyboardButton(text="🎯 Кено", callback_data="game_keno"),
             InlineKeyboardButton(text="🐶 Dog House", callback_data="game_doghouse")],
            [InlineKeyboardButton(text="🍬 Sugar Rush", callback_data="game_sugarrush"),
             InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_blackjack")],
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

    def get_game_keyboard(self, game_type: str, game_state: Dict = None, lang: str = 'ru') -> InlineKeyboardMarkup:
        buttons = []
        if game_type == "dice":
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
                 InlineKeyboardButton(text="💰 Своя ставка", callback_data="roulette_bet")]
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
                     InlineKeyboardButton(text="💰 Своя ставка", callback_data="mines_bet")]
                ]
        elif game_type == "plinko":
            buttons = [
                [InlineKeyboardButton(text="📌 Низкий риск", callback_data="plinko_low"),
                 InlineKeyboardButton(text="📌 Средний риск", callback_data="plinko_medium")],
                [InlineKeyboardButton(text="📌 Высокий риск", callback_data="plinko_high"),
                 InlineKeyboardButton(text="💰 Своя ставка", callback_data="plinko_bet")]
            ]
        elif game_type == "keno":
            buttons = [
                [InlineKeyboardButton(text="🎯 1 число", callback_data="keno_pick1"),
                 InlineKeyboardButton(text="🎯 3 числа", callback_data="keno_pick3")],
                [InlineKeyboardButton(text="🎯 5 чисел", callback_data="keno_pick5"),
                 InlineKeyboardButton(text="🎯 8 чисел", callback_data="keno_pick8")],
                [InlineKeyboardButton(text="💰 Своя ставка", callback_data="keno_bet")]
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
        elif game_type in ["doghouse", "sugarrush"]:
            buttons = [
                [InlineKeyboardButton(text="🎰 10 ⭐", callback_data=f"play_{game_type}_10"),
                 InlineKeyboardButton(text="🎰 50 ⭐", callback_data=f"play_{game_type}_50")],
                [InlineKeyboardButton(text="🎰 100 ⭐", callback_data=f"play_{game_type}_100"),
                 InlineKeyboardButton(text="🎰 500 ⭐", callback_data=f"play_{game_type}_500")],
                [InlineKeyboardButton(text="💰 Своя ставка", callback_data=f"custom_bet_{game_type}"),
                 InlineKeyboardButton(text=f"🎁 {get_text('buy_bonus', lang)}", callback_data=f"buy_bonus_{game_type}")]
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
             InlineKeyboardButton(text="⚙️ Настройки вейджера", callback_data="admin_wager")],
            [InlineKeyboardButton(text="🏆 Управление турнирами", callback_data="admin_tournaments_menu"),
             InlineKeyboardButton(text="🎁 Бонус коды", callback_data="admin_bonuses_menu")],
            [InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin_withdrawals"),
             InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="⚙️ Настройки казино", callback_data="admin_settings"),
             InlineKeyboardButton(text="📥 Скачать БД", callback_data="admin_download_db")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    async def cmd_start(self, message: Message):
        user_id = message.from_user.id
        await Database.create_user(user_id, message.from_user.username,
                                   message.from_user.first_name, message.from_user.last_name)
        user = await Database.get_user(user_id)
        lang = user.get('language', 'ru')
        text = get_text('welcome', lang) + f"\n{get_text('balance', lang)}: {user['balance']} ⭐"
        if user.get('bonus_balance', 0) > 0:
            text += f"\n🎁 Бонус: {user['bonus_balance']} ⭐ (требуется отыгрыш)"
        await message.answer(text, reply_markup=self.get_main_keyboard(lang, user_id))

    async def cmd_balance(self, user_id: int, message: Message):
        user = await Database.get_user(user_id)
        if not user:
            await message.answer(get_text('user_not_found'))
            return
        lang = user.get('language', 'ru')
        wager_status = await WagerManager.get_status(user_id)
        text = f"{get_text('balance', lang)}: **{user['balance']} ⭐**"
        if user.get('bonus_balance', 0) > 0:
            text += f"\n🎁 Бонус: {user['bonus_balance']} ⭐"
        if wager_status:
            text += f"\n{get_text('wager_required', lang)}: {wager_status['wagered']}/{wager_status['total']} ({wager_status['progress']}%)"
        text += f"\n{get_text('vip_level', lang)}: {user['vip_level']} ({get_text('experience', lang)}: {user['experience']})"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
             InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(text, reply_markup=kb)

    async def callback_handler(self, callback: CallbackQuery, state: FSMContext):
        data = callback.data
        user_id = callback.from_user.id

        user = await Database.get_user(user_id)
        lang = user.get('language', 'ru') if user else 'ru'

        if data == "main_menu":
            await callback.message.edit_text(
                "🎰 **ГЛАВНОЕ МЕНЮ**",
                reply_markup=self.get_main_keyboard(lang, user_id)
            )
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
                f"💸 Введите сумму (доступно: {user['balance']} ⭐):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
                ])
            )
        elif data.startswith("game_"):
            game = data.replace("game_", "")
            if game in self.games:
                await callback.message.edit_text(
                    f"🎮 **{game.upper()}**\nВыберите параметры:",
                    reply_markup=self.get_game_keyboard(game, lang=lang)
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
            await self.play_game(callback, game, bet, lang)
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
        elif data == "dice_single":
            await state.update_data(game_type="dice", mode="single")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲 Введите сумму:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]]))
        elif data == "dice_double":
            await state.update_data(game_type="dice", mode="double")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲🎲 Введите сумму:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]]))
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
            elif bt.startswith("column") or bt.startswith("dozen"):
                await state.update_data(game_type="roulette", bet_type=bt)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎡 Введите сумму ставки на {bt}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]]))
            elif bt in ["red","black","even","odd","low","high"]:
                await state.update_data(game_type="roulette", bet_type=bt)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎡 Введите сумму ставки на {bt}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]]))
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
        elif data.startswith("mines_"):
            parts = data.split("_")
            if len(parts) == 3 and parts[1] in ["easy","medium","hard","extreme"]:
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
                game_data = self.active_games[user_id]
                base_win = self.games["mines"].calculate_base_win(game_data["bet"], game_data["result"], game_data["revealed"])
                if base_win == 0:
                    await callback.answer("❌ Вы проиграли", show_alert=True)
                    del self.active_games[user_id]
                    await callback.message.edit_text(
                        "💥 Вы проиграли!",
                        reply_markup=self.get_game_keyboard("mines", lang=lang)
                    )
                    return
                win = await self.games["mines"].calculate_win(game_data["bet"], {"base_win": base_win}, user_id)
                await Database.update_balance(user_id, win, f"Выигрыш Mines")
                await Database.add_game_history(user_id, "mines", game_data["bet"], win, game_data["result"])
                await Database.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
                del self.active_games[user_id]
                jackpot = await Database.get_jackpot()
                await callback.message.edit_text(
                    f"✅ Вы выиграли {win} ⭐!\n💰 Джекпот: {jackpot} ⭐",
                    reply_markup=self.get_game_keyboard("mines", lang=lang)
                )
            elif data == "mines_new":
                if user_id in self.active_games:
                    del self.active_games[user_id]
                await callback.message.edit_text(
                    "💣 Mines",
                    reply_markup=self.get_game_keyboard("mines", lang=lang)
                )
            elif data.startswith("mine_cell_"):
                cell = int(data.replace("mine_cell_", ""))
                if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game_data = self.active_games[user_id]
                if cell in game_data["revealed"]:
                    await callback.answer("Уже открыто", show_alert=True)
                    return
                game_data["revealed"].append(cell)
                if cell in game_data["result"]["mine_positions"]:
                    del self.active_games[user_id]
                    await Database.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
                    await Database.add_game_history(user_id, "mines", game_data["bet"], 0, game_data["result"])
                    await callback.message.edit_text(
                        "💥 **БАБАХ!** Вы проиграли.",
                        reply_markup=self.get_game_keyboard("mines", lang=lang)
                    )
                else:
                    self.active_games[user_id] = game_data
                    cur_win = self.games["mines"].calculate_base_win(game_data["bet"], game_data["result"], game_data["revealed"])
                    await callback.message.edit_text(
                        f"✅ Безопасно! Текущий выигрыш: {cur_win} ⭐",
                        reply_markup=self.get_game_keyboard("mines", game_data, lang=lang)
                    )
        elif data.startswith("keno_"):
            pk = data.replace("keno_pick", "")
            if pk.isdigit():
                picks = int(pk)
                await state.update_data(game_type="keno", picks=picks)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎯 Введите {picks} чисел от 1 до 80 через пробел и сумму (пример: 5 12 33 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]]))
            elif data == "keno_bet":
                await state.update_data(game_type="keno", picks=5)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("🎯 Введите 5 чисел и сумму (пример: 5 12 33 45 78 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]]))
        elif data.startswith("blackjack_"):
            if data == "blackjack_new":
                if user_id in self.blackjack_games:
                    del self.blackjack_games[user_id]
                await callback.message.edit_text(
                    "🃏 Блэкджек",
                    reply_markup=self.get_game_keyboard("blackjack", lang=lang)
                )
            elif data == "blackjack_hit":
                session = await Database.get_blackjack_session(user_id)
                if not session:
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game_data = session['game_data']
                bet = session['bet']
                if not game_data['deck']:
                    await callback.answer("Колода пуста", show_alert=True)
                    return
                new_card = game_data['deck'].pop(0)
                game_data['player_hand'].append(new_card)
                game_data['player_score'] = self.games["blackjack"]._hand_score(game_data['player_hand'])
                if game_data['player_score'] > 21:
                    await Database.add_game_history(user_id, "blackjack", bet, 0, {"final":"bust"})
                    await Database.delete_blackjack_session(user_id)
                    await callback.message.edit_text(
                        f"❌ **ПЕРЕБОР!**\nВаши карты: {self.format_hand(game_data['player_hand'])} ({game_data['player_score']})\nДилер: {self.format_hand(game_data['dealer_hand'])}",
                        reply_markup=self.get_game_keyboard("blackjack", lang=lang)
                    )
                else:
                    await Database.save_blackjack_session(user_id, game_data, bet)
                    await callback.message.edit_text(
                        f"🃏 Ваши карты: {self.format_hand(game_data['player_hand'])} (очков: {game_data['player_score']})\nДилер: {self.format_hand(game_data['dealer_hand'][:1])} + ?",
                        reply_markup=self.get_game_keyboard("blackjack", {"active":True}, lang=lang)
                    )
            elif data == "blackjack_stand":
                session = await Database.get_blackjack_session(user_id)
                if not session:
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game_data = session['game_data']
                bet = session['bet']
                dealer_hand = game_data['dealer_hand']
                deck = game_data['deck']
                dealer_score = self.games["blackjack"]._hand_score(dealer_hand)
                while dealer_score < 17 and deck:
                    dealer_hand.append(deck.pop(0))
                    dealer_score = self.games["blackjack"]._hand_score(dealer_hand)
                win = self.games["blackjack"].calculate_base_win(bet, game_data['player_hand'], dealer_hand)
                profit = win - bet
                if win > 0:
                    await Database.update_balance(user_id, profit, "Выигрыш блэкджек")
                await Database.add_game_history(user_id, "blackjack", bet, win, {"player":game_data['player_hand'],"dealer":dealer_hand})
                await Database.delete_blackjack_session(user_id)
                await Database.update_jackpot(int(bet * JACKPOT_PERCENT))
                jackpot = await Database.get_jackpot()
                await callback.message.edit_text(
                    f"🃏 Результат:\nВаши: {self.format_hand(game_data['player_hand'])} ({game_data['player_score']})\nДилер: {self.format_hand(dealer_hand)} ({dealer_score})\n\n{'✅' if win>0 else '❌'} Выигрыш: {win} ⭐\n💰 Джекпот: {jackpot} ⭐",
                    reply_markup=self.get_game_keyboard("blackjack", lang=lang)
                )
            else:
                await callback.answer("Неизвестная команда", show_alert=True)
        elif data.startswith("buy_bonus_"):
            game_type = data.replace("buy_bonus_", "")
            price = await Database.get_bonus_price(game_type)
            user = await Database.get_user(user_id)
            if user['balance'] < price:
                await callback.answer(get_text('not_enough', lang), show_alert=True)
                return
            await Database.update_balance(user_id, -price, f"Покупка бонусной игры в {game_type}")
            if game_type == "doghouse":
                total_win = await self.games["doghouse"].play_bonus_game(user_id, 10)
            elif game_type == "sugarrush":
                total_win = 0  # заглушка, можно реализовать позже
            else:
                total_win = 0
            await Database.update_balance(user_id, total_win, f"Выигрыш в бонусной игре {game_type}")
            await callback.message.edit_text(
                f"🎉 {get_text('bonus_game', lang)} завершена! {get_text('total_win', lang)}: {total_win} ⭐",
                reply_markup=self.get_game_keyboard(game_type, lang=lang)
            )
        elif data == "tournaments":
            await self.show_tournaments(callback, lang)
        elif data == "bonuses":
            await self.show_bonuses(callback, lang)
        elif data == "claim_daily":
            await self.claim_daily(callback, lang)
        elif data == "claim_faucet":
            await self.claim_faucet(callback, lang)
        elif data == "activate_bonus":
            await state.set_state(BetStates.waiting_for_bonus_code)
            await callback.message.edit_text(
                "🎫 Введите бонус код:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="bonuses")]
                ])
            )
        elif data == "stats":
            await self.show_stats(callback, lang)
        elif data == "referrals":
            await self.show_referrals(callback, lang)
        elif data == "settings":
            await self.show_settings(callback, lang)
        elif data == "change_language":
            await self.change_language(callback)
        elif data == "provably_fair_info":
            await self.provably_fair_info(callback, lang)
        elif data == "toggle_pf":
            new_val = 0 if user['pf_enabled'] else 1
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('UPDATE users SET pf_enabled = ? WHERE user_id = ?', (new_val, user_id))
                await db.commit()
            await callback.answer(f"Provably Fair {'включен' if new_val else 'отключен'}", show_alert=True)
            await self.show_settings(callback, lang)
        elif data == "history":
            await self.show_history(callback, lang)
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
                [InlineKeyboardButton(text="🐶 Dog House", callback_data="admin_edit_doghouse"),
                 InlineKeyboardButton(text="🍬 Sugar Rush", callback_data="admin_edit_sugarrush")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("🎰 Выберите слот для редактирования:", reply_markup=kb)
        elif data == "admin_edit_doghouse":
            if user_id not in ADMIN_IDS:
                return
            await self.edit_slot(callback, state, "doghouse")
        elif data == "admin_edit_sugarrush":
            if user_id not in ADMIN_IDS:
                return
            await self.edit_slot(callback, state, "sugarrush")
        elif data == "admin_wager":
            if user_id not in ADMIN_IDS:
                return
            wager_mult = await Database.get_setting('wager_multiplier')
            wager_games = await Database.get_setting('wager_games')
            text = f"⚙️ **Настройки вейджера**\n\nМножитель: x{wager_mult}\nИгры: {wager_games}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Изменить множитель", callback_data="admin_wager_mult")],
                [InlineKeyboardButton(text="Изменить список игр", callback_data="admin_wager_games")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text(text, reply_markup=kb)
        elif data == "admin_wager_mult":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_wager_multiplier)
            await callback.message.edit_text("Введите новый множитель вейджера (число):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_wager")]]))
        elif data == "admin_wager_games":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_admin_action)
            await state.update_data(admin_action="wager_games")
            await callback.message.edit_text("Введите список игр через запятую (например: dice,roulette,mines,plinko,keno,doghouse,sugarrush,blackjack):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_wager")]]))
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
            kb_buttons = []
            for p in pending:
                kb_buttons.append([
                    InlineKeyboardButton(text=f"✅ Подтвердить {p['user_id']} {p['amount']}⭐", callback_data=f"confirm_{p['transaction_id']}"),
                    InlineKeyboardButton(text=f"❌ Отклонить {p['user_id']}", callback_data=f"reject_{p['transaction_id']}")
                ])
            kb_buttons.append([InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
        elif data.startswith("confirm_"):
            if user_id not in ADMIN_IDS:
                return
            tx_id = data.replace("confirm_", "")
            await Database.update_transaction_status(tx_id, 'completed')
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                row = await cursor.fetchone()
                if row:
                    uid, amt = row
                    await bot.send_message(uid, f"✅ Ваш вывод на {amt} ⭐ подтверждён и отправлен.")
            await callback.answer("✅ Вывод подтверждён")
            await self.admin_withdrawals(callback)
        elif data.startswith("reject_"):
            if user_id not in ADMIN_IDS:
                return
            tx_id = data.replace("reject_", "")
            await Database.update_transaction_status(tx_id, 'rejected')
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                row = await cursor.fetchone()
                if row:
                    uid, amt = row
                    await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, uid))
                    await db.commit()
                    await bot.send_message(uid, f"❌ Ваш вывод на {amt} ⭐ отклонён. Средства возвращены.")
            await callback.answer("❌ Вывод отклонён")
            await self.admin_withdrawals(callback)
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

    async def play_game(self, callback: CallbackQuery, game_type: str, bet: int, lang: str, **kwargs):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        if not user:
            await callback.answer(get_text('user_not_found', lang), show_alert=True)
            return

        if user['balance'] + user.get('bonus_balance', 0) < bet:
            await callback.answer(get_text('not_enough', lang), show_alert=True)
            return

        game = self.games.get(game_type)
        if not game:
            await callback.answer("❌ Игра недоступна", show_alert=True)
            return
        await game.load_settings()

        from_bonus, from_real = await WagerManager.process_bet(user_id, game_type, bet)
        if from_bonus == 0 and from_real == 0:
            await callback.answer("❌ Ошибка при списании средств", show_alert=True)
            return

        if game_type == "roulette":
            result = game.generate_result(bet, user_id)
            base_win = game.calculate_base_win(bet, result, kwargs.get("bet_type"), kwargs.get("bet_number"))
            win = await game.calculate_win(bet, {"base_win": base_win}, user_id)
        elif game_type == "dice":
            result = game.generate_result(bet, user_id, kwargs.get("mode", "single"))
            win = await game.calculate_win(bet, result, user_id)
        elif game_type == "plinko":
            result = game.generate_result(bet, user_id, kwargs.get("risk", "medium"))
            win = await game.calculate_win(bet, result, user_id)
        elif game_type == "mines":
            result = game.generate_result(bet, user_id, kwargs.get("mines",5), kwargs.get("difficulty","medium"))
            self.active_games[user_id] = {
                "game": "mines",
                "result": result,
                "bet": bet,
                "revealed": []
            }
            win = 0
        elif game_type == "keno":
            picks = kwargs.get("picks", [])
            result = game.generate_result(bet, user_id)
            base_win = game.calculate_base_win(bet, result, picks)
            win = await game.calculate_win(bet, {"base_win": base_win}, user_id)
        elif game_type == "blackjack":
            result = game.generate_result(bet, user_id)
            await Database.save_blackjack_session(user_id, result, bet)
            win = 0
        elif game_type in ["doghouse", "sugarrush"]:
            result = game.generate_result(bet, user_id)
            win = await game.calculate_win(bet, result, user_id)
        else:
            await callback.answer("❌ Игра не реализована", show_alert=True)
            return

        if game_type != "mines" and game_type != "blackjack":
            if win > 0:
                await Database.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await Database.add_game_history(user_id, game_type, bet, win, result if 'result' in locals() else {})
            await Database.update_jackpot(int(bet * JACKPOT_PERCENT))

        jackpot = await Database.get_jackpot()
        user_pf = user.get('pf_enabled', 1)
        text = self.format_game_result(game_type, result if 'result' in locals() else {}, bet, win, show_hash=user_pf)
        text += f"\n\n💰 {get_text('jackpot', lang)}: **{jackpot} ⭐**"

        if game_type == "mines":
            await callback.message.edit_text(
                text,
                reply_markup=self.get_game_keyboard(game_type, self.active_games.get(user_id), lang)
            )
        elif game_type == "blackjack":
            await callback.message.edit_text(
                f"🃏 **БЛЭКДЖЕК**\n\nВаши карты: {self.format_hand(result['player_hand'])} ({result['player_score']})\nДилер: {self.format_hand(result['dealer_hand'][:1])} + ?",
                reply_markup=self.get_game_keyboard(game_type, {"active": True}, lang)
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=self.get_game_keyboard(game_type, lang=lang)
            )

    def format_game_result(self, game_type: str, result: Dict, bet: int, win: int, show_hash: bool = True) -> str:
        if game_type == "dice":
            s = f"🎲 **КОСТИ**\n\nРезультат: {result.get('result', '?')}\nМножитель: x{result.get('base_mult', 1):.2f}\n"
        elif game_type == "roulette":
            s = f"🎡 **РУЛЕТКА**\n\nВыпало: {result.get('number', '?')} {result.get('color', '?')}\n"
        elif game_type == "mines":
            s = f"💣 **MINES**\n\nМин: {result.get('mines', 0)}\n"
        elif game_type == "plinko":
            s = f"📌 **PLINKO**\n\nПозиция: {result.get('final_position', 0)}\nМножитель: x{result.get('base_mult', 1):.2f}\n"
        elif game_type == "keno":
            s = f"🎯 **КЕНО**\n\nВыигрышные числа: {result.get('winning', [])[:10]}...\n"
        elif game_type == "doghouse":
            matrix = result.get("matrix", [])
            s = "🐶 **DOG HOUSE**\n\n"
            for row in matrix:
                s += " | ".join(row) + "\n"
        elif game_type == "sugarrush":
            s = f"🍬 **SUGAR RUSH**\n\nКаскадов: {result.get('cascade_count', 0)}\n"
        else:
            s = ""
        s += f"\nСтавка: **{bet} ⭐**\n"
        if win > 0:
            s += f"✅ Выигрыш: **{win} ⭐** (Профит: **+{win-bet} ⭐**)"
        elif win == 0 and game_type not in ["mines","blackjack"]:
            s += f"❌ Проигрыш"
        if show_hash and "hash" in result:
            s += f"\n\n🔐 Provably Fair: `{result['hash'][:16]}...`"
        return s

    def format_hand(self, hand):
        return " ".join([f"{r}{s}" for r,s in hand])

    async def show_tournaments(self, callback: CallbackQuery, lang: str):
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

    async def show_bonuses(self, callback: CallbackQuery, lang: str):
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

    async def claim_daily(self, callback: CallbackQuery, lang: str):
        user_id = callback.from_user.id
        can, streak, bonus = await Database.get_daily_reward(user_id)
        if not can:
            await callback.answer("❌ Вы уже получили сегодня", show_alert=True)
            return
        await WagerManager.add_bonus(user_id, bonus, "Ежедневный бонус")
        await callback.answer(f"✅ Получено {bonus} ⭐! Серия {streak}", show_alert=True)
        await self.show_bonuses(callback, lang)

    async def claim_faucet(self, callback: CallbackQuery, lang: str):
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
            await WagerManager.add_bonus(user_id, amount, "Кран")
            await db.execute('INSERT INTO transactions (transaction_id, user_id, amount, type, status, description) VALUES (?,?,?,?,?,?)',
                           (str(uuid.uuid4()), user_id, amount, 'faucet', 'completed', 'Кран'))
            await db.commit()
        await callback.answer(f"✅ {get_text('faucet_claimed', lang)} {amount} ⭐!", show_alert=True)
        await self.show_bonuses(callback, lang)

    async def show_stats(self, callback: CallbackQuery, lang: str):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        top = await Database.get_top_players(5)
        text = f"📊 **Статистика**\n\nВаша:\nИгр: {user['total_bets']}\nПобед: {user['total_wins']}\nПрофит: ...\n\nТоп-5:\n"
        for i,p in enumerate(top,1):
            text += f"{i}. {p['username'] or 'Аноним'}: {p['total_wins']} побед\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    async def show_referrals(self, callback: CallbackQuery, lang: str):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        bot_user = await bot.me()
        link = f"https://t.me/{bot_user.username}?start={user['referral_code']}"
        text = f"👥 **Рефералы**\n\nВаша ссылка:\n`{link}`\n\nПриглашайте друзей и получайте бонусы!"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]]))

    async def show_settings(self, callback: CallbackQuery, lang: str):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        pf_status = "✅" if user['pf_enabled'] else "❌"
        text = f"⚙️ **Настройки**\n\n{get_text('language', lang)}: {'🇷🇺 Русский' if lang=='ru' else '🇬🇧 English'}\n{get_text('vip_level', lang)}: {user['vip_level']} ({get_text('experience', lang)}: {user['experience']})\nProvably Fair: {pf_status}\n\nИграйте больше, чтобы повысить VIP!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Сменить язык", callback_data="change_language")],
            [InlineKeyboardButton(text=f"Provably Fair: {'Вкл' if user['pf_enabled'] else 'Выкл'}", callback_data="toggle_pf")],
            [InlineKeyboardButton(text="🔐 Provably Fair Info", callback_data="provably_fair_info")],
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
        await self.show_settings(callback, new_lang)

    async def provably_fair_info(self, callback: CallbackQuery, lang: str):
        text = "🔐 **Provably Fair**\n\nВсе игры используют криптографическую систему, позволяющую проверить честность каждого раунда. Хеш результата отображается в конце игры, если функция включена в настройках."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Назад", callback_data="settings")]]))

    async def show_history(self, callback: CallbackQuery, lang: str):
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

    async def edit_slot(self, callback: CallbackQuery, state: FSMContext, slot_type: str):
        settings = await Database.get_game_settings(slot_type)
        text = (
            f"🎰 Редактирование {slot_type}\n\n"
            f"Текущие настройки:\n"
            f"Символы: {settings.get('symbols', [])}\n"
            f"Веса: {settings.get('weights', [])}\n"
            f"Значения: {settings.get('values', [])}\n"
            f"Wild: {settings.get('wild', '')}\n"
            f"Scatter: {settings.get('scatter', '')}\n"
            f"RTP: {settings.get('rtp', RTP_ACTUAL)}\n"
            f"Волатильность: {settings.get('volatility', 0.15)}\n\n"
            f"Введите новые настройки в формате JSON."
        )
        await state.set_state(BetStates.waiting_for_slot_edit)
        await state.update_data(slot_type=slot_type)
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_slot_edit")]]))

casino_bot = CasinoBot()

@dp.message(CommandStart())
async def start_command(message: Message):
    await casino_bot.cmd_start(message)

@dp.message(Command("balance"))
async def balance_command(message: Message):
    await casino_bot.cmd_balance(message.from_user.id, message)

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    await casino_bot.callback_handler(callback, state)

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

    if game_type == "dice":
        kwargs["mode"] = mode or "single"
    elif game_type == "plinko":
        kwargs["risk"] = risk or "medium"
    elif game_type == "mines":
        kwargs["mines"] = mines
        kwargs["difficulty"] = difficulty

    await casino_bot.play_game(
        CallbackQuery(id='', from_user=message.from_user, message=message, data=f'play_{game_type}_{bet}'),
        game_type, bet, user.get('language','ru'), **kwargs
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
            await WagerManager.add_bonus(message.from_user.id, res, f"Бонус код {code}")
            await message.answer(f"✅ Получено {res} ⭐! Требуется отыгрыш.")
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

@dp.message(BetStates.waiting_for_slot_edit)
async def handle_slot_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    slot_type = data.get('slot_type')
    try:
        new_settings = json.loads(message.text)
        await Database.update_game_settings(slot_type, new_settings)
        await message.answer(f"✅ Настройки {slot_type} обновлены")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()

@dp.message(BetStates.waiting_for_wager_multiplier)
async def handle_wager_multiplier(message: Message, state: FSMContext):
    try:
        mult = int(message.text)
        await Database.update_setting('wager_multiplier', str(mult))
        await message.answer(f"✅ Множитель вейджера изменен на {mult}")
    except:
        await message.answer("❌ Введите число")
    await state.clear()

@dp.message(BetStates.waiting_for_admin_action)
async def handle_admin_action(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get('admin_action')
    if action == "wager_games":
        games = message.text
        await Database.update_setting('wager_games', games)
        await message.answer(f"✅ Список игр для вейджера обновлен")
        await state.clear()
    elif action and action.startswith("setting_"):
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

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    amount = message.successful_payment.total_amount
    await Database.update_balance(message.from_user.id, amount, "Пополнение Stars")
    await message.answer(f"✅ Пополнено {amount} ⭐")

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
