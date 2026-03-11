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
    waiting_for_withdrawal = State()
    waiting_for_custom_game_params = State()
    waiting_for_admin_action = State()
    waiting_for_rtp_change = State()
    waiting_for_bonus_code = State()
    waiting_for_faucet = State()

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
                status TEXT
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
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                        ('faucet_amount', '10'))
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                        ('faucet_cooldown', '3600'))
        
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
    async def create_user(user_id: int, username: str = None, first_name: str = None, 
                         last_name: str = None, referred_by: int = None):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            referral_code = Database.generate_referral_code()
            await db.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, referral_code, referred_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, referral_code, referred_by))
            
            if referred_by:
                await db.execute('''
                    UPDATE users SET balance = balance + 50 WHERE user_id = ?
                ''', (referred_by,))
            
            await db.commit()
            logger.info(f"✅ Пользователь {user_id} создан/обновлен")
    
    @staticmethod
    def generate_referral_code(length: int = 8) -> str:
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
    
    @staticmethod
    async def update_balance(user_id: int, amount: int) -> bool:
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
            await db.commit()
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
                UPDATE rtp_settings SET 
                    current_rtp = ?,
                    last_modified = CURRENT_TIMESTAMP,
                    modified_by = ?
                WHERE game_type = ?
            ''', (new_rtp, admin_id, game_type))
            
            if db.total_changes == 0:
                await db.execute('''
                    INSERT INTO rtp_settings (game_type, base_rtp, current_rtp, modified_by)
                    VALUES (?, ?, ?, ?)
                ''', (game_type, RTP_ACTUAL, new_rtp, admin_id))
            
            await db.commit()
    
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
# КЛАСС ДЛЯ ИГРЫ В СЛОТЫ
# ============================================
class SlotGame(BaseGame):
    def __init__(self):
        super().__init__("slot")
        self.symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐", "🎰"]
        self.symbol_values = {
            "🍒": 2, "🍋": 3, "🍊": 4, "🍇": 5,
            "💎": 10, "7️⃣": 20, "⭐": 50, "🎰": 100
        }
        self.reels = 5
        self.rows = 3
    
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
        
        win_amount = self.calculate_win(bet, {"matrix": matrix})
        
        return {
            "matrix": matrix,
            "win_amount": win_amount,
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
            if all(s == symbols[0] for s in symbols):
                multiplier = self.symbol_values.get(symbols[0], 1)
                win += bet * multiplier
        
        rtp_factor = self.actual_rtp / 100.0
        win = int(win * rtp_factor)
        
        if random.random() < 0.001:
            jackpot = asyncio.run(Database.get_jackpot())
            win += jackpot
            if win > 0:
                asyncio.create_task(Database.reset_jackpot(result.get("user_id", 0)))
        
        return win
    
    def get_paylines(self) -> List[List[int]]:
        return [
            [0, 0, 0, 0, 0],
            [1, 1, 1, 1, 1],
            [2, 2, 2, 2, 2],
            [0, 1, 2, 1, 0],
            [2, 1, 0, 1, 2],
            [0, 0, 1, 2, 2],
            [2, 2, 1, 0, 0],
        ]

# ============================================
# КЛАСС ДЛЯ ИГРЫ В КОСТИ
# ============================================
class DiceGame(BaseGame):
    def __init__(self):
        super().__init__("dice")
        self.multipliers = {1: 6, 2: 3, 3: 2, 4: 1.5, 5: 1.2, 6: 1}
    
    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        seed = self.get_provably_fair_seed(server_seed, client_seed, nonce)
        result = self.get_random_number(1, 6, seed)
        
        return {
            "result": result,
            "multiplier": self.multipliers[result],
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": seed
        }
    
    def calculate_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["multiplier"])

# ============================================
# КЛАСС ДЛЯ РУЛЕТКИ
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
    
    def calculate_win(self, bet: int, result: Dict, bet_type: str = "red", bet_number: int = None) -> int:
        number = result["number"]
        
        if bet_type == "straight" and bet_number == number:
            return bet * 36
        elif bet_type == "red" and self.colors[number] == "red":
            return bet * 2
        elif bet_type == "black" and self.colors[number] == "black":
            return bet * 2
        elif bet_type == "even" and number > 0 and number % 2 == 0:
            return bet * 2
        elif bet_type == "odd" and number % 2 == 1:
            return bet * 2
        elif bet_type == "low" and 1 <= number <= 18:
            return bet * 2
        elif bet_type == "high" and 19 <= number <= 36:
            return bet * 2
        
        return 0

# ============================================
# КЛАСС ДЛЯ БЛЭКДЖЕКА
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
    
    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        deck = [(rank, suit) for suit in self.suits for rank in self.ranks]
        shuffled_deck = self.shuffle_deck(deck, server_seed, client_seed, nonce)
        
        player_hand = [shuffled_deck[0], shuffled_deck[2]]
        dealer_hand = [shuffled_deck[1], shuffled_deck[3]]
        remaining_deck = shuffled_deck[4:]
        
        return {
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "deck": remaining_deck,
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
    
    def calculate_win(self, bet: int, result: Dict, player_stands: bool = True) -> int:
        player_hand = result["player_hand"]
        dealer_hand = result["dealer_hand"]
        remaining_deck = result.get("deck", [])
        
        player_score = self.calculate_hand_score(player_hand)
        dealer_score = self.calculate_hand_score(dealer_hand)
        
        while dealer_score < 17 and remaining_deck:
            dealer_hand.append(remaining_deck.pop(0))
            dealer_score = self.calculate_hand_score(dealer_hand)
        
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
# КЛАСС ДЛЯ PLINKO
# ============================================
class PlinkoGame(BaseGame):
    def __init__(self):
        super().__init__("plinko")
        self.rows = 16
        self.multipliers = {
            16: [16, 9, 2, 1.4, 1.2, 1.1, 1, 0.5, 0.5, 1, 1.1, 1.2, 1.4, 2, 9, 16],
            15: [15, 8, 1.8, 1.3, 1.1, 1, 0.7, 0.5, 0.5, 0.7, 1, 1.1, 1.3, 1.8, 8, 15],
            14: [14, 7, 1.6, 1.2, 1, 0.8, 0.6, 0.4, 0.4, 0.6, 0.8, 1, 1.2, 1.6, 7, 14],
            13: [13, 6, 1.5, 1.1, 0.9, 0.7, 0.5, 0.3, 0.3, 0.5, 0.7, 0.9, 1.1, 1.5, 6, 13],
            12: [12, 5, 1.4, 1, 0.8, 0.6, 0.4, 0.2, 0.2, 0.4, 0.6, 0.8, 1, 1.4, 5, 12],
            11: [11, 4, 1.3, 0.9, 0.7, 0.5, 0.3, 0.1, 0.1, 0.3, 0.5, 0.7, 0.9, 1.3, 4, 11],
            10: [10, 3, 1.2, 0.8, 0.6, 0.4, 0.2, 0.1, 0.1, 0.2, 0.4, 0.6, 0.8, 1.2, 3, 10],
            9: [9, 2, 1.1, 0.7, 0.5, 0.3, 0.2, 0.1, 0.1, 0.2, 0.3, 0.5, 0.7, 1.1, 2, 9],
            8: [8, 1.5, 1, 0.6, 0.4, 0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.6, 1, 1.5, 8]
        }
    
    def generate_result(self, bet: int, user_id: int = None, risk: str = "medium") -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        risk_levels = {"low": 16, "medium": 14, "high": 12}
        rows = risk_levels.get(risk, 14)
        
        path = []
        position = 0
        
        for _ in range(rows):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + len(path))
            direction = self.get_random_number(0, 1, seed)
            if direction == 0:
                position -= 0.5
            else:
                position += 0.5
            path.append(direction)
        
        final_position = int(round(position + rows / 2))
        final_position = max(0, min(rows, final_position))
        
        multiplier = self.multipliers.get(rows, self.multipliers[14])[final_position]
        
        return {
            "path": path,
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
# КЛАСС ДЛЯ MINES
# ============================================
class MinesGame(BaseGame):
    def __init__(self):
        super().__init__("mines")
        self.grid_size = 5
        self.max_mines = 24
    
    def generate_result(self, bet: int, user_id: int = None, mines_count: int = 3) -> Dict:
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        nonce = secrets.randbelow(1000000)
        
        mine_positions = []
        all_positions = list(range(self.grid_size * self.grid_size))
        
        for i in range(mines_count):
            seed = self.get_provably_fair_seed(server_seed, client_seed, nonce + i)
            idx = self.get_random_number(0, len(all_positions) - 1, seed)
            mine_positions.append(all_positions.pop(idx))
        
        return {
            "mine_positions": mine_positions,
            "mines_count": mines_count,
            "grid_size": self.grid_size,
            "server_seed": server_seed,
            "client_seed": client_seed,
            "nonce": nonce,
            "hash": self.get_provably_fair_seed(server_seed, client_seed, nonce),
            "revealed": []
        }
    
    def calculate_win(self, bet: int, result: Dict, revealed_cells: List[int]) -> int:
        mine_positions = result["mine_positions"]
        mines_count = result["mines_count"]
        total_cells = self.grid_size * self.grid_size
        safe_cells = total_cells - mines_count
        
        if any(cell in mine_positions for cell in revealed_cells):
            return 0
        
        revealed_count = len(revealed_cells)
        if revealed_count == 0:
            return 0
        
        multiplier = (safe_cells) / (safe_cells - revealed_count + 1)
        
        return int(bet * multiplier)

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
            "mines": MinesGame()
        }
        self.active_games = {}
        logger.info(f"✅ Игры загружены: {list(self.games.keys())}")
    
    def get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="🎰 Слоты", callback_data="game_slot"),
             InlineKeyboardButton(text="🎲 Кости", callback_data="game_dice")],
            [InlineKeyboardButton(text="🎡 Рулетка", callback_data="game_roulette"),
             InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game_blackjack")],
            [InlineKeyboardButton(text="📌 Plinko", callback_data="game_plinko"),
             InlineKeyboardButton(text="💣 Mines", callback_data="game_mines")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
             InlineKeyboardButton(text="🏆 Турниры", callback_data="tournaments")],
            [InlineKeyboardButton(text="🎁 Бонусы", callback_data="bonuses"),
             InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
             InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
        ]
        
        if user_id in ADMIN_IDS:
            buttons.append([InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")])
            logger.info(f"👑 Админ-панель показана для пользователя {user_id}")
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_game_keyboard(self, game_type: str, game_state: Dict = None) -> InlineKeyboardMarkup:
        buttons = []
        
        if game_type == "slot":
            buttons = [
                [InlineKeyboardButton(text="🎰 Крутить (10⭐)", callback_data="play_slot_10"),
                 InlineKeyboardButton(text="🎰 Крутить (50⭐)", callback_data="play_slot_50")],
                [InlineKeyboardButton(text="🎰 Крутить (100⭐)", callback_data="play_slot_100"),
                 InlineKeyboardButton(text="🎰 Крутить (500⭐)", callback_data="play_slot_500")],
                [InlineKeyboardButton(text="💰 Макс ставка", callback_data="play_slot_1000"),
                 InlineKeyboardButton(text="🔧 Своя ставка", callback_data="custom_bet_slot")]
            ]
        elif game_type == "dice":
            buttons = [
                [InlineKeyboardButton(text="🎲 Бросить (10⭐)", callback_data="play_dice_10"),
                 InlineKeyboardButton(text="🎲 Бросить (50⭐)", callback_data="play_dice_50")],
                [InlineKeyboardButton(text="🎲 Бросить (100⭐)", callback_data="play_dice_100"),
                 InlineKeyboardButton(text="🎲 Бросить (500⭐)", callback_data="play_dice_500")],
                [InlineKeyboardButton(text="🔧 Своя ставка", callback_data="custom_bet_dice")]
            ]
        elif game_type == "roulette":
            buttons = [
                [InlineKeyboardButton(text="🔴 Красное", callback_data="roulette_red"),
                 InlineKeyboardButton(text="⚫ Черное", callback_data="roulette_black")],
                [InlineKeyboardButton(text="👤 Четное", callback_data="roulette_even"),
                 InlineKeyboardButton(text="👥 Нечетное", callback_data="roulette_odd")],
                [InlineKeyboardButton(text="1️⃣ 1-18", callback_data="roulette_low"),
                 InlineKeyboardButton(text="2️⃣ 19-36", callback_data="roulette_high")],
                [InlineKeyboardButton(text="💰 Ставка", callback_data="roulette_bet")]
            ]
        elif game_type == "blackjack":
            buttons = [
                [InlineKeyboardButton(text="🃏 Играть (10⭐)", callback_data="play_blackjack_10"),
                 InlineKeyboardButton(text="🃏 Играть (50⭐)", callback_data="play_blackjack_50")],
                [InlineKeyboardButton(text="🃏 Играть (100⭐)", callback_data="play_blackjack_100"),
                 InlineKeyboardButton(text="🔧 Своя ставка", callback_data="custom_bet_blackjack")]
            ]
        elif game_type == "plinko":
            buttons = [
                [InlineKeyboardButton(text="📌 Низкий риск", callback_data="plinko_low"),
                 InlineKeyboardButton(text="📌 Средний риск", callback_data="plinko_medium")],
                [InlineKeyboardButton(text="📌 Высокий риск", callback_data="plinko_high"),
                 InlineKeyboardButton(text="💰 Ставка", callback_data="plinko_bet")]
            ]
        elif game_type == "mines":
            buttons = [
                [InlineKeyboardButton(text="💣 3 мины", callback_data="mines_3"),
                 InlineKeyboardButton(text="💣 5 мин", callback_data="mines_5")],
                [InlineKeyboardButton(text="💣 10 мин", callback_data="mines_10"),
                 InlineKeyboardButton(text="💰 Ставка", callback_data="mines_bet")]
            ]
        
        buttons.append([
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    def get_admin_keyboard(self) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats"),
             InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="💰 Управление балансом", callback_data="admin_balance"),
             InlineKeyboardButton(text="🎮 Настройки RTP", callback_data="admin_rtp")],
            [InlineKeyboardButton(text="🏆 Турниры", callback_data="admin_tournaments"),
             InlineKeyboardButton(text="🎁 Бонус коды", callback_data="admin_bonuses")],
            [InlineKeyboardButton(text="⚙️ Общие настройки", callback_data="admin_settings"),
             InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
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
        
        await Database.create_user(user_id, username, first_name, last_name, referred_by)
        user = await Database.get_user(user_id)
        
        welcome_text = (
            f"🎰 Добро пожаловать в **Mega Casino**!\n\n"
            f"Самый высокий RTP в Telegram — **{RTP_DISPLAY}%**!\n"
            f"👤 Ваш ID: `{user_id}`\n"
            f"💰 Баланс: {user['balance'] if user else 0} ⭐\n\n"
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
            await message.answer("❌ Пользователь не найден. Напишите /start")
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*), SUM(profit) FROM games WHERE user_id = ?', (user_id,))
            games_count, total_profit = await cursor.fetchone()
        
        balance_text = (
            f"💰 **Ваш баланс**\n\n"
            f"Баланс: **{user['balance']} ⭐**\n"
            f"Всего игр: **{games_count or 0}**\n"
            f"Общий профит: **{total_profit or 0} ⭐**\n"
            f"VIP уровень: **{user['vip_level']}**\n\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(balance_text, reply_markup=keyboard)
    
    async def play_game(self, callback: CallbackQuery, game_type: str, bet: int, **kwargs):
        user_id = callback.from_user.id
        
        user = await Database.get_user(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден. Напишите /start", show_alert=True)
            return
        
        if user['balance'] < bet:
            await callback.answer("❌ Недостаточно средств", show_alert=True)
            return
        
        game = self.games.get(game_type)
        if not game:
            await callback.answer("❌ Игра временно недоступна", show_alert=True)
            return
        
        if game_type == "roulette" and "bet_type" in kwargs:
            result = game.generate_result(bet, user_id)
            win_amount = game.calculate_win(bet, result, kwargs["bet_type"])
        elif game_type == "plinko" and "risk" in kwargs:
            result = game.generate_result(bet, user_id, kwargs["risk"])
            win_amount = game.calculate_win(bet, result)
        elif game_type == "mines" and "mines_count" in kwargs:
            result = game.generate_result(bet, user_id, kwargs["mines_count"])
            win_amount = 0
            self.active_games[user_id] = {
                "game": "mines",
                "result": result,
                "bet": bet,
                "revealed": []
            }
        else:
            result = game.generate_result(bet, user_id)
            win_amount = game.calculate_win(bet, result)
        
        if game_type != "mines":
            profit = win_amount - bet
            await Database.update_balance(user_id, profit)
            
            jackpot_contribution = int(bet * JACKPOT_PERCENT)
            await Database.update_jackpot(jackpot_contribution)
            
            await Database.add_game_history(user_id, game_type, bet, win_amount, result)
        
        jackpot = await Database.get_jackpot()
        result_text = self.format_game_result(game_type, result, bet, win_amount)
        result_text += f"\n\n💰 Джекпот: **{jackpot} ⭐**"
        
        await callback.message.edit_text(
            result_text,
            reply_markup=self.get_game_keyboard(game_type)
        )
    
    def format_game_result(self, game_type: str, result: Dict, bet: int, win: int) -> str:
        if game_type == "slot":
            matrix = result["matrix"]
            result_str = "🎰 **Слоты**\n\n"
            for row in matrix:
                result_str += " | ".join(row) + "\n"
        elif game_type == "dice":
            result_str = f"🎲 **Кости**\n\nРезультат: **{result['result']}**\nМножитель: **x{result['multiplier']}**\n"
        elif game_type == "roulette":
            result_str = f"🎡 **Рулетка**\n\nВыпало: **{result['number']}** {result['color']}\n"
        elif game_type == "blackjack":
            player_score = BlackjackGame().calculate_hand_score(result["player_hand"])
            dealer_score = BlackjackGame().calculate_hand_score(result["dealer_hand"])
            result_str = (
                f"🃏 **Блэкджек**\n\n"
                f"Ваши карты: {self.format_hand(result['player_hand'])} (очков: {player_score})\n"
                f"Карты дилера: {self.format_hand(result['dealer_hand'])} (очков: {dealer_score})\n"
            )
        elif game_type == "plinko":
            result_str = f"📌 **Plinko**\n\nПозиция: **{result['final_position']}**\nМножитель: **x{result['multiplier']:.2f}**\nРиск: **{result['risk']}**\n"
        elif game_type == "mines":
            result_str = f"💣 **Mines**\n\nМин: **{result['mines_count']}**\n"
        else:
            result_str = f"Результат игры\n"
        
        result_str += f"\nСтавка: **{bet} ⭐**\n"
        if win > 0:
            result_str += f"✅ Выигрыш: **{win} ⭐**"
        else:
            result_str += f"❌ Проигрыш"
        
        if "hash" in result:
            result_str += f"\n\n🔐 Provably Fair: `{result['hash'][:16]}...`"
        
        return result_str
    
    def format_hand(self, hand: List) -> str:
        return " ".join([f"{rank}{suit}" for rank, suit in hand])
    
    async def admin_panel(self, callback: CallbackQuery):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            return
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            users_count = (await cursor.fetchone())[0]
        
        jackpot = await Database.get_jackpot()
        
        admin_text = (
            f"👑 **Админ панель**\n\n"
            f"📊 **Общая статистика:**\n"
            f"Пользователей: **{users_count}**\n"
            f"Текущий джекпот: **{jackpot} ⭐**\n\n"
            f"Выберите действие:"
        )
        
        await callback.message.edit_text(admin_text, reply_markup=self.get_admin_keyboard())
    
    async def show_tournaments(self, callback: CallbackQuery):
        await callback.message.edit_text(
            "🏆 **Турниры**\n\nФункция в разработке",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
        )
    
    async def show_bonuses(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT value FROM settings WHERE key = "faucet_amount"')
            faucet_amount = int((await cursor.fetchone())[0])
        
        text = (
            "🎁 **Бонусы и награды**\n\n"
            f"💧 **Кран**\n"
            f"Сумма: **{faucet_amount} ⭐**\n\n"
            f"🎫 **Бонус коды**\n"
            f"Введите код для активации"
        )
        
        buttons = [
            [InlineKeyboardButton(text="💧 Забрать с крана", callback_data="claim_faucet")],
            [InlineKeyboardButton(text="🎫 Активировать код", callback_data="activate_bonus")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
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
                    await callback.answer(f"❌ Подождите {int(time_left // 60)} мин", show_alert=True)
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
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
            referrals_count = (await cursor.fetchone())[0]
        
        text = (
            f"👥 **Реферальная программа**\n\n"
            f"Ваша реферальная ссылка:\n"
            f"`https://t.me/{(await bot.me()).username}?start={user['referral_code']}`\n\n"
            f"Приглашено друзей: **{referrals_count or 0}**\n"
            f"За каждого друга вы получаете **50 ⭐** бонуса!"
        )
        
        buttons = [
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_stats(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        
        top_players = await Database.get_top_players(5)
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('''
                SELECT COUNT(*), SUM(profit) FROM games WHERE user_id = ?
            ''', (user_id,))
            games_count, total_profit = await cursor.fetchone()
        
        stats_text = "📊 **Статистика**\n\n"
        
        stats_text += f"**Ваша статистика:**\n"
        stats_text += f"Всего игр: {games_count or 0}\n"
        stats_text += f"Общий профит: {total_profit or 0} ⭐\n\n"
        
        stats_text += "**Топ-5 игроков:**\n"
        for i, player in enumerate(top_players, 1):
            stats_text += f"{i}. {player['username'] or f'ID{player['user_id']}'}: {player['total_wins']} побед\n"
        
        buttons = [
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await callback.message.edit_text(stats_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    async def show_settings(self, callback: CallbackQuery):
        user_id = callback.from_user.id
        user = await Database.get_user(user_id)
        
        text = (
            f"⚙️ **Настройки**\n\n"
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
    
    async def callback_handler(self, callback: CallbackQuery, state: FSMContext):
        data = callback.data
        
        if data == "main_menu":
            await callback.message.edit_text(
                "🎰 **Главное меню**\n\nВыберите игру:",
                reply_markup=self.get_main_keyboard(callback.from_user.id)
            )
        elif data == "balance":
            await self.cmd_balance(callback.message)
        elif data == "deposit":
            await callback.message.edit_text(
                "💳 **Пополнение баланса**\n\nФункция в разработке",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
            )
        elif data.startswith("game_"):
            game_type = data.replace("game_", "")
            if game_type in self.games:
                await callback.message.edit_text(
                    f"Выберите ставку:",
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
                f"Введите сумму ставки (от {MIN_BET} до {MAX_BET}):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"game_{game_type}")]
                ])
            )
        elif data.startswith("roulette_"):
            bet_type = data.replace("roulette_", "")
            await state.set_state(BetStates.waiting_for_bet)
            await state.update_data(game_type="roulette", bet_type=bet_type)
            await callback.message.edit_text(
                f"Введите сумму ставки для {bet_type}:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                ])
            )
        elif data.startswith("plinko_"):
            risk = data.replace("plinko_", "")
            await state.set_state(BetStates.waiting_for_bet)
            await state.update_data(game_type="plinko", risk=risk)
            await callback.message.edit_text(
                f"Введите сумму ставки для Plinko ({risk} риск):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]
                ])
            )
        elif data.startswith("mines_"):
            if data == "mines_bet":
                await state.set_state(BetStates.waiting_for_bet)
                await state.update_data(game_type="mines")
                await callback.message.edit_text(
                    f"Введите сумму ставки для Mines:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                    ])
                )
            else:
                try:
                    mines_count = int(data.replace("mines_", ""))
                    await state.set_state(BetStates.waiting_for_bet)
                    await state.update_data(game_type="mines", mines_count=mines_count)
                    await callback.message.edit_text(
                        f"Введите сумму ставки для Mines ({mines_count} мин):",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                        ])
                    )
                except ValueError:
                    await callback.answer("❌ Неверный формат", show_alert=True)
        elif data == "tournaments":
            await self.show_tournaments(callback)
        elif data == "bonuses":
            await self.show_bonuses(callback)
        elif data == "claim_faucet":
            await self.claim_faucet(callback)
        elif data == "activate_bonus":
            await state.set_state(BetStates.waiting_for_bonus_code)
            await callback.message.edit_text(
                "Введите бонус код:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="bonuses")]
                ])
            )
        elif data == "referrals":
            await self.show_referrals(callback)
        elif data == "stats":
            await self.show_stats(callback)
        elif data == "settings":
            await self.show_settings(callback)
        elif data == "admin_panel":
            await self.admin_panel(callback)
        elif data == "admin_stats":
            if callback.from_user.id not in ADMIN_IDS:
                return
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT COUNT(*) FROM users')
                users_count = (await cursor.fetchone())[0]
                cursor = await db.execute('SELECT SUM(profit) FROM games')
                total_profit = (await cursor.fetchone())[0] or 0
            jackpot = await Database.get_jackpot()
            await callback.message.edit_text(
                f"📊 **Статистика бота**\n\n"
                f"Пользователей: **{users_count}**\n"
                f"Общий профит: **{total_profit} ⭐**\n"
                f"Джекпот: **{jackpot} ⭐**",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
                ])
            )
        elif data == "admin_rtp":
            if callback.from_user.id not in ADMIN_IDS:
                return
            text = "🎮 **Управление RTP**\n\n"
            buttons = []
            for game_type in self.games.keys():
                game_names = {
                    "slot": "🎰 Слоты", "dice": "🎲 Кости", "roulette": "🎡 Рулетка",
                    "blackjack": "🃏 Блэкджек", "plinko": "📌 Plinko", "mines": "💣 Mines"
                }
                buttons.append([InlineKeyboardButton(
                    text=f"Изменить {game_names[game_type]}",
                    callback_data=f"admin_rtp_{game_type}"
                )])
            buttons.append([InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        elif data.startswith("admin_rtp_"):
            if callback.from_user.id not in ADMIN_IDS:
                return
            game_type = data.replace("admin_rtp_", "")
            await state.set_state(BetStates.waiting_for_rtp_change)
            await state.update_data(game_type=game_type)
            await callback.message.edit_text(
                f"Введите новое значение RTP для {game_type} (70-85%):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_rtp")]
                ])
            )
        
        await callback.answer()

# ============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================
@dp.message(CommandStart())
async def start_command(message: Message):
    await casino_bot.cmd_start(message)

@dp.message(Command("balance"))
async def balance_command(message: Message):
    await casino_bot.cmd_balance(message)

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    await casino_bot.callback_handler(callback, state)

@dp.message(BetStates.waiting_for_bet)
async def handle_custom_bet(message: Message, state: FSMContext):
    try:
        bet = int(message.text)
        if bet < MIN_BET or bet > MAX_BET:
            await message.answer(f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET}")
            return
        
        data = await state.get_data()
        game_type = data.get('game_type')
        bet_type = data.get('bet_type')
        risk = data.get('risk')
        mines_count = data.get('mines_count')
        await state.clear()
        
        user = await Database.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не найден. Напишите /start")
            return
        
        if user['balance'] < bet:
            await message.answer("❌ Недостаточно средств")
            return
        
        kwargs = {}
        if bet_type:
            kwargs["bet_type"] = bet_type
        if risk:
            kwargs["risk"] = risk
        if mines_count:
            kwargs["mines_count"] = mines_count
        
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
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(BetStates.waiting_for_bonus_code)
async def handle_bonus_code(message: Message, state: FSMContext):
    code = message.text.upper()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            SELECT * FROM bonus_codes 
            WHERE code = ? AND used_count < max_uses 
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        ''', (code,))
        bonus = await cursor.fetchone()
        
        if not bonus:
            await message.answer("❌ Недействительный бонус код")
            await state.clear()
            return
        
        cursor = await db.execute('''
            SELECT * FROM bonus_uses WHERE code = ? AND user_id = ?
        ''', (code, message.from_user.id))
        if await cursor.fetchone():
            await message.answer("❌ Вы уже использовали этот код")
            await state.clear()
            return
        
        amount = bonus[1]
        await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, message.from_user.id))
        await db.execute('UPDATE bonus_codes SET used_count = used_count + 1 WHERE code = ?', (code,))
        await db.execute('INSERT INTO bonus_uses (code, user_id) VALUES (?, ?)', (code, message.from_user.id))
        
        await db.commit()
    
    await state.clear()
    await message.answer(f"✅ Бонус активирован! Получено {amount} ⭐")

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

# ============================================
# HTTP-СЕРВЕР ДЛЯ RENDER
# ============================================
async def run_http_server():
    app = web.Application()
    
    async def handle(request):
        return web.Response(text="Bot is running!")

    app.router.add_get('/', handle)
    app.router.add_get('/health', handle)
    
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
    await init_db()
    asyncio.create_task(run_http_server())
    logger.info("🚀 Бот запускается...")
    await dp.start_polling(bot)

# Создаем экземпляр бота
casino_bot = CasinoBot()

if __name__ == "__main__":
    asyncio.run(main())
