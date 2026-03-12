import aiosqlite
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
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
                    min_rtp REAL DEFAULT 0.0,
                    max_rtp REAL DEFAULT 200.0,
                    volatility REAL DEFAULT 0.15,
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
            # Таблица настроек казино
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
            # Таблица настроек игр
            await db.execute('''
                CREATE TABLE IF NOT EXISTS game_settings (
                    game_type TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL
                )
            ''')
            # Таблица магазина бонусов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bonus_shop (
                    game_type TEXT PRIMARY KEY,
                    price INTEGER DEFAULT 100,
                    enabled INTEGER DEFAULT 1
                )
            ''')
            # Таблица для временных данных бонусных игр
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
            # Таблица для вейджера
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
            # Таблица для сессий блэкджека
            await db.execute('''
                CREATE TABLE IF NOT EXISTS blackjack_sessions (
                    user_id INTEGER PRIMARY KEY,
                    game_data TEXT,
                    bet INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.commit()
        logger.info("База данных инициализирована")

    # ----- Пользователи -----
    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users WHERE username = ?', (username.replace('@', ''),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, user_id: int, username: str = None, first_name: str = None,
                          last_name: str = None, referred_by: int = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            exists = await cursor.fetchone()
            cursor = await db.execute('SELECT value FROM settings WHERE key = "welcome_bonus"')
            welcome_bonus = int((await cursor.fetchone())[0])
            cursor = await db.execute('SELECT value FROM settings WHERE key = "referral_bonus"')
            referral_bonus = int((await cursor.fetchone())[0])
            if exists:
                await db.execute('''
                    UPDATE users SET username=?, first_name=?, last_name=?, last_active=CURRENT_TIMESTAMP
                    WHERE user_id=?
                ''', (username, first_name, last_name, user_id))
                logger.info(f"Пользователь {user_id} обновлён")
                bonus = 0
            else:
                referral_code = self._generate_referral_code()
                await db.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, referral_code, referred_by, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, referral_code, referred_by, welcome_bonus))
                logger.info(f"Новый пользователь {user_id} создан с балансом {welcome_bonus}")
                bonus = welcome_bonus
                if referred_by:
                    await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (referral_bonus, referred_by))
                    await db.execute('''
                        INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (str(uuid.uuid4()), referred_by, referral_bonus, 'referral', 'completed',
                          f'Реферальный бонус за пользователя {user_id}'))
            await db.commit()
            return bonus

    def _generate_referral_code(self, length: int = 8) -> str:
        import secrets, string
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))

    async def update_balance(self, user_id: int, amount: int, description: str = "") -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if not row:
                return False
            new_balance = row[0] + amount
            if new_balance < 0:
                return False
            await db.execute('UPDATE users SET balance = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (new_balance, user_id))
            if description:
                tx_type = 'admin' if amount > 0 else 'admin_withdraw'
                await db.execute('''
                    INSERT INTO transactions (transaction_id, user_id, amount, type, status, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (str(uuid.uuid4()), user_id, amount, tx_type, 'completed', description))
            await db.commit()
            logger.info(f"Баланс {user_id} изменён на {amount} (новый: {new_balance})")
            return True

    async def add_game_history(self, user_id: int, game_type: str, bet_amount: int,
                               win_amount: int, game_data: Dict):
        async with aiosqlite.connect(self.db_path) as db:
            game_id = str(uuid.uuid4())
            profit = win_amount - bet_amount
            await db.execute('''
                INSERT INTO games (game_id, user_id, game_type, bet_amount, win_amount, profit, game_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (game_id, user_id, game_type, bet_amount, win_amount, profit, json.dumps(game_data)))
            await db.execute('''
                UPDATE users SET total_bets = total_bets + 1,
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
            await self.update_tournament_scores(user_id, game_type, bet_amount, win_amount)

    async def get_user_game_stats(self, user_id: int, game_type: str) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*), SUM(win_amount) FROM games WHERE user_id = ? AND game_type = ?
            ''', (user_id, game_type))
            row = await cursor.fetchone()
            return {'total_bets': row[0] or 0, 'total_wins': row[1] or 0}

    # ----- RTP настройки -----
    async def get_rtp_settings(self, game_type: str = None) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if game_type:
                cursor = await db.execute('SELECT * FROM rtp_settings WHERE game_type = ?', (game_type,))
                row = await cursor.fetchone()
                return dict(row) if row else {'game_type': game_type, 'current_rtp': 76.82}
            else:
                cursor = await db.execute('SELECT * FROM rtp_settings')
                rows = await cursor.fetchall()
                return {row['game_type']: dict(row) for row in rows}

    async def update_rtp_settings(self, game_type: str, new_rtp: float, admin_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO rtp_settings (game_type, base_rtp, current_rtp, modified_by, last_modified)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (game_type, 76.82, new_rtp, admin_id))
            await db.commit()
            logger.info(f"RTP для {game_type} изменён на {new_rtp}% админом {admin_id}")

    # ----- Джекпот -----
    async def update_jackpot(self, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE jackpot SET amount = amount + ? WHERE id = 1', (amount,))
            await db.commit()

    async def get_jackpot(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT amount FROM jackpot WHERE id = 1')
            row = await cursor.fetchone()
            return row[0] if row else 1000

    async def reset_jackpot(self, winner_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE jackpot SET amount = 1000, last_win = CURRENT_TIMESTAMP, last_winner = ?
                WHERE id = 1
            ''', (winner_id,))
            await db.commit()
            logger.info(f"Джекпот сброшен победителем {winner_id}")

    # ----- Админка -----
    async def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT user_id, username, balance, total_bets, total_wins, vip_level, join_date, is_banned
                FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?
            ''', (limit, offset))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_users_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            row = await cursor.fetchone()
            return row[0]

    async def get_top_players(self, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT user_id, username, balance, total_wins, total_bets,
                       CAST(total_wins AS FLOAT) / total_bets * 100 as win_rate
                FROM users WHERE total_bets > 0 ORDER BY total_wins DESC LIMIT ?
            ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ----- Транзакции -----
    async def add_transaction(self, user_id: int, amount: int, tx_type: str,
                              status: str, description: str, wallet_address: str = None) -> str:
        tx_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO transactions (transaction_id, user_id, amount, type, status, description, wallet_address)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (tx_id, user_id, amount, tx_type, status, description, wallet_address))
            await db.commit()
        return tx_id

    async def update_transaction_status(self, transaction_id: str, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE transactions SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE transaction_id = ?
            ''', (status, transaction_id))
            await db.commit()

    async def get_transactions(self, user_id: int = None, limit: int = 20) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if user_id:
                cursor = await db.execute('''
                    SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
                ''', (user_id, limit))
            else:
                cursor = await db.execute('''
                    SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?
                ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ----- Бонус коды -----
    async def create_bonus_code(self, code: str, amount: int, max_uses: int,
                                 expires_at: datetime, created_by: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO bonus_codes (code, amount, max_uses, expires_at, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, amount, max_uses, expires_at, created_by))
            await db.commit()
            logger.info(f"Бонус код {code} создан админом {created_by}")

    async def get_bonus_codes(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM bonus_codes ORDER BY created_at DESC')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def use_bonus_code(self, code: str, user_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM bonus_codes WHERE code = ? AND used_count < max_uses
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ''', (code,))
            row = await cursor.fetchone()
            if not row:
                return None
            cursor = await db.execute('SELECT * FROM bonus_uses WHERE code = ? AND user_id = ?', (code, user_id))
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

    # ----- Турниры -----
    async def create_tournament(self, name: str, prize_pool: int, game_type: str,
                                 duration_hours: int, min_bet: int, created_by: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            start = datetime.now()
            end = start + timedelta(hours=duration_hours)
            cursor = await db.execute('''
                INSERT INTO tournaments (name, prize_pool, start_date, end_date, game_type, min_bet, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                RETURNING tournament_id
            ''', (name, prize_pool, start, end, game_type, min_bet, created_by))
            row = await cursor.fetchone()
            tid = row[0] if row else None
            await db.commit()
            logger.info(f"Турнир {name} создан админом {created_by}")
            return tid

    async def get_active_tournaments(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            now = datetime.now()
            cursor = await db.execute('''
                SELECT * FROM tournaments WHERE status = 'active' AND end_date > ? ORDER BY prize_pool DESC
            ''', (now,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_tournaments(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM tournaments ORDER BY created_at DESC')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_tournament_scores(self, user_id: int, game_type: str, bet: int, win: int):
        # Заглушка, будет реализовано при необходимости
        pass

    async def get_tournament_leaderboard(self, tournament_id: int, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT tp.user_id, u.username, tp.score
                FROM tournament_participants tp
                JOIN users u ON tp.user_id = u.user_id
                WHERE tp.tournament_id = ?
                ORDER BY tp.score DESC LIMIT ?
            ''', (tournament_id, limit))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def end_tournament(self, tournament_id: int):
        # Заглушка
        pass

    async def check_expired_tournaments(self):
        # Заглушка
        pass

    # ----- Ежедневные награды -----
    async def get_daily_reward(self, user_id: int) -> Tuple[bool, int, int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT last_claim, streak FROM daily_rewards WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            now = datetime.now()
            if row:
                last_claim = datetime.fromisoformat(row[0])
                streak = row[1]
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
                ON CONFLICT(user_id) DO UPDATE SET last_claim = ?, streak = ?
            ''', (user_id, now, streak, now, streak))
            await db.commit()
            return True, streak, bonus

    # ----- Настройки казино -----
    async def get_setting(self, key: str) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = await cursor.fetchone()
            return row[0] if row else ''

    async def update_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            await db.commit()

    # ----- Настройки игр -----
    async def get_game_settings(self, game_type: str) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT settings_json FROM game_settings WHERE game_type = ?', (game_type,))
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else {}

    async def update_game_settings(self, game_type: str, settings: Dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO game_settings (game_type, settings_json) VALUES (?, ?)
            ''', (game_type, json.dumps(settings)))
            await db.commit()

    # ----- Магазин бонусов -----
    async def get_bonus_price(self, game_type: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT price FROM bonus_shop WHERE game_type = ?', (game_type,))
            row = await cursor.fetchone()
            return row[0] if row else 100

    async def set_bonus_price(self, game_type: str, price: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bonus_shop (game_type, price, enabled) VALUES (?, ?, 1)
            ''', (game_type, price))
            await db.commit()

    # ----- Временные данные бонусных игр -----
    async def get_bonus_wild(self, user_id: int, game_type: str) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM bonus_wilds WHERE user_id = ? AND game_type = ?',
                                      (user_id, game_type))
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {'multiplier': 1.0, 'spins_left': 0, 'total_win': 0, 'sticky_positions': '[]'}

    async def update_bonus_wild(self, user_id: int, game_type: str, multiplier: float,
                                 spins_left: int, total_win: int, sticky_positions: List = None):
        sticky_json = json.dumps(sticky_positions) if sticky_positions else '[]'
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bonus_wilds (user_id, game_type, multiplier, spins_left, total_win, sticky_positions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, game_type, multiplier, spins_left, total_win, sticky_json))
            await db.commit()

    async def clear_bonus_wild(self, user_id: int, game_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM bonus_wilds WHERE user_id = ? AND game_type = ?', (user_id, game_type))
            await db.commit()

    # ----- Вейджер -----
    async def add_wager_requirement(self, user_id: int, amount: int, eligible_games: str) -> str:
        wager_mult = int(await self.get_setting('wager_multiplier') or 35)
        total = amount * wager_mult
        wager_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO wager_requirements (wager_id, user_id, bonus_amount, total_to_wager, eligible_games)
                VALUES (?, ?, ?, ?, ?)
            ''', (wager_id, user_id, amount, total, eligible_games))
            await db.commit()
        return wager_id

    async def get_active_wager(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM wager_requirements WHERE user_id = ? AND status = 'active' ORDER BY created_at LIMIT 1
            ''', (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_wager_progress(self, wager_id: str, bet_amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE wager_requirements SET wagered_amount = wagered_amount + ? WHERE wager_id = ? AND status = 'active'
            ''', (bet_amount, wager_id))
            cursor = await db.execute('SELECT wagered_amount, total_to_wager, user_id, bonus_amount FROM wager_requirements WHERE wager_id = ?', (wager_id,))
            row = await cursor.fetchone()
            if row and row[0] >= row[1]:
                await db.execute("UPDATE wager_requirements SET status = 'completed', completed_at = ? WHERE wager_id = ?",
                                 (datetime.now(), wager_id))
                await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (row[3], row[2]))
            await db.commit()

    # ----- Сессии блэкджека -----
    async def save_blackjack_session(self, user_id: int, game_data: Dict, bet: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO blackjack_sessions (user_id, game_data, bet, created_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, json.dumps(game_data), bet, datetime.now()))
            await db.commit()

    async def get_blackjack_session(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM blackjack_sessions WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if row:
                return {'game_data': json.loads(row['game_data']), 'bet': row['bet']}
            return None

    async def delete_blackjack_session(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM blackjack_sessions WHERE user_id = ?', (user_id,))
            await db.commit()
