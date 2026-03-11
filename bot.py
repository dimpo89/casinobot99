import os
import sys
import asyncio
import logging
import random
import string
import json
import hashlib
import hmac
import time
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
import math
from enum import Enum

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    ChatMemberUpdated, ChatMember, LabeledPrice, PreCheckoutQuery,
    ShippingQuery, SuccessfulPayment
)
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
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

# Парсим ADMIN_IDS
ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',') if id.strip()]
        print(f"✅ ADMIN_IDS загружены: {ADMIN_IDS}")
    except Exception as e:
        print(f"❌ Ошибка парсинга ADMIN_IDS: {e}")
else:
    print("⚠️ ADMIN_IDS не заданы, админ-панель будет недоступна")

# Конфигурация
DATABASE_PATH = os.getenv('DATABASE_PATH', 'casino_bot.db')
STAR_RATE = 1.0
RTP_DISPLAY = 98.2
RTP_ACTUAL = 76.82
JACKPOT_PERCENT = 0.05
MAX_BET = 1000000
MIN_BET = 1

print("="*60 + "\n")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================
# КЛАССЫ ДЛЯ ИГР
# ============================================
class GameType(Enum):
    SLOT = "slot"
    DICE = "dice"
    COINFLIP = "coinflip"
    ROULETTE = "roulette"
    BLACKJACK = "blackjack"
    POKER = "poker"
    PLINKO = "plinko"
    MINES = "mines"
    KENO = "keno"
    WHEEL = "wheel"

# ============================================
# СОСТОЯНИЯ FSM
# ============================================
class BetStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_game_selection = State()
    waiting_for_withdrawal_amount = State()
    waiting_for_withdrawal_address = State()
    waiting_for_withdrawal_method = State()
    waiting_for_custom_game_params = State()
    waiting_for_admin_action = State()
    waiting_for_rtp_change = State()
    waiting_for_bonus_code = State()
    waiting_for_bonus_code_amount = State()
    waiting_for_bonus_code_uses = State()
    waiting_for_bonus_code_expiry = State()
    waiting_for_faucet = State()
    waiting_for_user_id = State()
    waiting_for_balance_amount = State()
    waiting_for_broadcast_message = State()
    waiting_for_tournament_name = State()
    waiting_for_tournament_prize = State()
    waiting_for_tournament_game = State()
    waiting_for_tournament_duration = State()
    waiting_for_tournament_min_bet = State()
    waiting_for_deposit_amount = State()

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
        
        await db.commit()
    logger.info("✅ База данных инициализирована")

# ============================================
# КЛАСС ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ
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
            # Проверяем, существует ли пользователь
            cursor = await db.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            exists = await cursor.fetchone()
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "welcome_bonus"')
            welcome_bonus = int((await cursor.fetchone())[0])
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "referral_bonus"')
            referral_bonus = int((await cursor.fetchone())[0])
            
            if exists:
                # Обновляем существующего пользователя
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
                # Создаем нового пользователя
                referral_code = Database.generate_referral_code()
                await db.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, referral_code, referred_by, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, referral_code, referred_by, welcome_bonus))
                
                logger.info(f"✅ Новый пользователь {user_id} создан с балансом {welcome_bonus} ⭐")
                bonus = welcome_bonus
                
                # Даем бонус пригласившему
                if referred_by:
                    await db.execute('''
                        UPDATE users SET balance = balance + ? WHERE user_id = ?
                    ''', (referral_bonus, referred_by))
                    
                    # Записываем транзакцию для реферала
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
            
            # Записываем транзакцию если есть описание
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
            
            # Проверяем турниры
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
            # Проверяем код
            cursor = await db.execute('''
                SELECT * FROM bonus_codes 
                WHERE code = ? AND used_count < max_uses 
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ''', (code,))
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            # Проверяем, не использовал ли пользователь уже
            cursor = await db.execute('''
                SELECT * FROM bonus_uses WHERE code = ? AND user_id = ?
            ''', (code, user_id))
            if await cursor.fetchone():
                return -1  # Уже использовал
            
            amount = row[1]
            
            # Начисляем бонус
            await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            
            # Обновляем счетчик использований
            await db.execute('UPDATE bonus_codes SET used_count = used_count + 1 WHERE code = ?', (code,))
            
            # Записываем использование
            await db.execute('INSERT INTO bonus_uses (code, user_id) VALUES (?, ?)', (code, user_id))
            
            # Записываем транзакцию
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
            # Получаем информацию о турнире
            cursor = await db.execute('SELECT * FROM tournaments WHERE tournament_id = ?', (tournament_id,))
            tournament = await cursor.fetchone()
            
            if not tournament:
                return None
            
            # Получаем победителей
            leaderboard = await Database.get_tournament_leaderboard(tournament_id, 3)
            
            # Начисляем призы (50%, 30%, 20%)
            if leaderboard:
                prizes = [0.5, 0.3, 0.2]
                for i, player in enumerate(leaderboard):
                    if i < len(prizes):
                        prize = int(tournament[2] * prizes[i])  # prize_pool * процент
                        await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                                       (prize, player['user_id']))
                        
                        # Записываем транзакцию
                        await db.execute('''
                            INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (str(uuid.uuid4()), player['user_id'], prize, 'tournament', 'completed', 
                              f'Приз за турнир #{tournament_id}: {tournament[1]}'))
            
            # Обновляем статус турнира
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

# ============================================
# БАЗОВЫЙ КЛАСС ДЛЯ ИГР
# ============================================
class BaseGame:
    def __init__(self, game_type: str):
        self.game_type = game_type
        self.actual_rtp = RTP_ACTUAL
        self.display_rtp = RTP_DISPLAY
    
    async def get_current_rtp(self) -> float:
        settings = await Database.get_rtp_settings(self.game_type)
        return settings.get('current_rtp', self.actual_rtp)
    
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
# КЛАСС ДЛЯ ИГРЫ В СЛОТЫ (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class SlotGame(BaseGame):
    def __init__(self):
        super().__init__("slot")
        self.symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐", "🎰", "👑", "💫"]
        self.symbol_values = {
            "🍒": 2, "🍋": 3, "🍊": 4, "🍇": 5,
            "💎": 10, "7️⃣": 20, "⭐": 50, "🎰": 100,
            "👑": 200, "💫": 500
        }
        self.reels = 5
        self.rows = 3
        self.free_spins_feature = True
        self.wild_symbol = "⭐"
        self.scatter_symbol = "🎰"
    
    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        matrix = []
        for i in range(self.rows):
            row = []
            for j in range(self.reels):
                seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i * self.reels + j)
                symbol_index = self.get_random_number(0, len(self.symbols) - 1, seed)
                row.append(self.symbols[symbol_index])
            matrix.append(row)
        
        win_amount = self.calculate_win(bet, {"matrix": matrix, "user_id": user_id})
        
        # Проверка на бонусную игру (фриспины)
        scatter_count = sum(row.count(self.scatter_symbol) for row in matrix)
        free_spins = 0
        if scatter_count >= 3:
            free_spins = 10 * scatter_count
        
        return {
            "matrix": matrix,
            "win_amount": win_amount,
            "free_spins": free_spins,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }
    
    def calculate_win(self, bet: int, result: Dict) -> int:
        matrix = result["matrix"]
        win = 0
        paylines = self.get_paylines()
        
        for payline in paylines:
            symbols = [matrix[row][col] for col, row in enumerate(payline)]
            
            # Проверка на Wild (заменяет любой символ кроме Scatter)
            if symbols[0] == self.wild_symbol or all(s == self.wild_symbol for s in symbols):
                multiplier = self.symbol_values.get(self.wild_symbol, 1)
                win += bet * multiplier
                continue
            
            # Проверка на комбинацию
            if all(s == symbols[0] or s == self.wild_symbol for s in symbols):
                multiplier = self.symbol_values.get(symbols[0], 1)
                # Увеличиваем множитель за каждое совпадение
                match_count = sum(1 for s in symbols if s == symbols[0] or s == self.wild_symbol)
                multiplier = multiplier * (1 + (match_count - 3) * 0.5)
                win += bet * multiplier
        
        # Случайный множитель (x2 иногда)
        if random.random() < 0.1:  # 10% шанс
            win *= 2
        
        rtp_factor = self.actual_rtp / 100.0
        win = int(win * rtp_factor)
        
        # Шанс на джекпот
        if random.random() < 0.001:
            jackpot = asyncio.run(Database.get_jackpot())
            win += jackpot
            if win > 0 and result.get("user_id"):
                asyncio.create_task(Database.reset_jackpot(result["user_id"]))
        
        return win
    
    def get_paylines(self) -> List[List[int]]:
        return [
            [0, 0, 0, 0, 0],  # Линия 1
            [1, 1, 1, 1, 1],  # Линия 2
            [2, 2, 2, 2, 2],  # Линия 3
            [0, 1, 2, 1, 0],  # Линия 4
            [2, 1, 0, 1, 2],  # Линия 5
            [0, 0, 1, 2, 2],  # Линия 6
            [2, 2, 1, 0, 0],  # Линия 7
            [1, 0, 1, 2, 1],  # Линия 8
            [1, 2, 1, 0, 1],  # Линия 9
            [0, 1, 1, 1, 0],  # Линия 10
        ]

# ============================================
# КЛАСС ДЛЯ ИГРЫ В КОСТИ (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class DiceGame(BaseGame):
    def __init__(self):
        super().__init__("dice")
        self.multipliers = {
            1: 6, 2: 3, 3: 2, 4: 1.5, 5: 1.2, 6: 1,
            "double": {2: 12, 3: 6, 4: 4, 5: 3, 6: 2, 7: 1.5, 8: 2, 9: 3, 10: 4, 11: 6, 12: 12}
        }
    
    def generate_result(self, bet: int, user_id: int = None, mode: str = "single") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        if mode == "single":
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce)
            result = self.get_random_number(1, 6, seed)
            multiplier = self.multipliers[result]
        else:  # double dice
            seed1 = self.get_provably_fair_seed(server_seed, client_seed, nonce)
            seed2 = self.get_provably_fair_seed(server_seed, client_seed, nonce + 1)
            die1 = self.get_random_number(1, 6, seed1)
            die2 = self.get_random_number(1, 6, seed2)
            result = die1 + die2
            multiplier = self.multipliers["double"][result]
        
        return {
            "result": result,
            "multiplier": multiplier,
            "mode": mode,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }
    
    def calculate_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["multiplier"])

# ============================================
# КЛАСС ДЛЯ РУЛЕТКИ (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class RouletteGame(BaseGame):
    def __init__(self):
        super().__init__("roulette")
        self.numbers = list(range(0, 37))
        self.colors = {0: "green"}
        for i in range(1, 37):
            if i in [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]:
                self.colors[i] = "red"
            else:
                self.colors[i] = "black"
        
        self.bet_types = {
            "straight": 36, "split": 18, "street": 12, "corner": 9,
            "sixline": 6, "column": 3, "dozen": 3, "red": 2,
            "black": 2, "even": 2, "odd": 2, "low": 2, "high": 2
        }
        
        # Сектора для ставок
        self.columns = {
            1: [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34],
            2: [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35],
            3: [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
        }
        
        self.dozens = {
            1: list(range(1, 13)),
            2: list(range(13, 25)),
            3: list(range(25, 37))
        }
    
    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        seed = self.get_provably_fair_seed(server_seed, client_seed, nonce)
        number = self.get_random_number(0, 36, seed)
        
        # Определяем выигрышные сектора
        winning_sectors = {
            "number": number,
            "color": self.colors[number],
            "even": number > 0 and number % 2 == 0,
            "odd": number % 2 == 1,
            "low": 1 <= number <= 18,
            "high": 19 <= number <= 36,
            "dozen1": number in self.dozens[1],
            "dozen2": number in self.dozens[2],
            "dozen3": number in self.dozens[3],
            "column1": number in self.columns[1],
            "column2": number in self.columns[2],
            "column3": number in self.columns[3]
        }
        
        return {
            "number": number,
            "color": self.colors[number],
            "sectors": winning_sectors,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": seed
        }
    
    def calculate_win(self, bet: int, result: Dict, bet_type: str = "red", bet_number: int = None) -> int:
        number = result["number"]
        sectors = result["sectors"]
        
        if bet_type == "straight" and bet_number == number:
            return bet * 36
        elif bet_type == "split" and bet_number and abs(bet_number - number) in [1, 3]:
            return bet * 18
        elif bet_type == "street" and bet_number and (number - 1) // 3 == (bet_number - 1) // 3:
            return bet * 12
        elif bet_type == "corner" and bet_number:
            # Упрощенная проверка угла
            if number in [bet_number, bet_number+1, bet_number+3, bet_number+4]:
                return bet * 9
        elif bet_type == "column" and sectors[f"column{bet_number}"]:
            return bet * 3
        elif bet_type == "dozen" and sectors[f"dozen{bet_number}"]:
            return bet * 3
        elif bet_type == "red" and sectors["color"] == "red":
            return bet * 2
        elif bet_type == "black" and sectors["color"] == "black":
            return bet * 2
        elif bet_type == "even" and sectors["even"]:
            return bet * 2
        elif bet_type == "odd" and sectors["odd"]:
            return bet * 2
        elif bet_type == "low" and sectors["low"]:
            return bet * 2
        elif bet_type == "high" and sectors["high"]:
            return bet * 2
        
        return 0

# ============================================
# КЛАСС ДЛЯ БЛЭКДЖЕКА (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class BlackjackGame(BaseGame):
    def __init__(self):
        super().__init__("blackjack")
        self.suits = ["♠", "♥", "♦", "♣"]
        self.ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        self.card_values = {
            "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
            "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11
        }
        self.insurance_allowed = True
        self.double_allowed = True
        self.split_allowed = True
    
    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        deck = [(rank, suit) for suit in self.suits for rank in self.ranks] * 4  # 4 колоды
        shuffled_deck = self.shuffle_deck(deck, server_seed, client_seed, nonce)
        
        player_hand = [shuffled_deck[0], shuffled_deck[2]]
        dealer_hand = [shuffled_deck[1], shuffled_deck[3]]
        remaining_deck = shuffled_deck[4:]
        
        player_score = self.calculate_hand_score(player_hand)
        dealer_score = self.calculate_hand_score([dealer_hand[0]])
        
        # Проверка на блэкджек
        player_blackjack = player_score == 21 and len(player_hand) == 2
        dealer_blackjack = self.calculate_hand_score(dealer_hand) == 21 and len(dealer_hand) == 2
        
        return {
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "deck": remaining_deck,
            "player_score": player_score,
            "dealer_upcard_score": dealer_score,
            "dealer_upcard": dealer_hand[0],
            "player_blackjack": player_blackjack,
            "dealer_blackjack": dealer_blackjack,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }
    
    def shuffle_deck(self, deck: List, server_seed: str, client_seed: str, nonce: int) -> List:
        shuffled = deck.copy()
        for i in range(len(shuffled) - 1, 0, -1):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            j = self.get_random_number(0, i, seed)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled
    
    def hit(self, game_state: Dict) -> Dict:
        if game_state["deck"]:
            card = game_state["deck"].pop(0)
            game_state["player_hand"].append(card)
            game_state["player_score"] = self.calculate_hand_score(game_state["player_hand"])
        return game_state
    
    def dealer_play(self, game_state: Dict) -> Dict:
        dealer_score = self.calculate_hand_score(game_state["dealer_hand"])
        while dealer_score < 17 and game_state["deck"]:
            game_state["dealer_hand"].append(game_state["deck"].pop(0))
            dealer_score = self.calculate_hand_score(game_state["dealer_hand"])
        return game_state
    
    def calculate_win(self, bet: int, result: Dict, player_stands: bool = True) -> int:
        player_hand = result["player_hand"]
        dealer_hand = result["dealer_hand"]
        
        player_score = self.calculate_hand_score(player_hand)
        dealer_score = self.calculate_hand_score(dealer_hand)
        
        # Проверка на блэкджек
        player_blackjack = player_score == 21 and len(player_hand) == 2
        dealer_blackjack = dealer_score == 21 and len(dealer_hand) == 2
        
        if player_blackjack and not dealer_blackjack:
            return int(bet * 2.5)  # Блэкджек платит 3:2
        elif dealer_blackjack and not player_blackjack:
            return 0
        elif player_blackjack and dealer_blackjack:
            return bet  # Ничья
        
        if player_score > 21:
            return 0
        elif dealer_score > 21:
            return bet * 2
        elif player_score > dealer_score:
            return bet * 2
        elif player_score == dealer_score:
            return bet
        else:
            return 0
    
    def calculate_hand_score(self, hand: List) -> int:
        score = 0
        aces = 0
        
        for rank, _ in hand:
            if rank == "A":
                aces += 1
                score += 11
            else:
                score += self.card_values[rank]
        
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        
        return score

# ============================================
# КЛАСС ДЛЯ PLINKO (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class PlinkoGame(BaseGame):
    def __init__(self):
        super().__init__("plinko")
        self.rows = 16
        self.multipliers = {
            "low": {
                16: [16, 9, 2, 1.4, 1.2, 1.1, 1, 0.5, 0.5, 1, 1.1, 1.2, 1.4, 2, 9, 16],
                15: [15, 8, 1.8, 1.3, 1.1, 1, 0.7, 0.5, 0.5, 0.7, 1, 1.1, 1.3, 1.8, 8, 15],
                14: [14, 7, 1.6, 1.2, 1, 0.8, 0.6, 0.4, 0.4, 0.6, 0.8, 1, 1.2, 1.6, 7, 14]
            },
            "medium": {
                16: [22, 12, 3, 1.8, 1.4, 1.2, 0.8, 0.3, 0.3, 0.8, 1.2, 1.4, 1.8, 3, 12, 22],
                14: [20, 10, 2.5, 1.5, 1.2, 0.9, 0.5, 0.2, 0.2, 0.5, 0.9, 1.2, 1.5, 2.5, 10, 20],
                12: [18, 8, 2, 1.3, 1, 0.7, 0.4, 0.1, 0.1, 0.4, 0.7, 1, 1.3, 2, 8, 18]
            },
            "high": {
                16: [33, 18, 5, 2.5, 1.8, 1.3, 0.5, 0.2, 0.2, 0.5, 1.3, 1.8, 2.5, 5, 18, 33],
                14: [28, 15, 4, 2, 1.5, 1, 0.4, 0.1, 0.1, 0.4, 1, 1.5, 2, 4, 15, 28],
                12: [24, 12, 3, 1.8, 1.2, 0.8, 0.3, 0.05, 0.05, 0.3, 0.8, 1.2, 1.8, 3, 12, 24]
            }
        }
    
    def generate_result(self, bet: int, user_id: int = None, risk: str = "medium") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        risk_levels = {"low": 16, "medium": 14, "high": 12}
        rows = risk_levels.get(risk, 14)
        
        # Симуляция падения с физикой
        path = []
        position = rows / 2
        bounces = []
        
        for step in range(rows):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + step)
            
            # Небольшая физика - шарик может отскочить сильнее
            direction = self.get_random_number(0, 100, seed)
            if direction < 48:
                move = -0.5
            elif direction < 96:
                move = 0.5
            else:
                move = -1 if direction < 98 else 1  # Редкие сильные отскоки
            
            position += move
            path.append(move)
            bounces.append(abs(move))
        
        final_position = int(round(position))
        final_position = max(0, min(rows, final_position))
        
        multiplier = self.multipliers[risk][rows][final_position]
        
        # Случайный множитель за отскоки
        total_bounces = sum(bounces)
        if total_bounces > rows * 0.7:
            multiplier *= 1.2
        
        return {
            "path": path,
            "bounces": bounces,
            "final_position": final_position,
            "multiplier": multiplier,
            "rows": rows,
            "risk": risk,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }
    
    def calculate_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["multiplier"])

# ============================================
# КЛАСС ДЛЯ MINES (УЛУЧШЕННАЯ ВЕРСИЯ)
# ============================================
class MinesGame(BaseGame):
    def __init__(self):
        super().__init__("mines")
        self.grid_size = 5
        self.max_mines = 24
        self.difficulty_multipliers = {
            "easy": 1.0,
            "medium": 1.2,
            "hard": 1.5,
            "extreme": 2.0
        }
    
    def generate_result(self, bet: int, user_id: int = None, 
                        mines_count: int = 3, difficulty: str = "medium") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        # Размещаем мины
        mine_positions = []
        all_positions = list(range(self.grid_size * self.grid_size))
        
        for i in range(mines_count):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            idx = self.get_random_number(0, len(all_positions) - 1, seed)
            mine_positions.append(all_positions.pop(idx))
        
        # Размещаем "золото" на безопасных клетках
        gold_positions = []
        if all_positions:
            gold_count = min(3, len(all_positions))
            for i in range(gold_count):
                seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + mines_count + i)
                idx = self.get_random_number(0, len(all_positions) - 1, seed)
                gold_positions.append(all_positions.pop(idx))
        
        return {
            "mine_positions": mine_positions,
            "gold_positions": gold_positions,
            "mines_count": mines_count,
            "grid_size": self.grid_size,
            "difficulty": difficulty,
            "difficulty_multiplier": self.difficulty_multipliers[difficulty],
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce),
            "revealed": []
        }
    
    def calculate_win(self, bet: int, result: Dict, revealed_cells: List[int]) -> int:
        mine_positions = result["mine_positions"]
        gold_positions = result["gold_positions"]
        mines_count = result["mines_count"]
        difficulty_mult = result.get("difficulty_multiplier", 1.0)
        total_cells = self.grid_size * self.grid_size
        safe_cells = total_cells - mines_count
        
        # Проверяем, не наступили ли на мину
        for cell in revealed_cells:
            if cell in mine_positions:
                return 0
        
        revealed_count = len(revealed_cells)
        if revealed_count == 0:
            return 0
        
        # Базовая формула множителя
        base_multiplier = (safe_cells) / (safe_cells - revealed_count + 1)
        
        # Бонус за найденное золото
        gold_bonus = 1.0
        for cell in revealed_cells:
            if cell in gold_positions:
                gold_bonus += 0.2
        
        total_multiplier = base_multiplier * gold_bonus * difficulty_mult
        
        return int(bet * total_multiplier)

# ============================================
# НОВЫЙ КЛАСС: КЕНО (KENO)
# ============================================
class KenoGame(BaseGame):
    def __init__(self):
        super().__init__("keno")
        self.numbers = list(range(1, 81))
        self.payouts = {
            1: {1: 3},
            2: {2: 12, 1: 1},
            3: {3: 42, 2: 2, 1: 1},
            4: {4: 150, 3: 5, 2: 1},
            5: {5: 500, 4: 15, 3: 2},
            6: {6: 1500, 5: 50, 4: 5, 3: 1},
            7: {7: 5000, 6: 150, 5: 15, 4: 2},
            8: {8: 15000, 7: 500, 6: 50, 5: 5, 4: 1}
        }
    
    def generate_result(self, bet: int, user_id: int = None, picks: List[int] = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        # Генерируем выигрышные числа
        winning_numbers = []
        available = self.numbers.copy()
        for i in range(20):  # В кено выпадает 20 чисел
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            idx = self.get_random_number(0, len(available) - 1, seed)
            winning_numbers.append(available.pop(idx))
        
        return {
            "winning_numbers": winning_numbers,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce)
        }
    
    def calculate_win(self, bet: int, result: Dict, picks: List[int]) -> int:
        winning_numbers = result["winning_numbers"]
        matches = sum(1 for num in picks if num in winning_numbers)
        picks_count = len(picks)
        
        if picks_count in self.payouts and matches in self.payouts[picks_count]:
            multiplier = self.payouts[picks_count][matches]
            return bet * multiplier
        
        return 0

# ============================================
# ОСНОВНОЙ КЛАСС БОТА
# ============================================
class CasinoBot:
    def __init__(self):
        self.games = {
            "slot": SlotGame(),
            "dice": DiceGame(),
            "roulette": RouletteGame(),
            "blackjack": BlackjackGame(),
            "plinko": PlinkoGame(),
            "mines": MinesGame(),
            "keno": KenoGame()
        }
        self.active_games = {}
        self.blackjack_games = {}
        self.pending_withdrawals = {}
        logger.info(f"✅ Игры загружены: {list(self.games.keys())}")
    
    def get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slot"),
             InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice")],
            [InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette"),
             InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_blackjack")],
            [InlineKeyboardButton(text="📌 Plinko", callback_data="game_plinko"),
             InlineKeyboardButton(text="💣 Mines", callback_data="game_mines")],
            [InlineKeyboardButton(text="🎯 Кено", callback_data="game_keno"),
             InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton(text="🏆 Турниры", callback_data="tournaments"),
             InlineKeyboardButton(text="🎁 Бонусы", callback_data="bonuses")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
             InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
             InlineKeyboardButton(text="📜 История", callback_data="history")]
        ]
        
        if user_id in ADMIN_IDS:
            buttons.append([InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")])
            logger.info(f"👑 Админ-панель показана для пользователя {user_id}")
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_game_keyboard(self, game_type: str, game_state: Dict = None) -> InlineKeyboardMarkup:
        buttons = []
        
        if game_type == "slot":
            buttons = [
                [InlineKeyboardButton(text="🎰 10 ⭐", callback_data="play_slot_10"),
                 InlineKeyboardButton(text="🎰 50 ⭐", callback_data="play_slot_50")],
                [InlineKeyboardButton(text="🎰 100 ⭐", callback_data="play_slot_100"),
                 InlineKeyboardButton(text="🎰 500 ⭐", callback_data="play_slot_500")],
                [InlineKeyboardButton(text="🎰 1000 ⭐", callback_data="play_slot_1000"),
                 InlineKeyboardButton(text="💰 Своя ставка", callback_data="custom_bet_slot")]
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
                 InlineKeyboardButton(text="📌 Экстрим", callback_data="plinko_extreme")],
                [InlineKeyboardButton(text="10 ⭐", callback_data="plinko_10"),
                 InlineKeyboardButton(text="50 ⭐", callback_data="plinko_50")],
                [InlineKeyboardButton(text="100 ⭐", callback_data="plinko_100"),
                 InlineKeyboardButton(text="💰 Своя ставка", callback_data="plinko_bet")]
            ]
        elif game_type == "mines":
            if game_state and game_state.get("active"):
                # Создаем сетку 5x5 для Mines
                grid_buttons = []
                revealed = game_state.get("revealed", [])
                mine_positions = game_state.get("mine_positions", [])
                gold_positions = game_state.get("gold_positions", [])
                
                for i in range(5):
                    row = []
                    for j in range(5):
                        cell = i * 5 + j
                        if cell in revealed:
                            if cell in mine_positions:
                                text = "💥"
                            elif cell in gold_positions:
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
                     InlineKeyboardButton(text="💣 15 мин (экстрим)", callback_data="mines_extreme_15")],
                    [InlineKeyboardButton(text="10 ⭐", callback_data="mines_10"),
                     InlineKeyboardButton(text="50 ⭐", callback_data="mines_50")],
                    [InlineKeyboardButton(text="100 ⭐", callback_data="mines_100"),
                     InlineKeyboardButton(text="💰 Своя ставка", callback_data="mines_bet")]
                ]
        elif game_type == "keno":
            buttons = [
                [InlineKeyboardButton(text="🎯 1 число", callback_data="keno_pick1"),
                 InlineKeyboardButton(text="🎯 3 числа", callback_data="keno_pick3")],
                [InlineKeyboardButton(text="🎯 5 чисел", callback_data="keno_pick5"),
                 InlineKeyboardButton(text="🎯 8 чисел", callback_data="keno_pick8")],
                [InlineKeyboardButton(text="10 ⭐", callback_data="keno_10"),
                 InlineKeyboardButton(text="50 ⭐", callback_data="keno_50")],
                [InlineKeyboardButton(text="100 ⭐", callback_data="keno_100"),
                 InlineKeyboardButton(text="💰 Своя ставка", callback_data="keno_bet")]
            ]
        
        buttons.append([
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_admin_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats"),
             InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users_menu")],
            [InlineKeyboardButton(text="💰 Управление балансом", callback_data="admin_balance"),
             InlineKeyboardButton(text="🎮 Настройки RTP", callback_data="admin_rtp")],
            [InlineKeyboardButton(text="🏆 Управление турнирами", callback_data="admin_tournaments_menu"),
             InlineKeyboardButton(text="🎁 Бонус коды", callback_data="admin_bonuses_menu")],
            [InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin_withdrawals"),
             InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="⚙️ Настройки казино", callback_data="admin_settings"),
             InlineKeyboardButton(text="📈 Логи и бэкап", callback_data="admin_logs")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_users_menu_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admin_user_search")],
            [InlineKeyboardButton(text="🔍 Поиск по username", callback_data="admin_user_search_username")],
            [InlineKeyboardButton(text="⛔ Заблокировать пользователя", callback_data="admin_user_ban")],
            [InlineKeyboardButton(text="✅ Разблокировать", callback_data="admin_user_unban")],
            [InlineKeyboardButton(text="👑 Назначить админом", callback_data="admin_user_make_admin")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_tournaments_menu_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="➕ Создать турнир", callback_data="admin_tournament_create")],
            [InlineKeyboardButton(text="📋 Список турниров", callback_data="admin_tournaments_list")],
            [InlineKeyboardButton(text="⏹ Завершить турнир", callback_data="admin_tournament_end")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_bonuses_menu_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="➕ Создать бонус код", callback_data="admin_bonus_create")],
            [InlineKeyboardButton(text="📋 Список кодов", callback_data="admin_bonuses_list")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    async def cmd_start(self, message: Message):
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        args = message.text.split()
        referred_by = None
        if len(args) > 1:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT user_id FROM users WHERE referral_code = ?', (args[1],))
                result = await cursor.fetchone()
                if result:
                    referred_by = result[0]
        
        bonus = await Database.create_user(user_id, username, first_name, last_name, referred_by)
        user = await Database.get_user(user_id)
        
        if user:
            welcome_text = (
                f"🎰 Добро пожаловать в **Mega Casino**!\n\n"
                f"Самый высокий RTP в Telegram — **{RTP_DISPLAY}%**!\n"
                f"👤 Ваш ID: `{user_id}`\n"
                f"💰 Баланс: **{user['balance']} ⭐**\n"
            )
            
            if bonus > 0:
                welcome_text += f"🎁 Приветственный бонус: **+{bonus} ⭐**\n"
            
            if referred_by:
                welcome_text += f"👥 Вы приглашены пользователем {referred_by}\n"
            
            welcome_text += f"\nВыберите игру в меню ниже:"
        else:
            welcome_text = (
                f"🎰 Добро пожаловать в **Mega Casino**!\n\n"
                f"Самый высокий RTP в Telegram — **{RTP_DISPLAY}%**!\n"
                f"👤 Ваш ID: `{user_id}`\n\n"
                f"Выберите игру в меню ниже:"
            )
        
        await message.answer(
            welcome_text,
            reply_markup=self.get_main_keyboard(user_id)
        )
        logger.info(f"✅ Пользователь {user_id} запустил бота")
    
    async def cmd_balance(self, message: Message):
        user_id = message.from_user.id
        user = await Database.get_user(user_id)
        
        if not user:
            logger.warning(f"❌ Пользователь {user_id} не найден в БД при проверке баланса")
            await message.answer("❌ Пользователь не найден. Напишите /start для регистрации")
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*), SUM(profit) FROM games WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            games_count = row[0] or 0
            total_profit = row[1] or 0
            
            cursor = await db.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = "completed"', (user_id,))
            transactions_count = (await cursor.fetchone())[0]
        
        jackpot = await Database.get_jackpot()
        
        balance_text = (
            f"💰 **Ваш баланс**\n\n"
            f"Баланс: **{user['balance']} ⭐**\n"
            f"Всего игр: **{games_count}**\n"
            f"Побед: **{user['total_wins']}**\n"
            f"Поражений: **{user['total_losses']}**\n"
            f"Винрейт: **{(user['total_wins']/games_count*100):.1f}%**" if games_count > 0 else "Винрейт: **0%**"
            f"Общий профит: **{total_profit} ⭐**\n"
            f"Транзакций: **{transactions_count}**\n"
            f"VIP уровень: **{user['vip_level']}**\n"
            f"Опыт: **{user['experience']}**\n\n"
            f"💰 Текущий джекпот: **{jackpot} ⭐**\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
             InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton(text="📜 История транзакций", callback_data="transaction_history")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(balance_text, reply_markup=keyboard)
        logger.info(f"💰 Баланс пользователя {user_id}: {user['balance']} ⭐")
    
    async def deposit(self, callback: CallbackQuery, state: FSMContext):
        await state.set_state(BetStates.waiting_for_deposit_amount)
        await callback.message.edit_text(
            "💳 **Пополнение баланса**\n\n"
            "Введите сумму пополнения в ⭐ (от 10 до 10000):\n\n"
            "Пример: 100",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
            ])
        )
    
    async def process_deposit(self, message: Message, state: FSMContext):
        try:
            amount = int(message.text)
            if amount < 10 or amount > 10000:
                await message.answer("❌ Сумма должна быть от 10 до 10000 ⭐")
                return
            
            # Создаем инвойс для оплаты звездами
            prices = [LabeledPrice(label="Пополнение баланса", amount=amount * 100)]  # В копейках/центах
            
            await bot.send_invoice(
                chat_id=message.chat.id,
                title="Пополнение баланса в Mega Casino",
                description=f"Пополнение баланса на {amount} ⭐",
                payload=f"deposit_{amount}",
                provider_token="",  # Для Stars оставляем пустым
                currency="XTR",  # Специальная валюта для Stars
                prices=prices,
                start_parameter="time-deposit"
            )
            
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите число")
    
    async def withdraw(self, callback: CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        
        min_withdrawal = int(await Database.get_setting('min_withdrawal'))
        withdrawal_fee = int(await Database.get_setting('withdrawal_fee'))
        
        if user['balance'] < min_withdrawal:
            await callback.answer(f"❌ Минимальная сумма вывода {min_withdrawal} ⭐", show_alert=True)
            return
        
        await state.set_state(BetStates.waiting_for_withdrawal_amount)
        await callback.message.edit_text(
            f"💸 **Вывод средств**\n\n"
            f"Ваш баланс: {user['balance']} ⭐\n"
            f"Минимальная сумма: {min_withdrawal} ⭐\n"
            f"Комиссия: {withdrawal_fee}%\n\n"
            f"Введите сумму для вывода:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
            ])
        )
    
    async def process_withdrawal_amount(self, message: Message, state: FSMContext):
        try:
            amount = int(message.text)
            user_id = message.from_user.id
            user = await Database.get_user(user_id)
            
            min_withdrawal = int(await Database.get_setting('min_withdrawal'))
            withdrawal_fee = int(await Database.get_setting('withdrawal_fee'))
            
            if amount < min_withdrawal:
                await message.answer(f"❌ Минимальная сумма вывода {min_withdrawal} ⭐")
                return
            
            if amount > user['balance']:
                await message.answer(f"❌ Недостаточно средств. Баланс: {user['balance']} ⭐")
                return
            
            fee_amount = int(amount * withdrawal_fee / 100)
            final_amount = amount - fee_amount
            
            await state.update_data(withdrawal_amount=amount, final_amount=final_amount)
            await state.set_state(BetStates.waiting_for_withdrawal_address)
            
            await message.answer(
                f"💸 **Подтверждение вывода**\n\n"
                f"Сумма: {amount} ⭐\n"
                f"Комиссия: {fee_amount} ⭐ ({withdrawal_fee}%)\n"
                f"К получению: {final_amount} ⭐\n\n"
                f"Введите адрес кошелька для вывода:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
                ])
            )
        except ValueError:
            await message.answer("❌ Введите число")
    
    async def process_withdrawal_address(self, message: Message, state: FSMContext):
        address = message.text
        user_id = message.from_user.id
        
        data = await state.get_data()
        amount = data.get('withdrawal_amount')
        final_amount = data.get('final_amount')
        
        # Создаем заявку на вывод
        tx_id = await Database.add_transaction(
            user_id=user_id,
            amount=amount,
            tx_type='withdrawal',
            status='pending',
            description=f'Вывод {amount} ⭐ на кошелек {address}',
            wallet_address=address
        )
        
        # Блокируем средства
        await Database.update_balance(user_id, -amount, f'Заблокировано под вывод {amount} ⭐')
        
        await state.clear()
        await message.answer(
            f"✅ Заявка на вывод создана!\n\n"
            f"ID транзакции: `{tx_id}`\n"
            f"Сумма: {amount} ⭐\n"
            f"К получению: {final_amount} ⭐\n"
            f"Адрес: {address}\n\n"
            f"Ожидайте подтверждения администратора."
        )
        
        # Уведомляем админов
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"💰 **Новая заявка на вывод!**\n\n"
                    f"Пользователь: {user_id}\n"
                    f"Сумма: {amount} ⭐\n"
                    f"К получению: {final_amount} ⭐\n"
                    f"Адрес: {address}\n"
                    f"ID: `{tx_id}`"
                )
            except:
                pass
    
    async def play_game(self, callback: CallbackQuery, game_type: str, bet: int, **kwargs):
        user_id = callback.from_user.id
        
        user = await Database.get_user(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден. Напишите /start", show_alert=True)
            return
        
        if user['balance'] < bet:
            await callback.answer(f"❌ Недостаточно средств. Баланс: {user['balance']} ⭐", show_alert=True)
            return
        
        game = self.games.get(game_type)
        if not game:
            await callback.answer("❌ Игра временно недоступна", show_alert=True)
            return
        
        # Списываем ставку
        await Database.update_balance(user_id, -bet, f'Ставка в {game_type}')
        
        # Генерируем результат
        if game_type == "roulette" and "bet_type" in kwargs:
            result = game.generate_result(bet, user_id)
            win_amount = game.calculate_win(bet, result, kwargs["bet_type"], kwargs.get("bet_number"))
        elif game_type == "plinko" and "risk" in kwargs:
            result = game.generate_result(bet, user_id, kwargs["risk"])
            win_amount = game.calculate_win(bet, result)
        elif game_type == "mines" and "mines_count" in kwargs and "difficulty" in kwargs:
            result = game.generate_result(bet, user_id, kwargs["mines_count"], kwargs["difficulty"])
            win_amount = 0
            self.active_games[user_id] = {
                "game": "mines",
                "result": result,
                "bet": bet,
                "revealed": []
            }
        elif game_type == "keno" and "picks" in kwargs:
            result = game.generate_result(bet, user_id)
            win_amount = game.calculate_win(bet, result, kwargs["picks"])
        elif game_type == "dice" and "mode" in kwargs:
            result = game.generate_result(bet, user_id, kwargs["mode"])
            win_amount = game.calculate_win(bet, result)
        else:
            result = game.generate_result(bet, user_id)
            win_amount = game.calculate_win(bet, result)
        
        if game_type != "mines" and game_type != "blackjack":
            # Начисляем выигрыш
            if win_amount > 0:
                await Database.update_balance(user_id, win_amount, f'Выигрыш в {game_type}')
            
            # Отчисляем в джекпот
            jackpot_contribution = int(bet * JACKPOT_PERCENT)
            await Database.update_jackpot(jackpot_contribution)
            
            # Сохраняем историю
            await Database.add_game_history(user_id, game_type, bet, win_amount, result)
        elif game_type == "blackjack":
            # Для блэкджека сохраняем состояние
            self.blackjack_games[user_id] = {
                "game_state": result,
                "bet": bet,
                "active": True,
                "doubled": False,
                "insured": False
            }
        
        jackpot = await Database.get_jackpot()
        result_text = self.format_game_result(game_type, result, bet, win_amount)
        result_text += f"\n\n💰 Джекпот: **{jackpot} ⭐**"
        
        if game_type == "blackjack":
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard(game_type, self.blackjack_games.get(user_id))
            )
        elif game_type == "mines":
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard(game_type, self.active_games.get(user_id))
            )
        else:
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard(game_type)
            )
        
        logger.info(f"🎮 {user_id} сыграл в {game_type}, ставка {bet}, выигрыш {win_amount}")
    
    async def blackjack_hit(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        if user_id not in self.blackjack_games:
            await callback.answer("❌ Нет активной игры", show_alert=True)
            return
        
        game = self.blackjack_games[user_id]
        game_state = game["game_state"]
        
        # Берем карту
        game_state = self.games["blackjack"].hit(game_state)
        
        # Проверяем перебор
        if game_state["player_score"] > 21:
            win_amount = 0
            await Database.update_balance(user_id, -game["bet"], f'Проигрыш в блэкджек')
            await Database.add_game_history(user_id, "blackjack", game["bet"], 0, game_state)
            del self.blackjack_games[user_id]
            
            result_text = self.format_game_result("blackjack", game_state, game["bet"], 0)
            result_text += "\n\n❌ **ПЕРЕБОР!** Вы проиграли."
            
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard("blackjack")
            )
        else:
            self.blackjack_games[user_id]["game_state"] = game_state
            result_text = self.format_game_result("blackjack", game_state, game["bet"], 0)
            result_text += "\n\n🃏 **Взяли карту. Ваш ход.**"
            
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard("blackjack", self.blackjack_games[user_id])
            )
    
    async def blackjack_stand(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        if user_id not in self.blackjack_games:
            await callback.answer("❌ Нет активной игры", show_alert=True)
            return
        
        game = self.blackjack_games[user_id]
        game_state = game["game_state"]
        
        # Дилер играет
        game_state = self.games["blackjack"].dealer_play(game_state)
        
        # Рассчитываем выигрыш
        win_amount = self.games["blackjack"].calculate_win(game["bet"], game_state)
        
        if win_amount > game["bet"]:
            profit = win_amount - game["bet"]
            await Database.update_balance(user_id, profit, f'Выигрыш в блэкджек')
        elif win_amount == game["bet"]:
            # Возврат ставки
            await Database.update_balance(user_id, game["bet"], f'Возврат ставки в блэкджек')
        else:
            # Проигрыш, ставка уже списана
            pass
        
        # Отчисляем в джекпот
        jackpot_contribution = int(game["bet"] * JACKPOT_PERCENT)
        await Database.update_jackpot(jackpot_contribution)
        
        await Database.add_game_history(user_id, "blackjack", game["bet"], win_amount, game_state)
        del self.blackjack_games[user_id]
        
        jackpot = await Database.get_jackpot()
        result_text = self.format_game_result("blackjack", game_state, game["bet"], win_amount)
        result_text += f"\n\n💰 Джекпот: **{jackpot} ⭐**"
        
        await callback.message.edit_text(
            result_text,
            reply_markup=self.get_game_keyboard("blackjack")
        )
    
    async def mine_reveal(self, callback: CallbackQuery, cell: int):
        user_id = callback.from_user.id
        
        if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
            await callback.answer("❌ Нет активной игры в Mines", show_alert=True)
            return
        
        game = self.active_games[user_id]
        
        if cell in game["revealed"]:
            await callback.answer("❌ Клетка уже открыта", show_alert=True)
            return
        
        game["revealed"].append(cell)
        
        # Проверяем, не на мину ли наступили
        if cell in game["result"]["mine_positions"]:
            # Проигрыш
            win_amount = 0
            await Database.add_game_history(user_id, "mines", game["bet"], 0, game["result"])
            del self.active_games[user_id]
            
            # Отчисляем в джекпот
            jackpot_contribution = int(game["bet"] * JACKPOT_PERCENT)
            await Database.update_jackpot(jackpot_contribution)
            
            result_text = self.format_game_result("mines", game["result"], game["bet"], 0)
            result_text += "\n\n💥 **БАБАХ!** Вы наступили на мину и проиграли."
            
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard("mines")
            )
        else:
            # Продолжаем игру
            self.active_games[user_id] = game
            
            # Рассчитываем текущий возможный выигрыш
            current_win = self.games["mines"].calculate_win(game["bet"], game["result"], game["revealed"])
            
            result_text = self.format_game_result("mines", game["result"], game["bet"], current_win)
            result_text += f"\n\n✅ Безопасно! Текущий множитель: x{(current_win/game['bet']):.2f}"
            
            await callback.message.edit_text(
                result_text,
                reply_markup=self.get_game_keyboard("mines", game)
            )
    
    async def mine_cashout(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
            await callback.answer("❌ Нет активной игры в Mines", show_alert=True)
            return
        
        game = self.active_games[user_id]
        
        if not game["revealed"]:
            await callback.answer("❌ Откройте хотя бы одну клетку", show_alert=True)
            return
        
        win_amount = self.games["mines"].calculate_win(game["bet"], game["result"], game["revealed"])
        
        # Начисляем выигрыш
        await Database.update_balance(user_id, win_amount, f'Выигрыш в Mines')
        
        # Отчисляем в джекпот
        jackpot_contribution = int(game["bet"] * JACKPOT_PERCENT)
        await Database.update_jackpot(jackpot_contribution)
        
        await Database.add_game_history(user_id, "mines", game["bet"], win_amount, game["result"])
        del self.active_games[user_id]
        
        jackpot = await Database.get_jackpot()
        result_text = self.format_game_result("mines", game["result"], game["bet"], win_amount)
        result_text += f"\n\n✅ Вы забрали выигрыш: **{win_amount} ⭐**"
        result_text += f"\n💰 Джекпот: **{jackpot} ⭐**"
        
        await callback.message.edit_text(
            result_text,
            reply_markup=self.get_game_keyboard("mines")
        )
    
    def format_game_result(self, game_type: str, result: Dict, bet: int, win: int) -> str:
        if game_type == "slot":
            matrix = result["matrix"]
            result_str = "🎰 **СЛОТЫ**\n\n"
            for row in matrix:
                result_str += " | ".join(row) + "\n"
            if result.get("free_spins", 0) > 0:
                result_str += f"\n🎁 **ФРИСПИНЫ!** +{result['free_spins']}"
        elif game_type == "dice":
            if result.get("mode") == "double":
                result_str = f"🎲🎲 **КОСТИ (2 кубика)**\n\nСумма: **{result['result']}**\nМножитель: **x{result['multiplier']}**\n"
            else:
                result_str = f"🎲 **КОСТИ**\n\nРезультат: **{result['result']}**\nМножитель: **x{result['multiplier']}**\n"
        elif game_type == "roulette":
            result_str = f"🎡 **РУЛЕТКА**\n\nВыпало: **{result['number']}** {result['color']}\n"
        elif game_type == "blackjack":
            player_score = self.games["blackjack"].calculate_hand_score(result["player_hand"])
            dealer_score = self.games["blackjack"].calculate_hand_score(result["dealer_hand"])
            result_str = (
                f"🃏 **БЛЭКДЖЕК**\n\n"
                f"Ваши карты: {self.format_hand(result['player_hand'])} (очков: {player_score})\n"
                f"Карты дилера: {self.format_hand(result['dealer_hand'][:1])} + ?\n"
                f"Открытая карта дилера: {self.format_hand([result['dealer_hand'][0]])} (очков: {result['dealer_upcard_score']})\n"
            )
        elif game_type == "plinko":
            result_str = f"📌 **PLINKO**\n\nПозиция: **{result['final_position']}**\nМножитель: **x{result['multiplier']:.2f}**\nРиск: **{result['risk']}**\n"
        elif game_type == "mines":
            result_str = f"💣 **MINES**\n\nМин: **{result['mines_count']}**\n"
            if "revealed" in result:
                result_str += f"Открыто клеток: **{len(result['revealed'])}**\n"
        elif game_type == "keno":
            winning = result["winning_numbers"]
            result_str = f"🎯 **КЕНО**\n\nВыигрышные числа: {winning[:10]}...\n"
        else:
            result_str = f"Результат игры\n"
        
        result_str += f"\nСтавка: **{bet} ⭐**\n"
        if win > 0:
            profit = win - bet
            result_str += f"✅ Выигрыш: **{win} ⭐** (Профит: **+{profit} ⭐**)"
        elif win == bet:
            result_str += f"🔄 Возврат ставки: **{bet} ⭐**"
        else:
            result_str += f"❌ Проигрыш"
        
        if "hash" in result:
            result_str += f"\n\n🔐 Provably Fair: `{result['hash'][:16]}...`"
        
        return result_str
    
    def format_hand(self, hand: List) -> str:
        return " ".join([f"{rank}{suit}" for rank, suit in hand])
    
    async def admin_panel(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        if user_id not in ADMIN_IDS:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            users_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute('SELECT SUM(profit) FROM games')
            total_profit = (await cursor.fetchone())[0] or 0
            
            cursor = await db.execute('SELECT COUNT(*) FROM transactions WHERE status = "pending"')
            pending_withdrawals = (await cursor.fetchone())[0]
        
        jackpot = await Database.get_jackpot()
        
        admin_text = (
            f"👑 **АДМИН ПАНЕЛЬ**\n\n"
            f"📊 **Общая статистика:**\n"
            f"Пользователей: **{users_count}**\n"
            f"Общий профит казино: **{total_profit} ⭐**\n"
            f"Текущий джекпот: **{jackpot} ⭐**\n"
            f"Ожидающих выводов: **{pending_withdrawals}**\n\n"
            f"Выберите действие:"
        )
        
        await callback.message.edit_text(admin_text, reply_markup=self.get_admin_keyboard())
        logger.info(f"👑 Админ {user_id} открыл админ-панель")
    
    async def admin_stats(self, callback: CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Общая статистика
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            users_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute('SELECT COUNT(*) FROM games')
            games_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute('SELECT SUM(bet_amount), SUM(win_amount), SUM(profit) FROM games')
            row = await cursor.fetchone()
            total_bets = row[0] or 0
            total_wins = row[1] or 0
            total_profit = row[2] or 0
            
            cursor = await db.execute('SELECT SUM(balance) FROM users')
            total_balance = (await cursor.fetchone())[0] or 0
            
            # Статистика по играм
            game_stats = {}
            for game_type in self.games.keys():
                cursor = await db.execute('''
                    SELECT COUNT(*), SUM(bet_amount), SUM(profit) 
                    FROM games WHERE game_type = ?
                ''', (game_type,))
                row = await cursor.fetchone()
                game_stats[game_type] = {
                    'count': row[0] or 0,
                    'bets': row[1] or 0,
                    'profit': row[2] or 0
                }
        
        jackpot = await Database.get_jackpot()
        
        text = (
            f"📊 **ДЕТАЛЬНАЯ СТАТИСТИКА**\n\n"
            f"👥 **Пользователи:**\n"
            f"Всего: {users_count}\n"
            f"Общий баланс: {total_balance} ⭐\n\n"
            f"🎮 **Игры:**\n"
            f"Всего игр: {games_count}\n"
            f"Сумма ставок: {total_bets} ⭐\n"
            f"Сумма выигрышей: {total_wins} ⭐\n"
            f"Профит казино: {total_profit} ⭐\n"
            f"RTP: {(total_wins/total_bets*100):.2f}%" if total_bets > 0 else "RTP: 0%\n\n"
            f"\n📈 **По играм:**\n"
        )
        
        for game_type, stats in game_stats.items():
            text += f"{game_type}: {stats['count']} игр, профит {stats['profit']} ⭐\n"
        
        text += f"\n💰 Джекпот: {jackpot} ⭐"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
        )
    
    async def admin_users_list(self, callback: CallbackQuery, page: int = 0):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        users = await Database.get_all_users(limit=10, offset=page*10)
        total_users = await Database.get_users_count()
        
        text = f"👥 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ** (страница {page+1})\n\n"
        
        for i, user in enumerate(users, page*10 + 1):
            status = "🚫" if user['is_banned'] else "✅"
            text += f"{i}. {status} ID: {user['user_id']}"
            if user['username']:
                text += f" (@{user['username']})"
            text += f"\n   Баланс: {user['balance']} ⭐, Игр: {user['total_bets']}, VIP: {user['vip_level']}\n\n"
        
        buttons = []
        nav_buttons = []
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_users_page_{page-1}"))
        if (page+1)*10 < total_users:
            nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"admin_users_page_{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def admin_user_search(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_user_id)
        await state.update_data(admin_action="search_user")
        
        await callback.message.edit_text(
            "🔍 **Поиск пользователя**\n\nВведите ID пользователя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
            ])
        )
    
    async def admin_user_search_username(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_user_id)
        await state.update_data(admin_action="search_username")
        
        await callback.message.edit_text(
            "🔍 **Поиск по username**\n\nВведите username (без @):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
            ])
        )
    
    async def admin_balance_action(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_user_id)
        await state.update_data(admin_action="balance_change")
        
        await callback.message.edit_text(
            "💰 **Управление балансом**\n\nВведите ID пользователя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
        )
    
    async def admin_bonus_create(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_bonus_code)
        await state.update_data(admin_action="create_bonus")
        
        await callback.message.edit_text(
            "🎁 **Создание бонус кода**\n\nВведите код (например, WELCOME100):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_bonuses_menu")]
            ])
        )
    
    async def admin_bonuses_list(self, callback: CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        codes = await Database.get_bonus_codes()
        
        text = "🎁 **СПИСОК БОНУС КОДОВ**\n\n"
        
        if not codes:
            text += "Нет созданных кодов"
        else:
            for code in codes:
                text += f"Код: `{code['code']}`\n"
                text += f"Сумма: {code['amount']} ⭐\n"
                text += f"Использовано: {code['used_count']}/{code['max_uses']}\n"
                text += f"Истекает: {code['expires_at'] or 'никогда'}\n"
                text += f"Создан: {code['created_at']}\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_bonuses_menu")]
            ])
        )
    
    async def admin_tournament_create(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_tournament_name)
        await state.update_data(admin_action="create_tournament")
        
        await callback.message.edit_text(
            "🏆 **Создание турнира**\n\nВведите название турнира:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_tournaments_menu")]
            ])
        )
    
    async def admin_tournaments_list(self, callback: CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        tournaments = await Database.get_all_tournaments()
        
        text = "🏆 **СПИСОК ТУРНИРОВ**\n\n"
        
        if not tournaments:
            text += "Нет созданных турниров"
        else:
            for t in tournaments:
                status_emoji = "🟢" if t['status'] == 'active' else "🔴" if t['status'] == 'ended' else "⚪"
                text += f"{status_emoji} **{t['name']}**\n"
                text += f"ID: {t['tournament_id']}\n"
                text += f"Приз: {t['prize_pool']} ⭐\n"
                text += f"Игра: {t['game_type']}\n"
                text += f"Статус: {t['status']}\n"
                text += f"Начало: {t['start_date']}\n"
                text += f"Конец: {t['end_date']}\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_tournaments_menu")]
            ])
        )
    
    async def admin_withdrawals(self, callback: CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM transactions 
                WHERE type = 'withdrawal' AND status = 'pending'
                ORDER BY created_at ASC
            ''')
            withdrawals = await cursor.fetchall()
        
        text = "💸 **ЗАЯВКИ НА ВЫВОД**\n\n"
        
        if not withdrawals:
            text += "Нет ожидающих заявок"
        else:
            for w in withdrawals:
                w = dict(w)
                text += f"ID: `{w['transaction_id']}`\n"
                text += f"Пользователь: {w['user_id']}\n"
                text += f"Сумма: {w['amount']} ⭐\n"
                text += f"Кошелек: {w['wallet_address']}\n"
                text += f"Дата: {w['created_at']}\n"
                text += f"[Подтвердить](confirm_{w['transaction_id']}) | [Отклонить](reject_{w['transaction_id']})\n\n"
        
        buttons = [
            [InlineKeyboardButton(text="✅ Подтвердить все", callback_data="admin_withdrawals_confirm_all")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
        ]
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            disable_web_page_preview=True
        )
    
    async def admin_broadcast(self, callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            return
        
        await state.set_state(BetStates.waiting_for_broadcast_message)
        
        await callback.message.edit_text(
            "📢 **РАССЫЛКА**\n\nВведите сообщение для рассылки всем пользователям:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
        )
    
    async def process_broadcast(self, message: Message, state: FSMContext):
        if message.from_user.id not in ADMIN_IDS:
            await state.clear()
            return
        
        text = message.text
        
        # Получаем всех пользователей
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT user_id FROM users')
            users = await cursor.fetchall()
        
        status_msg = await message.answer(f"📤 Начинаю рассылку... 0/{len(users)}")
        
        success = 0
        failed = 0
        
        for i, (user_id,) in enumerate(users, 1):
            try:
                await bot.send_message(user_id, text)
                success += 1
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            
            if i % 10 == 0:
                await status_msg.edit_text(f"📤 Рассылка... {i}/{len(users)} (✅ {success}, ❌ {failed})")
            
            await asyncio.sleep(0.05)  # Чтобы не флудить
        
        await status_msg.edit_text(f"✅ Рассылка завершена!\nУспешно: {success}\nОшибок: {failed}")
        await state.clear()
    
    async def show_tournaments(self, callback: CallbackQuery):
        tournaments = await Database.get_active_tournaments()
        
        if not tournaments:
            await callback.message.edit_text(
                "🏆 **ТУРНИРЫ**\n\nВ данный момент нет активных турниров.\nСледите за обновлениями!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
            )
            return
        
        text = "🏆 **АКТИВНЫЕ ТУРНИРЫ**\n\n"
        buttons = []
        
        for tournament in tournaments:
            time_left = datetime.fromisoformat(tournament['end_date']) - datetime.now()
            hours_left = int(time_left.total_seconds() / 3600)
            minutes_left = int((time_left.total_seconds() % 3600) / 60)
            
            text += (
                f"**{tournament['name']}**\n"
                f"Призовой фонд: {tournament['prize_pool']} ⭐\n"
                f"Игра: {tournament['game_type']}\n"
                f"Мин. ставка: {tournament['min_bet']} ⭐\n"
                f"Осталось: {hours_left}ч {minutes_left}м\n\n"
            )
            
            buttons.append([InlineKeyboardButton(
                text=f"📊 {tournament['name']} - таблица",
                callback_data=f"tournament_{tournament['tournament_id']}"
            )])
        
        buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_tournament(self, callback: CallbackQuery, tournament_id: int):
        leaderboard = await Database.get_tournament_leaderboard(tournament_id, 10)
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT * FROM tournaments WHERE tournament_id = ?', (tournament_id,))
            tournament = await cursor.fetchone()
        
        if not tournament:
            await callback.answer("❌ Турнир не найден", show_alert=True)
            return
        
        text = f"🏆 **{tournament[1]}**\n\n"
        text += f"Призовой фонд: {tournament[2]} ⭐\n"
        text += f"Игра: {tournament[4]}\n\n"
        text += "**Текущая таблица:**\n"
        
        if not leaderboard:
            text += "Пока нет участников"
        else:
            for i, player in enumerate(leaderboard, 1):
                text += f"{i}. {player['username'] or f'ID{player['user_id']}'}: {player['score']} очков\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад к турнирам", callback_data="tournaments")]
            ])
        )
    
    async def show_bonuses(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT value FROM settings WHERE key = "faucet_amount"')
            faucet_amount = int((await cursor.fetchone())[0])
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "faucet_cooldown"')
            faucet_cooldown = int((await cursor.fetchone())[0])
            
            cursor = await db.execute('''
                SELECT created_at FROM transactions 
                WHERE user_id = ? AND type = 'faucet' 
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            last_faucet = await cursor.fetchone()
        
        now = datetime.now()
        can_claim = True
        time_left = 0
        
        if last_faucet:
            last_time = datetime.fromisoformat(last_faucet[0])
            time_passed = (now - last_time).total_seconds()
            if time_passed < faucet_cooldown:
                can_claim = False
                time_left = faucet_cooldown - time_passed
        
        can_daily, streak, daily_bonus = await Database.get_daily_reward(user_id)
        
        text = (
            "🎁 **БОНУСЫ И НАГРАДЫ**\n\n"
            f"📅 **Ежедневный бонус**\n"
            f"Текущая серия: {streak} дней\n"
            f"Сумма: {daily_bonus} ⭐\n"
            f"Доступен: {'✅' if can_daily else '❌'}\n\n"
            f"💧 **Кран**\n"
            f"Сумма: {faucet_amount} ⭐\n"
            f"Перезарядка: {faucet_cooldown // 60} мин\n"
            f"Доступен: {'✅' if can_claim else '❌'}\n"
            f"{f'Следующий через: {int(time_left // 60)} мин {int(time_left % 60)} сек' if not can_claim else ''}\n\n"
            f"🎫 **Бонус коды**\n"
            f"Введите код для активации"
        )
        
        buttons = [
            [InlineKeyboardButton(text="📅 Забрать ежедневный", callback_data="claim_daily")],
            [InlineKeyboardButton(text="💧 Забрать с крана", callback_data="claim_faucet")],
            [InlineKeyboardButton(text="🎫 Активировать код", callback_data="activate_bonus")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def claim_daily(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        can_claim, streak, bonus = await Database.get_daily_reward(user_id)
        
        if not can_claim:
            await callback.answer("❌ Вы уже получали сегодняшний бонус", show_alert=True)
            return
        
        await Database.update_balance(user_id, bonus, f'Ежедневный бонус (день {streak})')
        
        await callback.answer(f"✅ Получено {bonus} ⭐! Серия: {streak} дней", show_alert=True)
        await self.show_bonuses(callback)
    
    async def claim_faucet(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT value FROM settings WHERE key = "faucet_cooldown"')
            cooldown = int((await cursor.fetchone())[0])
            
            cursor = await db.execute('''
                SELECT created_at FROM transactions 
                WHERE user_id = ? AND type = 'faucet' 
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            last_faucet = await cursor.fetchone()
            
            now = datetime.now()
            if last_faucet:
                last_time = datetime.fromisoformat(last_faucet[0])
                if (now - last_time).total_seconds() < cooldown:
                    time_left = cooldown - (now - last_time).total_seconds()
                    await callback.answer(f"❌ Подождите {int(time_left // 60)} мин {int(time_left % 60)} сек", show_alert=True)
                    return
            
            cursor = await db.execute('SELECT value FROM settings WHERE key = "faucet_amount"')
            amount = int((await cursor.fetchone())[0])
            
            await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            await db.execute('''
                INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(uuid.uuid4()), user_id, amount, 'faucet', 'completed', 'Кран'))
            
            await db.commit()
        
        await callback.answer(f"✅ Получено {amount} ⭐!", show_alert=True)
        await self.show_bonuses(callback)
    
    async def show_referrals(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
            referrals_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute('''
                SELECT SUM(profit) FROM games WHERE user_id IN 
                (SELECT user_id FROM users WHERE referred_by = ?)
            ''', (user_id,))
            referrals_profit = (await cursor.fetchone())[0] or 0
        
        bot_username = (await bot.me()).username
        
        text = (
            f"👥 **РЕФЕРАЛЬНАЯ ПРОГРАММА**\n\n"
            f"Ваша реферальная ссылка:\n"
            f"`https://t.me/{bot_username}?start={user['referral_code']}`\n\n"
            f"Приглашено друзей: **{referrals_count}**\n"
            f"Профит рефералов: **{referrals_profit} ⭐**\n"
            f"Ваш бонус: **{referrals_count * 50} ⭐**\n\n"
            f"Как это работает:\n"
            f"1. Отправьте ссылку другу\n"
            f"2. Друг регистрируется по ссылке\n"
            f"3. Вы получаете 50 ⭐ на баланс\n"
            f"4. Друг получает 100 ⭐ приветственного бонуса"
        )
        
        buttons = [
            [InlineKeyboardButton(text="📊 Статистика рефералов", callback_data="referral_stats")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_stats(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        top_players = await Database.get_top_players(5)
        top_rich = await Database.get_top_players_by_balance(5)
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT COUNT(*), SUM(profit) FROM games WHERE user_id = ?
            ''', (user_id,))
            row = await cursor.fetchone()
            games_count = row[0] or 0
            total_profit = row[1] or 0
            
            cursor = await db.execute('''
                SELECT game_type, COUNT(*) FROM games WHERE user_id = ? GROUP BY game_type
            ''', (user_id,))
            games_by_type = await cursor.fetchall()
        
        win_rate = (user['total_wins'] / user['total_bets'] * 100) if user['total_bets'] > 0 else 0
        
        stats_text = "📊 **СТАТИСТИКА**\n\n"
        
        stats_text += f"**Ваша статистика:**\n"
        stats_text += f"Всего игр: {games_count}\n"
        stats_text += f"Побед: {user['total_wins']}\n"
        stats_text += f"Поражений: {user['total_losses']}\n"
        stats_text += f"Винрейт: {win_rate:.1f}%\n"
        stats_text += f"Общий профит: {total_profit} ⭐\n"
        stats_text += f"Макс выигрыш: {user['biggest_win']} ⭐\n"
        stats_text += f"Макс проигрыш: {user['biggest_loss']} ⭐\n\n"
        
        if games_by_type:
            stats_text += "**По играм:**\n"
            for game_type, count in games_by_type:
                stats_text += f"{game_type}: {count} игр\n"
            stats_text += "\n"
        
        stats_text += "**Топ-5 по победам:**\n"
        for i, player in enumerate(top_players, 1):
            name = player['username'] or f"ID{player['user_id']}"
            stats_text += f"{i}. {name}: {player['total_wins']} побед ({player['win_rate']:.1f}%)\n"
        
        stats_text += "\n**Топ-5 по балансу:**\n"
        for i, player in enumerate(top_rich, 1):
            name = player['username'] or f"ID{player['user_id']}"
            stats_text += f"{i}. {name}: {player['balance']} ⭐ (VIP {player['vip_level']})\n"
        
        buttons = [
            [InlineKeyboardButton(text="📈 Моя история игр", callback_data="game_history")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(stats_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_history(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM games 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 10
            ''', (user_id,))
            games = await cursor.fetchall()
        
        text = "📜 **ИСТОРИЯ ИГР**\n\n"
        
        if not games:
            text += "У вас пока нет сыгранных игр"
        else:
            for game in games:
                game = dict(game)
                profit_emoji = "✅" if game['profit'] > 0 else "❌" if game['profit'] < 0 else "🔄"
                text += f"{profit_emoji} {game['game_type']}: ставка {game['bet_amount']} ⭐, "
                text += f"выигрыш {game['win_amount']} ⭐ (профит {game['profit']} ⭐)\n"
                text += f"   {game['created_at']}\n\n"
        
        buttons = [
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_settings(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        text = (
            f"⚙️ **НАСТРОЙКИ**\n\n"
            f"Язык: {'🇷🇺 Русский' if user['language'] == 'ru' else '🇬🇧 English'}\n"
            f"Уведомления: ✅\n\n"
            f"Выберите настройку для изменения:"
        )
        
        buttons = [
            [InlineKeyboardButton(text="🌐 Сменить язык", callback_data="change_language")],
            [InlineKeyboardButton(text="🔐 Provably Fair", callback_data="provably_fair_info")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def provably_fair_info(self, callback: CallbackQuery):
        text = (
            "🔐 **PROVABLY FAIR**\n\n"
            "Все игры в нашем казино используют систему Provably Fair, "
            "которая позволяет вам проверить честность каждого раунда.\n\n"
            "**Как это работает:**\n"
            "1. Сервер генерирует seed и отправляет вам его хеш до начала игры\n"
            "2. Вы можете добавить свой client seed\n"
            "3. После игры вы можете проверить, что результат был честным\n\n"
            "**Проверка результата:**\n"
            "Каждая игра показывает хеш результата. Вы можете использовать любой "
            "онлайн-инструмент для проверки SHA-256 хеша, чтобы убедиться, "
            "что результат не был изменен после вашей ставки."
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="settings")]
            ])
        )
    
    async def change_language(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('UPDATE users SET language = "en" WHERE user_id = ?', (user_id,))
            await db.commit()
        
        await callback.answer("🇬🇧 Language changed to English", show_alert=True)
        await self.show_settings(callback)
    
    async def callback_handler(self, callback: CallbackQuery, state: FSMContext):
        data = callback.data
        
        # Главное меню
        if data == "main_menu":
            user_id = callback.from_user.id
            await callback.message.edit_text(
                "🎰 **ГЛАВНОЕ МЕНЮ**\n\nВыберите игру:",
                reply_markup=self.get_main_keyboard(user_id)
            )
        
        # Баланс и транзакции
        elif data == "balance":
            await self.cmd_balance(callback.message)
        elif data == "deposit":
            await self.deposit(callback, state)
        elif data == "withdraw":
            await self.withdraw(callback, state)
        elif data == "transaction_history":
            transactions = await Database.get_transactions(callback.from_user.id, 10)
            text = "📜 **ИСТОРИЯ ТРАНЗАКЦИЙ**\n\n"
            if not transactions:
                text += "Нет транзакций"
            else:
                for tx in transactions:
                    status_emoji = "✅" if tx['status'] == 'completed' else "⏳" if tx['status'] == 'pending' else "❌"
                    text += f"{status_emoji} {tx['type']}: {tx['amount']} ⭐ ({tx['status']})\n"
                    text += f"   {tx['description']}\n"
                    text += f"   {tx['created_at']}\n\n"
            
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="balance")]
                ])
            )
        
        # Игры
        elif data.startswith("game_"):
            game_type = data.replace("game_", "")
            if game_type in self.games:
                await callback.message.edit_text(
                    f"🎮 **{game_type.upper()}**\n\nВыберите ставку:",
                    reply_markup=self.get_game_keyboard(game_type)
                )
            else:
                await callback.answer(f"❌ Игра временно недоступна", show_alert=True)
        
        elif data.startswith("play_"):
            parts = data.split("_")
            if len(parts) < 3:
                await callback.answer("❌ Неверный формат", show_alert=True)
                return
            game_type = parts[1]
            try:
                bet = int(parts[2])
            except ValueError:
                await callback.answer("❌ Неверная сумма", show_alert=True)
                return
            await self.play_game(callback, game_type, bet)
        
        elif data.startswith("custom_bet_"):
            game_type = data.replace("custom_bet_", "")
            await state.set_state(BetStates.waiting_for_bet)
            await state.update_data(game_type=game_type)
            await callback.message.edit_text(
                f"💰 **СВОЯ СТАВКА**\n\nВведите сумму (от {MIN_BET} до {MAX_BET}):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"game_{game_type}")]
                ])
            )
        
        # Специальные для игр
        elif data == "dice_single":
            await state.set_state(BetStates.waiting_for_bet)
            await state.update_data(game_type="dice", mode="single")
            await callback.message.edit_text(
                "🎲 **КОСТИ (1 кубик)**\n\nВведите сумму ставки:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]
                ])
            )
        elif data == "dice_double":
            await state.set_state(BetStates.waiting_for_bet)
            await state.update_data(game_type="dice", mode="double")
            await callback.message.edit_text(
                "🎲🎲 **КОСТИ (2 кубика)**\n\nВведите сумму ставки:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]
                ])
            )
        
        elif data.startswith("roulette_"):
            bet_type = data.replace("roulette_", "")
            if bet_type == "bet":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="roulette")
                await callback.message.edit_text(
                    "🎡 **РУЛЕТКА**\n\nВведите сумму ставки:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                    ])
                )
            elif bet_type == "number":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="roulette", bet_type="straight")
                await callback.message.edit_text(
                    "🎯 **СТАВКА НА ЧИСЛО**\n\nВведите число (0-36) и сумму через пробел\nНапример: 7 100",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                    ])
                )
            elif bet_type == "columns":
                buttons = [
                    [InlineKeyboardButton(text="1-я колонка", callback_data="roulette_column_1"),
                     InlineKeyboardButton(text="2-я колонка", callback_data="roulette_column_2")],
                    [InlineKeyboardButton(text="3-я колонка", callback_data="roulette_column_3")],
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="game_roulette")]
                ]
                await callback.message.edit_text(
                    "📊 **ВЫБЕРИТЕ КОЛОНКУ**",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )
            elif bet_type.startswith("column_"):
                column = bet_type.replace("column_", "")
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="roulette", bet_type="column", bet_number=int(column))
                await callback.message.edit_text(
                    f"📊 **СТАВКА НА {column}-ю КОЛОНКУ**\n\nВведите сумму:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                    ])
                )
            elif bet_type.startswith("dozen"):
                dozen = bet_type.replace("dozen", "")
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="roulette", bet_type="dozen", bet_number=int(dozen))
                await callback.message.edit_text(
                    f"📊 **СТАВКА НА {dozen}-ю ДЮЖИНУ**\n\nВведите сумму:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                    ])
                )
            else:
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="roulette", bet_type=bet_type)
                await callback.message.edit_text(
                    f"🎡 **СТАВКА НА {bet_type}**\n\nВведите сумму:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                    ])
                )
        
        elif data.startswith("plinko_"):
            risk = data.replace("plinko_", "")
            if risk in ["low", "medium", "high", "extreme"]:
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="plinko", risk=risk)
                await callback.message.edit_text(
                    f"📌 **PLINKO ({risk} риск)**\n\nВведите сумму ставки:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]
                    ])
                )
            elif risk.isdigit():
                bet = int(risk)
                await self.play_game(callback, "plinko", bet, risk="medium")
            elif risk == "bet":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="plinko")
                await callback.message.edit_text(
                    "📌 **PLINKO**\n\nВведите сумму ставки (риск: средний):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]
                    ])
                )
        
        elif data.startswith("mines_"):
            parts = data.split("_")
            if len(parts) == 3 and parts[1] in ["easy", "medium", "hard", "extreme"]:
                difficulty = parts[1]
                mines = int(parts[2])
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="mines", mines_count=mines, difficulty=difficulty)
                await callback.message.edit_text(
                    f"💣 **MINES ({difficulty}, {mines} мин)**\n\nВведите сумму ставки:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                    ])
                )
            elif data == "mines_bet":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="mines", mines_count=5, difficulty="medium")
                await callback.message.edit_text(
                    "💣 **MINES**\n\nВведите сумму ставки (5 мин, средний риск):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                    ])
                )
            elif data == "mines_cashout":
                await self.mine_cashout(callback)
            elif data == "mines_new":
                if callback.from_user.id in self.active_games:
                    del self.active_games[callback.from_user.id]
                await callback.message.edit_text(
                    "💣 **MINES**\n\nВыберите сложность:",
                    reply_markup=self.get_game_keyboard("mines")
                )
            elif data.startswith("mine_cell_"):
                cell = int(data.replace("mine_cell_", ""))
                await self.mine_reveal(callback, cell)
        
        elif data.startswith("keno_"):
            parts = data.split("_")
            if len(parts) == 3 and parts[1] == "pick":
                picks = int(parts[2])
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="keno", picks_count=picks)
                await callback.message.edit_text(
                    f"🎯 **КЕНО ({picks} чисел)**\n\nВведите {picks} чисел от 1 до 80 через пробел и сумму\nНапример: 5 12 33 45 100",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]
                    ])
                )
            elif parts[1].isdigit():
                bet = int(parts[1])
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="keno", picks_count=5)
                await callback.message.edit_text(
                    f"🎯 **КЕНО (5 чисел)**\n\nВведите 5 чисел от 1 до 80 через пробел\nНапример: 5 12 33 45 78",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]
                    ])
                )
            elif parts[1] == "bet":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="keno", picks_count=5)
                await callback.message.edit_text(
                    "🎯 **КЕНО**\n\nВведите 5 чисел от 1 до 80 через пробел и сумму\nНапример: 5 12 33 45 78 100",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]
                    ])
                )
        
        # Блэкджек
        elif data == "blackjack_hit":
            await self.blackjack_hit(callback)
        elif data == "blackjack_stand":
            await self.blackjack_stand(callback)
        elif data == "blackjack_double":
            user_id = callback.from_user.id
            if user_id not in self.blackjack_games:
                await callback.answer("❌ Нет активной игры", show_alert=True)
                return
            
            game = self.blackjack_games[user_id]
            user = await Database.get_user(user_id)
            
            if user['balance'] < game['bet']:
                await callback.answer("❌ Недостаточно средств для удвоения", show_alert=True)
                return
            
            # Списываем дополнительную ставку
            await Database.update_balance(user_id, -game['bet'], 'Удвоение в блэкджек')
            game['bet'] *= 2
            game['doubled'] = True
            
            # Берем карту
            game['game_state'] = self.games["blackjack"].hit(game['game_state'])
            
            if game['game_state']["player_score"] > 21:
                # Перебор
                win_amount = 0
                await Database.add_game_history(user_id, "blackjack", game['bet'], 0, game['game_state'])
                del self.blackjack_games[user_id]
                
                result_text = self.format_game_result("blackjack", game['game_state'], game['bet'], 0)
                result_text += "\n\n❌ **ПЕРЕБОР!** Вы проиграли."
                
                await callback.message.edit_text(
                    result_text,
                    reply_markup=self.get_game_keyboard("blackjack")
                )
            else:
                # Автоматически заканчиваем
                await self.blackjack_stand(callback)
        
        elif data == "blackjack_insurance":
            user_id = callback.from_user.id
            if user_id not in self.blackjack_games:
                await callback.answer("❌ Нет активной игры", show_alert=True)
                return
            
            game = self.blackjack_games[user_id]
            user = await Database.get_user(user_id)
            
            insurance_cost = game['bet'] // 2
            if user['balance'] < insurance_cost:
                await callback.answer("❌ Недостаточно средств для страховки", show_alert=True)
                return
            
            # Списываем страховку
            await Database.update_balance(user_id, -insurance_cost, 'Страховка в блэкджек')
            game['insured'] = True
            
            # Проверяем блэкджек дилера
            dealer_score = self.games["blackjack"].calculate_hand_score(game['game_state']["dealer_hand"])
            if dealer_score == 21 and len(game['game_state']["dealer_hand"]) == 2:
                # Страховка сработала
                win_amount = insurance_cost * 2
                await Database.update_balance(user_id, win_amount, 'Выигрыш страховки в блэкджек')
                await callback.answer(f"✅ Страховка сработала! Выигрыш {win_amount} ⭐", show_alert=True)
            
            await callback.message.edit_text(
                self.format_game_result("blackjack", game['game_state'], game['bet'], 0),
                reply_markup=self.get_game_keyboard("blackjack", game)
            )
        
        elif data == "blackjack_new":
            if callback.from_user.id in self.blackjack_games:
                del self.blackjack_games[callback.from_user.id]
            await callback.message.edit_text(
                "🃏 **БЛЭКДЖЕК**\n\nВыберите ставку:",
                reply_markup=self.get_game_keyboard("blackjack")
            )
        
        # Турниры
        elif data == "tournaments":
            await self.show_tournaments(callback)
        elif data.startswith("tournament_"):
            tournament_id = int(data.replace("tournament_", ""))
            await self.show_tournament(callback, tournament_id)
        
        # Бонусы
        elif data == "bonuses":
            await self.show_bonuses(callback)
        elif data == "claim_daily":
            await self.claim_daily(callback)
        elif data == "claim_faucet":
            await self.claim_faucet(callback)
        elif data == "activate_bonus":
            await state.set_state(BetStates.waiting_for_bonus_code)
            await state.update_data(admin_action="use_bonus")
            await callback.message.edit_text(
                "🎫 **АКТИВАЦИЯ БОНУС КОДА**\n\nВведите код:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="bonuses")]
                ])
            )
        
        # Рефералы
        elif data == "referrals":
            await self.show_referrals(callback)
        elif data == "referral_stats":
            user_id = callback.from_user.id
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT u.user_id, u.username, u.balance, u.total_bets, u.join_date
                    FROM users u
                    WHERE u.referred_by = ?
                    ORDER BY u.join_date DESC
                ''', (user_id,))
                referrals = await cursor.fetchall()
            
            text = "📊 **СТАТИСТИКА РЕФЕРАЛОВ**\n\n"
            if not referrals:
                text += "У вас пока нет рефералов"
            else:
                for i, ref in enumerate(referrals, 1):
                    ref = dict(ref)
                    text += f"{i}. ID: {ref['user_id']}"
                    if ref['username']:
                        text += f" (@{ref['username']})"
                    text += f"\n   Баланс: {ref['balance']} ⭐, Игр: {ref['total_bets']}\n"
                    text += f"   Зарегистрирован: {ref['join_date']}\n\n"
            
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="referrals")]
                ])
            )
        
        # Статистика и история
        elif data == "stats":
            await self.show_stats(callback)
        elif data == "history":
            await self.show_history(callback)
        elif data == "game_history":
            user_id = callback.from_user.id
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT * FROM games 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT 20
                ''', (user_id,))
                games = await cursor.fetchall()
            
            text = "📊 **ДЕТАЛЬНАЯ ИСТОРИЯ ИГР**\n\n"
            if not games:
                text += "У вас пока нет сыгранных игр"
            else:
                for game in games:
                    game = dict(game)
                    profit_emoji = "✅" if game['profit'] > 0 else "❌" if game['profit'] < 0 else "🔄"
                    text += f"{profit_emoji} {game['game_type']}: {game['bet_amount']} ⭐ → {game['win_amount']} ⭐\n"
                    text += f"   {game['created_at']}\n\n"
            
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="stats")]
                ])
            )
        
        # Настройки
        elif data == "settings":
            await self.show_settings(callback)
        elif data == "change_language":
            await self.change_language(callback)
        elif data == "provably_fair_info":
            await self.provably_fair_info(callback)
        
        # Админ панель
        elif data == "admin_panel":
            await self.admin_panel(callback)
        elif data == "admin_stats":
            await self.admin_stats(callback)
        elif data == "admin_users_menu":
            if callback.from_user.id in ADMIN_IDS:
                await callback.message.edit_text(
                    "👥 **УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ**\n\nВыберите действие:",
                    reply_markup=self.get_users_menu_keyboard()
                )
        elif data == "admin_users_list":
            await self.admin_users_list(callback, 0)
        elif data.startswith("admin_users_page_"):
            page = int(data.replace("admin_users_page_", ""))
            await self.admin_users_list(callback, page)
        elif data == "admin_user_search":
            await self.admin_user_search(callback, state)
        elif data == "admin_user_search_username":
            await self.admin_user_search_username(callback, state)
        elif data == "admin_user_ban":
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="ban_user")
            await callback.message.edit_text(
                "⛔ **БЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ**\n\nВведите ID пользователя:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
                ])
            )
        elif data == "admin_user_unban":
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="unban_user")
            await callback.message.edit_text(
                "✅ **РАЗБЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ**\n\nВведите ID пользователя:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
                ])
            )
        elif data == "admin_user_make_admin":
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="make_admin")
            await callback.message.edit_text(
                "👑 **НАЗНАЧЕНИЕ АДМИНА**\n\nВведите ID пользователя:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_users_menu")]
                ])
            )
        
        elif data == "admin_balance":
            await self.admin_balance_action(callback, state)
        elif data == "admin_rtp":
            if callback.from_user.id in ADMIN_IDS:
                rtp_settings = await Database.get_rtp_settings()
                text = "🎮 **НАСТРОЙКИ RTP**\n\n"
                text += f"Отображаемый RTP: **{RTP_DISPLAY}%**\n"
                text += f"Базовый RTP: **{RTP_ACTUAL}%**\n\n"
                text += "Текущие настройки по играм:\n"
                
                buttons = []
                game_names = {
                    "slot": "🎰 Слоты", "dice": "🎲 Кости", "roulette": "🎡 Рулетка",
                    "blackjack": "🃏 Блэкджек", "plinko": "📌 Plinko", "mines": "💣 Mines",
                    "keno": "🎯 Кено"
                }
                
                for game_type, game_name in game_names.items():
                    settings = rtp_settings.get(game_type, {})
                    current = settings.get('current_rtp', RTP_ACTUAL)
                    text += f"{game_name}: **{current:.2f}%**\n"
                    buttons.append([InlineKeyboardButton(
                        text=f"Изменить {game_name}",
                        callback_data=f"admin_rtp_{game_type}"
                    )])
                
                buttons.append([InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")])
                
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        
        elif data.startswith("admin_rtp_"):
            if callback.from_user.id in ADMIN_IDS:
                game_type = data.replace("admin_rtp_", "")
                await state.set_state(BetStates.waiting_for_rtp_change)
                await state.update_data(game_type=game_type)
                await callback.message.edit_text(
                    f"🎮 **ИЗМЕНЕНИЕ RTP**\n\nВведите новое значение RTP для {game_type} (70-85%):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_rtp")]
                    ])
                )
        
        elif data == "admin_tournaments_menu":
            if callback.from_user.id in ADMIN_IDS:
                await callback.message.edit_text(
                    "🏆 **УПРАВЛЕНИЕ ТУРНИРАМИ**\n\nВыберите действие:",
                    reply_markup=self.get_tournaments_menu_keyboard()
                )
        elif data == "admin_tournament_create":
            await self.admin_tournament_create(callback, state)
        elif data == "admin_tournaments_list":
            await self.admin_tournaments_list(callback)
        elif data == "admin_tournament_end":
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="end_tournament")
            await callback.message.edit_text(
                "⏹ **ЗАВЕРШЕНИЕ ТУРНИРА**\n\nВведите ID турнира:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_tournaments_menu")]
                ])
            )
        
        elif data == "admin_bonuses_menu":
            if callback.from_user.id in ADMIN_IDS:
                await callback.message.edit_text(
                    "🎁 **УПРАВЛЕНИЕ БОНУС КОДАМИ**\n\nВыберите действие:",
                    reply_markup=self.get_bonuses_menu_keyboard()
                )
        elif data == "admin_bonus_create":
            await self.admin_bonus_create(callback, state)
        elif data == "admin_bonuses_list":
            await self.admin_bonuses_list(callback)
        
        elif data == "admin_withdrawals":
            await self.admin_withdrawals(callback)
        elif data.startswith("confirm_"):
            if callback.from_user.id in ADMIN_IDS:
                tx_id = data.replace("confirm_", "")
                await Database.update_transaction_status(tx_id, 'completed')
                
                # Получаем информацию о транзакции
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    cursor = await db.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                    row = await cursor.fetchone()
                    if row:
                        user_id, amount = row
                        # Средства уже списаны при создании заявки
                        await bot.send_message(
                            user_id,
                            f"✅ Ваш вывод на {amount} ⭐ подтвержден и отправлен!"
                        )
                
                await callback.answer("✅ Вывод подтвержден", show_alert=True)
                await self.admin_withdrawals(callback)
        elif data.startswith("reject_"):
            if callback.from_user.id in ADMIN_IDS:
                tx_id = data.replace("reject_", "")
                await Database.update_transaction_status(tx_id, 'rejected')
                
                # Возвращаем средства
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    cursor = await db.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                    row = await cursor.fetchone()
                    if row:
                        user_id, amount = row
                        await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
                        await db.commit()
                        
                        await bot.send_message(
                            user_id,
                            f"❌ Ваш вывод на {amount} ⭐ отклонен. Средства возвращены на баланс."
                        )
                
                await callback.answer("❌ Вывод отклонен", show_alert=True)
                await self.admin_withdrawals(callback)
        elif data == "admin_withdrawals_confirm_all":
            if callback.from_user.id in ADMIN_IDS:
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    cursor = await db.execute('''
                        SELECT transaction_id, user_id, amount FROM transactions 
                        WHERE type = 'withdrawal' AND status = 'pending'
                    ''')
                    withdrawals = await cursor.fetchall()
                    
                    for tx_id, user_id, amount in withdrawals:
                        await db.execute('UPDATE transactions SET status = "completed" WHERE transaction_id = ?', (tx_id,))
                        try:
                            await bot.send_message(
                                user_id,
                                f"✅ Ваш вывод на {amount} ⭐ подтвержден и отправлен!"
                            )
                        except:
                            pass
                    
                    await db.commit()
                
                await callback.answer(f"✅ Подтверждено {len(withdrawals)} выводов", show_alert=True)
                await self.admin_withdrawals(callback)
        
        elif data == "admin_broadcast":
            await self.admin_broadcast(callback, state)
        elif data == "admin_settings":
            if callback.from_user.id in ADMIN_IDS:
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    cursor = await db.execute('SELECT key, value FROM settings ORDER BY key')
                    settings = await cursor.fetchall()
                
                text = "⚙️ **НАСТРОЙКИ КАЗИНО**\n\n"
                for key, value in settings:
                    text += f"{key}: {value}\n"
                
                buttons = [
                    [InlineKeyboardButton(text="💰 Изменить мин. вывод", callback_data="admin_setting_min_withdrawal")],
                    [InlineKeyboardButton(text="💰 Изменить комиссию", callback_data="admin_setting_withdrawal_fee")],
                    [InlineKeyboardButton(text="🎁 Изменить приветственный бонус", callback_data="admin_setting_welcome_bonus")],
                    [InlineKeyboardButton(text="👥 Изменить реферальный бонус", callback_data="admin_setting_referral_bonus")],
                    [InlineKeyboardButton(text="💧 Изменить сумму крана", callback_data="admin_setting_faucet_amount")],
                    [InlineKeyboardButton(text="⏱ Изменить перезарядку крана", callback_data="admin_setting_faucet_cooldown")],
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
                ]
                
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        
        elif data.startswith("admin_setting_"):
            if callback.from_user.id in ADMIN_IDS:
                setting = data.replace("admin_setting_", "")
                await state.set_state(BetStates.waiting_for_admin_action)
                await state.update_data(admin_action=f"setting_{setting}")
                
                descriptions = {
                    "min_withdrawal": "💰 Введите минимальную сумму вывода:",
                    "withdrawal_fee": "💰 Введите комиссию за вывод (в %):",
                    "welcome_bonus": "🎁 Введите приветственный бонус:",
                    "referral_bonus": "👥 Введите реферальный бонус:",
                    "faucet_amount": "💧 Введите сумму крана:",
                    "faucet_cooldown": "⏱ Введите перезарядку крана (в минутах):"
                }
                
                await callback.message.edit_text(
                    descriptions.get(setting, "Введите новое значение:"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_settings")]
                    ])
                )
        
        elif data == "admin_logs":
            if callback.from_user.id in ADMIN_IDS:
                await callback.message.edit_text(
                    "📈 **ЛОГИ И БЭКАП**\n\n"
                    "Функция в разработке. Скоро здесь будут логи и возможность бэкапа БД.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
                    ])
                )
        
        await callback.answer()

# ============================================
# СОЗДАЕМ ЭКЗЕМПЛЯР БОТА
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
    await casino_bot.cmd_balance(message)

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await casino_bot.admin_panel(CallbackQuery(
            id='',
            from_user=message.from_user,
            message=message,
            data='admin_panel'
        ))

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    await casino_bot.callback_handler(callback, state)

@dp.message(BetStates.waiting_for_bet)
async def handle_custom_bet(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        game_type = data.get('game_type')
        bet_type = data.get('bet_type')
        bet_number = data.get('bet_number')
        risk = data.get('risk')
        mode = data.get('mode')
        mines_count = data.get('mines_count', 5)
        difficulty = data.get('difficulty', 'medium')
        picks_count = data.get('picks_count', 5)
        
        parts = message.text.split()
        
        if game_type == "keno":
            if len(parts) < picks_count + 1:
                await message.answer(f"❌ Введите {picks_count} чисел и сумму")
                return
            
            try:
                picks = [int(p) for p in parts[:-1]]
                bet = int(parts[-1])
                
                if any(p < 1 or p > 80 for p in picks):
                    await message.answer("❌ Числа должны быть от 1 до 80")
                    return
                if len(set(picks)) != len(picks):
                    await message.answer("❌ Числа не должны повторяться")
                    return
            except ValueError:
                await message.answer("❌ Введите числа и сумму")
                return
            
        elif game_type == "roulette" and bet_type == "straight":
            if len(parts) != 2:
                await message.answer("❌ Введите число и сумму через пробел")
                return
            try:
                bet_number = int(parts[0])
                bet = int(parts[1])
                if bet_number < 0 or bet_number > 36:
                    await message.answer("❌ Число должно быть от 0 до 36")
                    return
            except ValueError:
                await message.answer("❌ Введите число и сумму")
                return
        else:
            try:
                bet = int(message.text)
            except ValueError:
                await message.answer("❌ Введите число")
                return
        
        if bet < MIN_BET or bet > MAX_BET:
            await message.answer(f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET}")
            return
        
        await state.clear()
        
        user = await Database.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден. Напишите /start")
            return
        
        if user['balance'] < bet:
            await message.answer(f"❌ Недостаточно средств. Баланс: {user['balance']} ⭐")
            return
        
        kwargs = {}
        if bet_type:
            kwargs["bet_type"] = bet_type
        if bet_number is not None:
            kwargs["bet_number"] = bet_number
        if risk:
            kwargs["risk"] = risk
        if mode:
            kwargs["mode"] = mode
        if mines_count:
            kwargs["mines_count"] = mines_count
        if difficulty:
            kwargs["difficulty"] = difficulty
        if game_type == "keno" and picks:
            kwargs["picks"] = picks
        
        # Создаем callback и запускаем игру
        await casino_bot.play_game(
            CallbackQuery(
                id='',
                from_user=message.from_user,
                message=message,
                data=f'play_{game_type}_{bet}'
            ),
            game_type,
            bet,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Ошибка в custom bet: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте снова.")

@dp.message(BetStates.waiting_for_deposit_amount)
async def handle_deposit(message: Message, state: FSMContext):
    await casino_bot.process_deposit(message, state)

@dp.message(BetStates.waiting_for_withdrawal_amount)
async def handle_withdrawal_amount(message: Message, state: FSMContext):
    await casino_bot.process_withdrawal_amount(message, state)

@dp.message(BetStates.waiting_for_withdrawal_address)
async def handle_withdrawal_address(message: Message, state: FSMContext):
    await casino_bot.process_withdrawal_address(message, state)

@dp.message(BetStates.waiting_for_bonus_code)
async def handle_bonus_code(message: Message, state: FSMContext):
    data = await state.get_data()
    admin_action = data.get('admin_action')
    
    if admin_action == "create_bonus":
        if message.from_user.id not in ADMIN_IDS:
            await state.clear()
            return
        
        code = message.text.upper()
        await state.update_data(bonus_code=code)
        await state.set_state(BetStates.waiting_for_bonus_code_amount)
        await message.answer(
            f"🎁 Введите сумму для кода {code}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonuses_menu")]
            ])
        )
    elif admin_action == "use_bonus":
        code = message.text.upper()
        user_id = message.from_user.id
        
        result = await Database.use_bonus_code(code, user_id)
        
        if result is None:
            await message.answer("❌ Недействительный бонус код")
        elif result == -1:
            await message.answer("❌ Вы уже использовали этот код")
        else:
            await message.answer(f"✅ Бонус активирован! Получено {result} ⭐")
        
        await state.clear()

@dp.message(BetStates.waiting_for_bonus_code_amount)
async def handle_bonus_code_amount(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        amount = int(message.text)
        if amount < 1 or amount > 100000:
            await message.answer("❌ Сумма должна быть от 1 до 100000")
            return
        
        await state.update_data(bonus_amount=amount)
        await state.set_state(BetStates.waiting_for_bonus_code_uses)
        await message.answer(
            "🎁 Введите максимальное количество использований (0 для безлимита):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonuses_menu")]
            ])
        )
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_bonus_code_uses)
async def handle_bonus_code_uses(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        max_uses = int(message.text)
        if max_uses < 0:
            await message.answer("❌ Количество использований не может быть отрицательным")
            return
        
        await state.update_data(bonus_max_uses=max_uses)
        await state.set_state(BetStates.waiting_for_bonus_code_expiry)
        await message.answer(
            "🎁 Введите срок действия в часах (0 для бессрочного):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonuses_menu")]
            ])
        )
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_bonus_code_expiry)
async def handle_bonus_code_expiry(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        hours = int(message.text)
        data = await state.get_data()
        code = data.get('bonus_code')
        amount = data.get('bonus_amount')
        max_uses = data.get('bonus_max_uses')
        
        expires_at = None
        if hours > 0:
            expires_at = datetime.now() + timedelta(hours=hours)
        
        await Database.create_bonus_code(code, amount, max_uses, expires_at, message.from_user.id)
        
        await state.clear()
        await message.answer(f"✅ Бонус код {code} создан!")
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_rtp_change)
async def handle_rtp_change(message: Message, state: FSMContext):
    try:
        new_rtp = float(message.text)
        if new_rtp < 70 or new_rtp > 85:
            await message.answer("❌ RTP должен быть от 70% до 85%")
            return
        
        data = await state.get_data()
        game_type = data.get('game_type')
        
        await Database.update_rtp_settings(game_type, new_rtp, message.from_user.id)
        await state.clear()
        
        await message.answer(f"✅ RTP для {game_type} изменен на {new_rtp}%")
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_user_id)
async def handle_user_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    data = await state.get_data()
    action = data.get('admin_action')
    
    if action == "search_user":
        try:
            user_id = int(message.text)
            user = await Database.get_user(user_id)
            
            if not user:
                await message.answer("❌ Пользователь не найден")
                await state.clear()
                return
            
            text = f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
            text += f"ID: {user['user_id']}\n"
            text += f"Username: @{user['username'] if user['username'] else 'нет'}\n"
            text += f"Имя: {user['first_name']} {user['last_name'] or ''}\n"
            text += f"Баланс: {user['balance']} ⭐\n"
            text += f"Игр: {user['total_bets']}\n"
            text += f"Побед: {user['total_wins']}\n"
            text += f"VIP: {user['vip_level']}\n"
            text += f"Регистрация: {user['join_date']}\n"
            text += f"Бан: {'✅' if user['is_banned'] else '❌'}\n"
            
            await message.answer(text)
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите ID пользователя")
    
    elif action == "search_username":
        username = message.text.replace('@', '')
        user = await Database.get_user_by_username(username)
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return
        
        text = f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
        text += f"ID: {user['user_id']}\n"
        text += f"Username: @{user['username']}\n"
        text += f"Имя: {user['first_name']} {user['last_name'] or ''}\n"
        text += f"Баланс: {user['balance']} ⭐\n"
        text += f"Игр: {user['total_bets']}\n"
        text += f"Побед: {user['total_wins']}\n"
        text += f"VIP: {user['vip_level']}\n"
        text += f"Регистрация: {user['join_date']}\n"
        text += f"Бан: {'✅' if user['is_banned'] else '❌'}\n"
        
        await message.answer(text)
        await state.clear()
    
    elif action == "balance_change":
        try:
            user_id = int(message.text)
            await state.update_data(target_user_id=user_id)
            await state.set_state(BetStates.waiting_for_balance_amount)
            await message.answer(
                f"💰 Введите сумму для изменения баланса пользователя {user_id} (может быть отрицательной):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
                ])
            )
        except ValueError:
            await message.answer("❌ Введите ID пользователя")
    
    elif action == "ban_user":
        try:
            user_id = int(message.text)
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
                await db.commit()
            await message.answer(f"✅ Пользователь {user_id} заблокирован")
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите ID пользователя")
    
    elif action == "unban_user":
        try:
            user_id = int(message.text)
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
                await db.commit()
            await message.answer(f"✅ Пользователь {user_id} разблокирован")
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите ID пользователя")
    
    elif action == "make_admin":
        try:
            user_id = int(message.text)
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
                await db.commit()
            await message.answer(f"👑 Пользователь {user_id} назначен админом")
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите ID пользователя")
    
    elif action == "end_tournament":
        try:
            tournament_id = int(message.text)
            leaderboard = await Database.end_tournament(tournament_id)
            
            if leaderboard:
                text = f"🏆 Турнир #{tournament_id} завершен!\n\nПобедители:\n"
                prizes = [50, 30, 20]
                for i, player in enumerate(leaderboard):
                    if i < 3:
                        text += f"{i+1}. {player['username'] or 'Аноним'}: {prizes[i]}% от призового фонда\n"
                await message.answer(text)
            else:
                await message.answer(f"🏆 Турнир #{tournament_id} завершен (нет участников)")
            
            await state.clear()
        except ValueError:
            await message.answer("❌ Введите ID турнира")

@dp.message(BetStates.waiting_for_balance_amount)
async def handle_balance_amount(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        amount = int(message.text)
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        
        if await Database.update_balance(target_user_id, amount, f'Админ: {message.from_user.id}'):
            await message.answer(f"✅ Баланс пользователя {target_user_id} изменен на {amount} ⭐")
            
            # Уведомляем пользователя
            try:
                action = "начислено" if amount > 0 else "списано"
                await bot.send_message(
                    target_user_id,
                    f"💰 Администратор {action} {abs(amount)} ⭐ на вашем балансе."
                )
            except:
                pass
        else:
            await message.answer("❌ Не удалось изменить баланс")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_tournament_name)
async def handle_tournament_name(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    name = message.text
    await state.update_data(tournament_name=name)
    await state.set_state(BetStates.waiting_for_tournament_prize)
    await message.answer(
        "🏆 Введите призовой фонд турнира (в ⭐):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_tournaments_menu")]
        ])
    )

@dp.message(BetStates.waiting_for_tournament_prize)
async def handle_tournament_prize(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        prize = int(message.text)
        if prize < 100:
            await message.answer("❌ Призовой фонд должен быть не менее 100 ⭐")
            return
        
        await state.update_data(tournament_prize=prize)
        await state.set_state(BetStates.waiting_for_tournament_game)
        
        # Клавиатура с выбором игры
        buttons = []
        for game_type in casino_bot.games.keys():
            buttons.append([InlineKeyboardButton(
                text=game_type,
                callback_data=f"tournament_game_{game_type}"
            )])
        
        await message.answer(
            "🏆 Выберите игру для турнира:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except ValueError:
        await message.answer("❌ Введите число")

@dp.callback_query(lambda c: c.data.startswith("tournament_game_"))
async def tournament_game_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    game_type = callback.data.replace("tournament_game_", "")
    await state.update_data(tournament_game=game_type)
    await state.set_state(BetStates.waiting_for_tournament_duration)
    
    await callback.message.edit_text(
        "🏆 Введите длительность турнира (в часах):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_tournaments_menu")]
        ])
    )

@dp.message(BetStates.waiting_for_tournament_duration)
async def handle_tournament_duration(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        hours = int(message.text)
        if hours < 1 or hours > 168:
            await message.answer("❌ Длительность должна быть от 1 до 168 часов")
            return
        
        await state.update_data(tournament_hours=hours)
        await state.set_state(BetStates.waiting_for_tournament_min_bet)
        await message.answer(
            "🏆 Введите минимальную ставку для участия в турнире:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_tournaments_menu")]
            ])
        )
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_tournament_min_bet)
async def handle_tournament_min_bet(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    try:
        min_bet = int(message.text)
        if min_bet < 1:
            await message.answer("❌ Минимальная ставка должна быть не менее 1 ⭐")
            return
        
        data = await state.get_data()
        name = data.get('tournament_name')
        prize = data.get('tournament_prize')
        game_type = data.get('tournament_game')
        hours = data.get('tournament_hours')
        
        tournament_id = await Database.create_tournament(name, prize, game_type, hours, min_bet, message.from_user.id)
        
        await state.clear()
        await message.answer(
            f"✅ Турнир создан!\n\n"
            f"ID: {tournament_id}\n"
            f"Название: {name}\n"
            f"Приз: {prize} ⭐\n"
            f"Игра: {game_type}\n"
            f"Длительность: {hours} часов\n"
            f"Мин. ставка: {min_bet} ⭐"
        )
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_admin_action)
async def handle_admin_setting(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    data = await state.get_data()
    action = data.get('admin_action')
    
    if action and action.startswith("setting_"):
        setting = action.replace("setting_", "")
        
        try:
            value = int(message.text)
            
            # Конвертируем минуты в секунды для faucet_cooldown
            if setting == "faucet_cooldown":
                value = value * 60
            
            await Database.update_setting(setting, str(value))
            await state.clear()
            await message.answer(f"✅ Настройка {setting} обновлена на {message.text}")
        except ValueError:
            await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_broadcast_message)
async def handle_broadcast(message: Message, state: FSMContext):
    await casino_bot.process_broadcast(message, state)

# ============================================
# ОБРАБОТЧИКИ ПЛАТЕЖЕЙ
# ============================================
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id
    amount = message.successful_payment.total_amount // 100  # Переводим из копеек в звезды
    
    # Обновляем баланс
    await Database.update_balance(user_id, amount, f'Пополнение через Stars')
    
    # Записываем транзакцию
    await Database.add_transaction(
        user_id=user_id,
        amount=amount,
        tx_type='deposit',
        status='completed',
        description=f'Пополнение через Telegram Stars',
        wallet_address=None
    )
    
    await message.answer(f"✅ Баланс успешно пополнен на {amount} ⭐!")

# ============================================
# ПРОВЕРКА ЗАВЕРШЕННЫХ ТУРНИРОВ (ФОНОВАЯ ЗАДАЧА)
# ============================================
async def check_tournaments_background():
    """Проверяет завершенные турниры каждые 10 минут"""
    while True:
        try:
            await Database.check_expired_tournaments()
            await asyncio.sleep(600)  # 10 минут
        except Exception as e:
            logger.error(f"Ошибка при проверке турниров: {e}")
            await asyncio.sleep(60)

# ============================================
# БЭКАП БАЗЫ ДАННЫХ (ФОНОВАЯ ЗАДАЧА)
# ============================================
async def backup_database_background():
    """Создает бэкап базы данных каждые 6 часов"""
    while True:
        try:
            await asyncio.sleep(21600)  # 6 часов
            
            # Создаем копию базы данных
            backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            
            if os.path.exists(DATABASE_PATH):
                import shutil
                shutil.copy2(DATABASE_PATH, f"/tmp/{backup_filename}")
                logger.info(f"✅ Бэкап базы данных создан: {backup_filename}")
                
                # Здесь можно добавить загрузку в облачное хранилище
        except Exception as e:
            logger.error(f"Ошибка при создании бэкапа: {e}")

# ============================================
# ОЧИСТКА СТАРЫХ ИГР (ФОНОВАЯ ЗАДАЧА)
# ============================================
async def cleanup_old_games_background():
    """Удаляет игры старше 30 дней каждые 24 часа"""
    while True:
        try:
            await asyncio.sleep(86400)  # 24 часа
            
            thirty_days_ago = datetime.now() - timedelta(days=30)
            
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('''
                    DELETE FROM games 
                    WHERE created_at < ?
                ''', (thirty_days_ago,))
                await db.commit()
                
                logger.info("✅ Старые игры удалены")
        except Exception as e:
            logger.error(f"Ошибка при очистке старых игр: {e}")

# ============================================
# ОБНОВЛЕНИЕ VIP СТАТУСОВ (ФОНОВАЯ ЗАДАЧА)
# ============================================
async def update_vip_status_background():
    """Обновляет VIP статусы пользователей каждые 24 часа"""
    while True:
        try:
            await asyncio.sleep(86400)  # 24 часа
            
            async with aiosqlite.connect(DATABASE_PATH) as db:
                # Обновляем VIP уровни на основе опыта
                await db.execute('''
                    UPDATE users SET 
                        vip_level = CASE
                            WHEN experience >= 10000 THEN 5
                            WHEN experience >= 5000 THEN 4
                            WHEN experience >= 2000 THEN 3
                            WHEN experience >= 500 THEN 2
                            WHEN experience >= 100 THEN 1
                            ELSE 0
                        END
                ''')
                await db.commit()
                
                logger.info("✅ VIP статусы обновлены")
        except Exception as e:
            logger.error(f"Ошибка при обновлении VIP статусов: {e}")

# ============================================
# HTTP-СЕРВЕР ДЛЯ RENDER
# ============================================
async def run_http_server():
    """Запускает минимальный HTTP-сервер для проверки порта Render."""
    app = web.Application()
    
    async def handle(request):
        return web.Response(text="Mega Casino Bot is running!")

    async def handle_stats(request):
        # Простая статистика для мониторинга
        users_count = await Database.get_users_count()
        jackpot = await Database.get_jackpot()
        
        return web.Response(
            text=json.dumps({
                "status": "online",
                "users": users_count,
                "jackpot": jackpot,
                "timestamp": datetime.now().isoformat()
            }),
            content_type="application/json"
        )

    app.router.add_get('/', handle)
    app.router.add_get('/health', handle)
    app.router.add_get('/stats', handle_stats)
    
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ HTTP-сервер для Render запущен на порту {port}")

# ============================================
# ЗАПУСК БОТА
# ============================================
async def main():
    # Инициализируем базу данных
    await init_db()
    
    # Запускаем фоновые задачи
    asyncio.create_task(run_http_server())
    asyncio.create_task(check_tournaments_background())
    asyncio.create_task(backup_database_background())
    asyncio.create_task(cleanup_old_games_background())
    asyncio.create_task(update_vip_status_background())
    
    logger.info("🚀 Бот запускается...")
    logger.info(f"👑 Админы: {ADMIN_IDS}")
    logger.info(f"🎮 Игр загружено: {len(casino_bot.games)}")
    
    # Запускаем бота
    await dp.start_polling(bot)

# Создаем экземпляр бота (убедимся, что он создан после всех определений)
casino_bot = CasinoBot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
