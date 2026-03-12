import asyncio
import logging
import uuid
import json
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BufferedInputFile
)
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web

from config import BOT_TOKEN, ADMIN_IDS, DATABASE_PATH, MIN_BET, MAX_BET, JACKPOT_PERCENT
from database import Database
from rtp import RTPManager
from games import (
    DiceGame, RouletteGame, MinesGame, PlinkoGame, KenoGame,
    DogHouseGame, SugarRushGame, BlackjackGame
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database(DATABASE_PATH)

# ---------- FSM состояния ----------
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
    waiting_for_wager_multiplier = State()
    waiting_for_bonus_type = State()
    waiting_for_bonus_wager = State()
    waiting_for_tilt_game = State()
    waiting_for_tilt_factor = State()
    waiting_for_tilt_hours = State()
    waiting_for_slot_weight = State()
    waiting_for_slot_value = State()

# ---------- Основной класс бота ----------
class CasinoBot:
    def __init__(self, db):
        self.db = db
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
        for game in self.games.values():
            game.db = db
        self.active_games = {}          # для Mines
        self.bonus_sessions = {}         # для временных данных бонусных игр

    # ---------- Клавиатуры ----------
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
            [InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
             InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton(text="🏆 Турниры", callback_data="tournaments"),
             InlineKeyboardButton(text="🎁 Бонусы", callback_data="bonuses")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
             InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
            [InlineKeyboardButton(text="📜 История", callback_data="history")]
        ]
        if user_id in ADMIN_IDS:
            buttons.append([InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def get_game_keyboard(self, game_type: str, game_state: dict = None, lang: str = 'ru') -> InlineKeyboardMarkup:
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
                mine_positions = game_state.get("mine_positions", [])
                gold_positions = game_state.get("gold_positions", [])
                for i in range(5):
                    row = []
                    for j in range(5):
                        cell = i*5 + j
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
            if game_state and game_state.get("bonus_active"):
                buttons = [
                    [InlineKeyboardButton(text=f"🎰 Крутить (осталось {game_state['spins_left']})",
                                         callback_data=f"bonus_spin_{game_type}")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ]
            else:
                buttons = [
                    [InlineKeyboardButton(text="10 ⭐", callback_data=f"play_{game_type}_10"),
                     InlineKeyboardButton(text="50 ⭐", callback_data=f"play_{game_type}_50")],
                    [InlineKeyboardButton(text="100 ⭐", callback_data=f"play_{game_type}_100"),
                     InlineKeyboardButton(text="500 ⭐", callback_data=f"play_{game_type}_500")],
                    [InlineKeyboardButton(text="💰 Своя ставка", callback_data=f"custom_bet_{game_type}"),
                     InlineKeyboardButton(text="🎁 Купить бонус", callback_data=f"buy_bonus_{game_type}")]
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
             InlineKeyboardButton(text="⚙️ Открутка/подкрутка", callback_data="admin_tilt_menu")],
            [InlineKeyboardButton(text="🎁 Бонус коды", callback_data="admin_bonus_menu"),
             InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="admin_withdrawals")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
             InlineKeyboardButton(text="⚙️ Настройки казино", callback_data="admin_settings")],
            [InlineKeyboardButton(text="📥 Скачать БД", callback_data="admin_download_db"),
             InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    # ---------- Вспомогательные методы ----------
    def format_hand(self, hand):
        return " ".join([f"{r}{s}" for r,s in hand])

    async def check_balance_and_deduct(self, user_id: int, bet: int) -> bool:
        user = await self.db.get_user(user_id)
        if not user:
            return False
        total = user['balance'] + user.get('bonus_balance', 0)
        if total < bet:
            return False
        from_bonus = min(bet, user.get('bonus_balance', 0))
        from_real = bet - from_bonus
        await self.db.update_balance(user_id, -from_real, "Ставка")
        if from_bonus > 0:
            async with aiosqlite.connect(self.db.db_path) as conn:
                await conn.execute('UPDATE users SET bonus_balance = bonus_balance - ? WHERE user_id = ?',
                                   (from_bonus, user_id))
                await conn.commit()
        return True

    # ---------- Команды ----------
    async def cmd_start(self, message: types.Message):
        user_id = message.from_user.id
        await self.db.create_user(user_id, message.from_user.username,
                                  message.from_user.first_name, message.from_user.last_name)
        user = await self.db.get_user(user_id)
        lang = user.get('language', 'ru')
        text = f"Добро пожаловать! Ваш баланс: {user['balance']} ⭐"
        if user.get('bonus_balance', 0) > 0:
            text += f"\n🎁 Бонусный баланс: {user['bonus_balance']} ⭐"
        await message.answer(text, reply_markup=self.get_main_keyboard(lang, user_id))

    async def cmd_balance(self, message: types.Message):
        user = await self.db.get_user(message.from_user.id)
        if not user:
            await message.answer("Пользователь не найден")
            return
        lang = user.get('language', 'ru')
        text = f"💰 Баланс: {user['balance']} ⭐\n🎁 Бонусный: {user['bonus_balance']} ⭐"
        wager = await self.db.get_active_wager(message.from_user.id)
        if wager:
            text += f"\n🎯 Отыгрыш: {wager['wagered_amount']}/{wager['total_to_wager']}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
             InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(text, reply_markup=kb)
    # ---------- ОСНОВНОЙ ОБРАБОТЧИК CALLBACK ----------
    async def callback_handler(self, callback: types.CallbackQuery, state: FSMContext):
        data = callback.data
        user_id = callback.from_user.id

        user = await self.db.get_user(user_id)
        if not user and data not in ("main_menu", "balance", "deposit", "withdraw"):
            await callback.answer("Пользователь не найден. Напишите /start")
            return
        lang = user.get('language', 'ru') if user else 'ru'

        # --- Главное меню ---
        if data == "main_menu":
            await callback.message.edit_text("Главное меню", reply_markup=self.get_main_keyboard(lang, user_id))

        # --- Баланс ---
        elif data == "balance":
            await self.cmd_balance(callback.message)

        # --- Пополнение ---
        elif data == "deposit":
            await state.set_state(BetStates.waiting_for_deposit_amount)
            await callback.message.edit_text(
                "💳 Введите сумму пополнения в ⭐ (от 10 до 10000):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="balance")]
                ])
            )

        # --- Вывод ---
        elif data == "withdraw":
            min_wd = int(await self.db.get_setting('min_withdrawal'))
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

        # --- Настройки ---
        elif data == "settings":
            await self.show_settings(callback, lang)

        elif data == "change_language":
            new_lang = 'en' if user['language'] == 'ru' else 'ru'
            async with aiosqlite.connect(self.db.db_path) as conn:
                await conn.execute('UPDATE users SET language = ? WHERE user_id = ?', (new_lang, user_id))
                await conn.commit()
            await callback.answer(f"Язык изменён на {'English' if new_lang=='en' else 'Русский'}", show_alert=True)
            await self.show_settings(callback, new_lang)

        elif data == "toggle_pf":
            new_val = 0 if user['pf_enabled'] else 1
            async with aiosqlite.connect(self.db.db_path) as conn:
                await conn.execute('UPDATE users SET pf_enabled = ? WHERE user_id = ?', (new_val, user_id))
                await conn.commit()
            await callback.answer(f"Provably Fair {'включён' if new_val else 'отключён'}", show_alert=True)
            await self.show_settings(callback, lang)

        elif data == "provably_fair_info":
            await callback.message.edit_text(
                "🔐 **Provably Fair**\n\nВсе игры используют криптографическую систему, позволяющую проверить честность каждого раунда. Хеш результата отображается в конце игры.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Назад", callback_data="settings")]
                ])
            )

        # --- Турниры (упрощённо) ---
        elif data == "tournaments":
            await self.show_tournaments(callback, lang)

        # --- Бонусы ---
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

        # --- Статистика и история ---
        elif data == "stats":
            await self.show_stats(callback, lang)

        elif data == "referrals":
            await self.show_referrals(callback, lang)

        elif data == "history":
            await self.show_history(callback, lang)

        # --- АДМИН ПАНЕЛЬ ---
        elif data == "admin_panel":
            if user_id not in ADMIN_IDS:
                await callback.answer("❌ Доступ запрещён", show_alert=True)
                return
            users_cnt = await self.db.get_users_count()
            jackpot = await self.db.get_jackpot()
            text = f"👑 **Админ панель**\n\nПользователей: {users_cnt}\nДжекпот: {jackpot} ⭐"
            await callback.message.edit_text(text, reply_markup=self.get_admin_keyboard())

        elif data == "admin_stats":
            if user_id not in ADMIN_IDS:
                return
            async with aiosqlite.connect(self.db.db_path) as conn:
                cursor = await conn.execute('SELECT COUNT(*) FROM users')
                users_cnt = (await cursor.fetchone())[0]
                cursor = await conn.execute('SELECT COUNT(*), SUM(bet_amount), SUM(profit) FROM games')
                row = await cursor.fetchone()
                games_cnt = row[0] or 0
                total_bets = row[1] or 0
                total_profit = row[2] or 0
            jack = await self.db.get_jackpot()
            text = f"📊 **Статистика бота**\n\nПользователей: {users_cnt}\nИгр сыграно: {games_cnt}\nВсего ставок: {total_bets} ⭐\nПрофит казино: {total_profit} ⭐\nДжекпот: {jack} ⭐"
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ]))

        # --- Управление пользователями (админ) ---
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
            users = await self.db.get_all_users(limit=10, offset=0)
            total = await self.db.get_users_count()
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
            users = await self.db.get_all_users(limit=10, offset=page*10)
            total = await self.db.get_users_count()
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
            await callback.message.edit_text("🔍 Введите ID пользователя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]
            ]))

        elif data == "admin_user_search_username":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="search_username")
            await callback.message.edit_text("🔍 Введите username (без @):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]
            ]))

        elif data == "admin_balance":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_user_id)
            await state.update_data(admin_action="balance_change")
            await callback.message.edit_text("💰 Введите ID пользователя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
            ]))

        # --- Настройки RTP (админ) ---
        elif data == "admin_rtp":
            if user_id not in ADMIN_IDS:
                return
            settings = await self.db.get_rtp_settings()
            text = "🎮 **Настройки RTP**\n\n"
            btns = []
            for g in self.games:
                cur = settings.get(g, {}).get('current_rtp', 76.82)
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
            await callback.message.edit_text(f"🎮 Введите новое RTP для {game} (0-200%):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_rtp")]
            ]))

        # --- Редактор слотов (с кнопками) ---
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

        # --- Открутка/подкрутка (tilt) ---
        elif data == "admin_tilt_menu":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎲 Кости", callback_data="admin_tilt_dice"),
                 InlineKeyboardButton(text="🎡 Рулетка", callback_data="admin_tilt_roulette")],
                [InlineKeyboardButton(text="💣 Mines", callback_data="admin_tilt_mines"),
                 InlineKeyboardButton(text="📌 Plinko", callback_data="admin_tilt_plinko")],
                [InlineKeyboardButton(text="🎯 Кено", callback_data="admin_tilt_keno"),
                 InlineKeyboardButton(text="🐶 Dog House", callback_data="admin_tilt_doghouse")],
                [InlineKeyboardButton(text="🍬 Sugar Rush", callback_data="admin_tilt_sugarrush"),
                 InlineKeyboardButton(text="🃏 Блэкджек", callback_data="admin_tilt_blackjack")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("⚙️ Выберите игру для настройки открутки/подкрутки:", reply_markup=kb)

        elif data.startswith("admin_tilt_"):
            if user_id not in ADMIN_IDS:
                return
            game = data.replace("admin_tilt_", "")
            await state.set_state(BetStates.waiting_for_tilt_factor)
            await state.update_data(tilt_game=game)
            await callback.message.edit_text(
                f"Введите множитель открутки (например, 1.2 для увеличения шансов, 0.8 для уменьшения):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_tilt_menu")]
                ])
            )

        # --- Бонус коды (админ) ---
        elif data == "admin_bonus_menu":
            if user_id not in ADMIN_IDS:
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать код", callback_data="admin_bonus_create")],
                [InlineKeyboardButton(text="📋 Список кодов", callback_data="admin_bonus_list")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_panel")]
            ])
            await callback.message.edit_text("🎁 Управление бонус кодами", reply_markup=kb)

        elif data == "admin_bonus_create":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_bonus_code)
            await state.update_data(admin_action="create_bonus")
            await callback.message.edit_text("Введите код (например, WELCOME100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_bonus_menu")]
            ]))

        elif data == "admin_bonus_list":
            if user_id not in ADMIN_IDS:
                return
            codes = await self.db.get_bonus_codes()
            text = "🎁 **Существующие бонус коды**\n\n"
            for c in codes:
                exp = c['expires_at'] if c['expires_at'] else "никогда"
                text += f"`{c['code']}`: {c['amount']}⭐ ({c['type']}), вейджер {c['wager_multiplier']}, использовано {c['used_count']}/{c['max_uses']}, истекает {exp}\n"
            if not codes:
                text = "Нет созданных кодов."
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_bonus_menu")]
            ]))

        # --- Заявки на вывод ---
        elif data == "admin_withdrawals":
            if user_id not in ADMIN_IDS:
                return
            txs = await self.db.get_transactions(limit=50)
            pending = [t for t in txs if t['type']=='withdrawal' and t['status']=='pending']
            text = "💸 **Заявки на вывод**\n\n"
            if not pending:
                text += "Нет заявок"
            else:
                for p in pending:
                    text += f"ID: `{p['transaction_id']}`\nПользователь: {p['user_id']}\nСумма: {p['amount']}⭐\nКошелёк: {p['wallet_address']}\n\n"
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
            await self.db.update_transaction_status(tx_id, 'completed')
            async with aiosqlite.connect(self.db.db_path) as conn:
                cursor = await conn.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                row = await cursor.fetchone()
                if row:
                    uid, amt = row
                    await bot.send_message(uid, f"✅ Ваш вывод на {amt} ⭐ подтверждён и отправлен.")
            await callback.answer("✅ Вывод подтверждён")
            await self.callback_handler(callback, state)

        elif data.startswith("reject_"):
            if user_id not in ADMIN_IDS:
                return
            tx_id = data.replace("reject_", "")
            await self.db.update_transaction_status(tx_id, 'rejected')
            async with aiosqlite.connect(self.db.db_path) as conn:
                cursor = await conn.execute('SELECT user_id, amount FROM transactions WHERE transaction_id = ?', (tx_id,))
                row = await cursor.fetchone()
                if row:
                    uid, amt = row
                    await conn.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, uid))
                    await conn.commit()
                    await bot.send_message(uid, f"❌ Ваш вывод на {amt} ⭐ отклонён. Средства возвращены.")
            await callback.answer("❌ Вывод отклонён")
            await self.callback_handler(callback, state)

        # --- Рассылка ---
        elif data == "admin_broadcast":
            if user_id not in ADMIN_IDS:
                return
            await state.set_state(BetStates.waiting_for_broadcast_message)
            await callback.message.edit_text("📢 Введите сообщение для рассылки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
            ]))

        # --- Настройки казино ---
        elif data == "admin_settings":
            if user_id not in ADMIN_IDS:
                return
            keys = ['min_withdrawal','withdrawal_fee','faucet_amount','faucet_cooldown']
            text = "⚙️ **Настройки казино**\n\n"
            btns = []
            for k in keys:
                val = await self.db.get_setting(k)
                text += f"{k}: {val}\n"
            btns = [
                [InlineKeyboardButton(text="Мин.вывод", callback_data="admin_setting_min_withdrawal"),
                 InlineKeyboardButton(text="Комиссия", callback_data="admin_setting_withdrawal_fee")],
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
                "faucet_amount": "Введите сумму крана:",
                "faucet_cooldown": "Введите перезарядку (минуты):"
            }
            await callback.message.edit_text(desc.get(setting, "Введите значение:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings")]
            ]))

        elif data == "admin_download_db":
            if user_id not in ADMIN_IDS:
                return
            await callback.message.answer_document(types.FSInputFile(self.db.db_path), caption="📦 Бэкап БД")

        # --- Игры: выбор игры ---
        elif data.startswith("game_"):
            game = data[5:]
            if game in self.games:
                await callback.message.edit_text(f"🎮 **{game.upper()}**", reply_markup=self.get_game_keyboard(game, lang=lang))
            else:
                await callback.answer("Игра не найдена")

        # --- Кости ---
        elif data == "dice_single":
            await state.update_data(game_type="dice", mode="single")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲 Введите сумму ставки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]
            ]))

        elif data == "dice_double":
            await state.update_data(game_type="dice", mode="double")
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text("🎲🎲 Введите сумму ставки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="game_dice")]
            ]))

        # --- Рулетка ---
        elif data.startswith("roulette_"):
            bt = data.replace("roulette_", "")
            if bt == "number":
                await state.update_data(game_type="roulette", bet_type="straight")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("🎯 Введите число и сумму через пробел (например 7 100):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                ]))
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
                await callback.message.edit_text(f"🎡 Введите сумму ставки на {bt}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                ]))
            elif bt in ["red","black","even","odd","low","high"]:
                await state.update_data(game_type="roulette", bet_type=bt)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎡 Введите сумму ставки на {bt}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_roulette")]
                ]))

        # --- Плинко ---
        elif data.startswith("plinko_"):
            risk = data.replace("plinko_", "")
            if risk in ["low","medium","high"]:
                await state.update_data(game_type="plinko", risk=risk)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"📌 Введите сумму (риск {risk}):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]
                ]))
            elif risk == "bet":
                await state.update_data(game_type="plinko", risk="medium")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("📌 Введите сумму (средний риск):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_plinko")]
                ]))

        # --- Мины ---
        elif data.startswith("mines_"):
            parts = data.split("_")
            if len(parts) == 3 and parts[1] in ["easy","medium","hard","extreme"]:
                difficulty = parts[1]
                mines = int(parts[2])
                await state.update_data(game_type="mines", mines=mines, difficulty=difficulty)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"💣 Введите сумму ({difficulty}, {mines} мин):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                ]))
            elif data == "mines_bet":
                await state.update_data(game_type="mines", mines=5, difficulty="medium")
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("💣 Введите сумму (5 мин, средний риск):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="game_mines")]
                ]))
            elif data == "mines_cashout":
                if user_id not in self.active_games or self.active_games[user_id]["game"] != "mines":
                    await callback.answer("Нет активной игры", show_alert=True)
                    return
                game_data = self.active_games[user_id]
                base_win = self.games["mines"].calculate_base_win(game_data["bet"], game_data["result"], game_data["revealed"])
                if base_win == 0:
                    await callback.answer("❌ Вы проиграли", show_alert=True)
                    del self.active_games[user_id]
                    await callback.message.edit_text("💥 Вы проиграли!", reply_markup=self.get_game_keyboard("mines", lang=lang))
                    return
                win = await self.games["mines"].finalize_win(base_win, game_data["bet"], user_id)
                await self.db.update_balance(user_id, win, "Выигрыш в Mines")
                await self.db.add_game_history(user_id, "mines", game_data["bet"], win, game_data["result"])
                await self.db.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
                del self.active_games[user_id]
                jackpot = await self.db.get_jackpot()
                await callback.message.edit_text(f"✅ Вы выиграли {win} ⭐!\n💰 Джекпот: {jackpot} ⭐",
                                                 reply_markup=self.get_game_keyboard("mines", lang=lang))
            elif data == "mines_new":
                if user_id in self.active_games:
                    del self.active_games[user_id]
                await callback.message.edit_text("💣 Mines", reply_markup=self.get_game_keyboard("mines", lang=lang))
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
                    await self.db.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
                    await self.db.add_game_history(user_id, "mines", game_data["bet"], 0, game_data["result"])
                    await callback.message.edit_text("💥 **БАБАХ!** Вы проиграли.",
                                                     reply_markup=self.get_game_keyboard("mines", lang=lang))
                else:
                    self.active_games[user_id] = game_data
                    cur_win = self.games["mines"].calculate_base_win(game_data["bet"], game_data["result"], game_data["revealed"])
                    await callback.message.edit_text(f"✅ Безопасно! Текущий выигрыш: {cur_win} ⭐",
                                                     reply_markup=self.get_game_keyboard("mines", game_data, lang=lang))

        # --- Кено ---
        elif data.startswith("keno_"):
            pk = data.replace("keno_pick", "")
            if pk.isdigit():
                picks = int(pk)
                await state.update_data(game_type="keno", picks=picks)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text(f"🎯 Введите {picks} чисел от 1 до 80 через пробел и сумму (пример: 5 12 33 100):",
                                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                     [InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]
                                                 ]))
            elif data == "keno_bet":
                await state.update_data(game_type="keno", picks=5)
                await state.set_state(BetStates.waiting_for_bet)
                await callback.message.edit_text("🎯 Введите 5 чисел и сумму (пример: 5 12 33 45 78 100):",
                                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                     [InlineKeyboardButton(text="❌ Отмена", callback_data="game_keno")]
                                                 ]))

        # --- Блэкджек ---
        elif data == "blackjack_new":
            if user_id in self.active_games and self.active_games[user_id].get("game") == "blackjack":
                del self.active_games[user_id]
            await callback.message.edit_text("🃏 Блэкджек", reply_markup=self.get_game_keyboard("blackjack", lang=lang))

        elif data == "blackjack_hit":
            if user_id not in self.active_games or self.active_games[user_id]["game"] != "blackjack":
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game_data = self.active_games[user_id]
            game = self.games["blackjack"]
            if not game_data["deck"]:
                await callback.answer("Колода пуста", show_alert=True)
                return
            new_card = game_data["deck"].pop(0)
            game_data["player_hand"].append(new_card)
            game_data["player_score"] = game._hand_score(game_data["player_hand"])
            if game_data["player_score"] > 21:
                await self.db.add_game_history(user_id, "blackjack", game_data["bet"], 0, {"final": "bust"})
                del self.active_games[user_id]
                await callback.message.edit_text(f"❌ **ПЕРЕБОР!**\nВаши карты: {self.format_hand(game_data['player_hand'])} ({game_data['player_score']})\nДилер: {self.format_hand(game_data['dealer_hand'])}",
                                                 reply_markup=self.get_game_keyboard("blackjack", lang=lang))
            else:
                self.active_games[user_id] = game_data
                await callback.message.edit_text(f"🃏 Ваши карты: {self.format_hand(game_data['player_hand'])} (очков: {game_data['player_score']})\nДилер: {self.format_hand(game_data['dealer_hand'][:1])} + ?",
                                                 reply_markup=self.get_game_keyboard("blackjack", {"active": True}, lang=lang))

        elif data == "blackjack_stand":
            if user_id not in self.active_games or self.active_games[user_id]["game"] != "blackjack":
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game_data = self.active_games[user_id]
            game = self.games["blackjack"]
            dealer_hand = game_data["dealer_hand"]
            deck = game_data["deck"]
            dealer_score = game._hand_score(dealer_hand)
            while dealer_score < 17 and deck:
                dealer_hand.append(deck.pop(0))
                dealer_score = game._hand_score(dealer_hand)
            win = game.calculate_base_win(game_data["bet"], game_data["player_hand"], dealer_hand)
            profit = win - game_data["bet"]
            if win > 0:
                await self.db.update_balance(user_id, profit, "Выигрыш в блэкджек")
            await self.db.add_game_history(user_id, "blackjack", game_data["bet"], win, {"player": game_data["player_hand"], "dealer": dealer_hand})
            del self.active_games[user_id]
            await self.db.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
            jackpot = await self.db.get_jackpot()
            await callback.message.edit_text(f"🃏 Результат:\nВаши: {self.format_hand(game_data['player_hand'])} ({game_data['player_score']})\nДилер: {self.format_hand(dealer_hand)} ({dealer_score})\n\n{'✅' if win>0 else '❌'} Выигрыш: {win} ⭐\n💰 Джекпот: {jackpot} ⭐",
                                             reply_markup=self.get_game_keyboard("blackjack", lang=lang))

        elif data == "blackjack_double":
            if user_id not in self.active_games or self.active_games[user_id]["game"] != "blackjack":
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game_data = self.active_games[user_id]
            game = self.games["blackjack"]
            user_cur = await self.db.get_user(user_id)
            if user_cur['balance'] + user_cur.get('bonus_balance',0) < game_data["bet"]:
                await callback.answer("❌ Недостаточно средств для удвоения", show_alert=True)
                return
            from_bonus = min(game_data["bet"], user_cur.get('bonus_balance',0))
            from_real = game_data["bet"] - from_bonus
            await self.db.update_balance(user_id, -from_real, "Удвоение ставки")
            if from_bonus > 0:
                async with aiosqlite.connect(self.db.db_path) as conn:
                    await conn.execute('UPDATE users SET bonus_balance = bonus_balance - ? WHERE user_id = ?',
                                       (from_bonus, user_id))
                    await conn.commit()
            game_data["bet"] *= 2
            new_card = game_data["deck"].pop(0)
            game_data["player_hand"].append(new_card)
            game_data["player_score"] = game._hand_score(game_data["player_hand"])
            if game_data["player_score"] > 21:
                await self.db.add_game_history(user_id, "blackjack", game_data["bet"], 0, {"final": "bust"})
                del self.active_games[user_id]
                await callback.message.edit_text(f"❌ **ПЕРЕБОР!**\nВаши карты: {self.format_hand(game_data['player_hand'])}",
                                                 reply_markup=self.get_game_keyboard("blackjack", lang=lang))
                return
            dealer_hand = game_data["dealer_hand"]
            deck = game_data["deck"]
            dealer_score = game._hand_score(dealer_hand)
            while dealer_score < 17 and deck:
                dealer_hand.append(deck.pop(0))
                dealer_score = game._hand_score(dealer_hand)
            win = game.calculate_base_win(game_data["bet"], game_data["player_hand"], dealer_hand)
            profit = win - game_data["bet"]
            if win > 0:
                await self.db.update_balance(user_id, profit, "Выигрыш в блэкджек")
            await self.db.add_game_history(user_id, "blackjack", game_data["bet"], win, {"player": game_data["player_hand"], "dealer": dealer_hand})
            del self.active_games[user_id]
            await self.db.update_jackpot(int(game_data["bet"] * JACKPOT_PERCENT))
            jackpot = await self.db.get_jackpot()
            await callback.message.edit_text(f"🃏 Результат (удвоение):\nВаши: {self.format_hand(game_data['player_hand'])} ({game_data['player_score']})\nДилер: {self.format_hand(dealer_hand)} ({dealer_score})\n\n{'✅' if win>0 else '❌'} Выигрыш: {win} ⭐\n💰 Джекпот: {jackpot} ⭐",
                                             reply_markup=self.get_game_keyboard("blackjack", lang=lang))

        elif data == "blackjack_insurance":
            if user_id not in self.active_games or self.active_games[user_id]["game"] != "blackjack":
                await callback.answer("Нет активной игры", show_alert=True)
                return
            game_data = self.active_games[user_id]
            user_cur = await self.db.get_user(user_id)
            insurance = game_data["bet"] // 2
            if user_cur['balance'] + user_cur.get('bonus_balance',0) < insurance:
                await callback.answer("❌ Недостаточно средств для страховки", show_alert=True)
                return
            from_bonus = min(insurance, user_cur.get('bonus_balance',0))
            from_real = insurance - from_bonus
            await self.db.update_balance(user_id, -from_real, "Страховка")
            if from_bonus > 0:
                async with aiosqlite.connect(self.db.db_path) as conn:
                    await conn.execute('UPDATE users SET bonus_balance = bonus_balance - ? WHERE user_id = ?',
                                       (from_bonus, user_id))
                    await conn.commit()
            dealer_hand = game_data["dealer_hand"]
            dealer_score = self.games["blackjack"]._hand_score(dealer_hand)
            if dealer_score == 21 and len(dealer_hand) == 2:
                win = insurance * 2
                await self.db.update_balance(user_id, win, "Выигрыш страховки")
                await callback.answer(f"✅ Страховка сработала! Выигрыш {win} ⭐", show_alert=True)
                del self.active_games[user_id]
                await callback.message.edit_text("🤝 У дилера блэкджек!", reply_markup=self.get_game_keyboard("blackjack", lang=lang))
            else:
                await callback.answer("❌ У дилера нет блэкджека, страховка проиграла", show_alert=True)

        # --- Слоты Dog House и Sugar Rush ---
        elif data.startswith("play_doghouse_"):
            await self.handle_slot_play(callback, state, "doghouse", int(data.split("_")[2]), lang)

        elif data.startswith("play_sugarrush_"):
            await self.handle_slot_play(callback, state, "sugarrush", int(data.split("_")[2]), lang)

        elif data.startswith("custom_bet_"):
            game = data.replace("custom_bet_", "")
            await state.update_data(game_type=game)
            await state.set_state(BetStates.waiting_for_bet)
            await callback.message.edit_text(f"💰 Введите сумму ставки (от {MIN_BET} до {MAX_BET}):",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                 [InlineKeyboardButton(text="❌ Отмена", callback_data=f"game_{game}")]
                                             ]))

        elif data.startswith("buy_bonus_"):
            game_type = data.replace("buy_bonus_", "")
            price = await self.db.get_bonus_price(game_type)
            user_cur = await self.db.get_user(user_id)
            if user_cur['balance'] < price:
                await callback.answer("❌ Недостаточно средств", show_alert=True)
                return
            await self.db.update_balance(user_id, -price, f"Покупка бонусной игры в {game_type}")
            if game_type == "doghouse":
                win = await self.games["doghouse"].play_bonus_game(user_id, 10)
            elif game_type == "sugarrush":
                win = await self.games["sugarrush"].play_bonus_game(user_id, 10)
            else:
                win = 0
            await self.db.update_balance(user_id, win, f"Выигрыш в бонусной игре {game_type}")
            await callback.message.edit_text(f"🎉 Бонусная игра завершена! Выигрыш: {win} ⭐",
                                             reply_markup=self.get_game_keyboard(game_type, lang=lang))

        # --- Обработка стандартных ставок (play_X_сумма) для игр, где нет особых параметров ---
        elif data.startswith("play_"):
            parts = data.split("_")
            if len(parts) < 3:
                await callback.answer("Неверный формат")
                return
            game = parts[1]
            try:
                bet = int(parts[2])
            except:
                await callback.answer("Неверная сумма")
                return
            await self.handle_slot_play(callback, state, game, bet, lang)

        else:
            await callback.answer("Неизвестная команда")

    # ---------- Универсальный метод для обработки игр ----------
    async def handle_slot_play(self, callback: types.CallbackQuery, state: FSMContext, game_type: str, bet: int, lang: str, **kwargs):
        user_id = callback.from_user.id
        game = self.games.get(game_type)
        if not game:
            await callback.answer("Игра не найдена")
            return
        await game.load_settings(self.db)

        # Проверка и списание ставки
        if not await self.check_balance_and_deduct(user_id, bet):
            await callback.answer("Недостаточно средств", show_alert=True)
            return

        # Генерация результата и выигрыша
        if game_type in ["doghouse", "sugarrush"]:
            result = game.generate_result(bet, user_id)
            base_win = game.calculate_base_win(bet, result)
            win = await game.finalize_win(base_win, bet, user_id)

            # Бонусная игра
            if result.get("bonus_triggered"):
                bonus_win = await game.play_bonus_game(user_id, bet)
                win += bonus_win
                await callback.message.answer(f"🎉 Бонусная игра! Дополнительный выигрыш: {bonus_win} ⭐")

            await self.db.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await self.db.add_game_history(user_id, game_type, bet, win, result)
            await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))

            # Отрисовка
            if game_type == "doghouse":
                img_buf = await game.render(result["matrix"], win)
            else:
                img_buf = await game.render(result["final_matrix"], win)
            await callback.message.answer_photo(
                BufferedInputFile(img_buf.getvalue(), filename=f"{game_type}.png"),
                caption=f"Выигрыш: {win} ⭐"
            )
            # Кнопка "Играть ещё"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🎰 Играть ещё {bet} ⭐", callback_data=f"play_{game_type}_{bet}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.answer("Выберите действие:", reply_markup=kb)

        elif game_type == "dice":
            result = game.generate_result(bet, user_id, kwargs.get("mode", "single"))
            base_win = game.calculate_base_win(bet, result)
            win = await game.finalize_win(base_win, bet, user_id)
            await self.db.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await self.db.add_game_history(user_id, game_type, bet, win, result)
            await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
            user_pf = user.get('pf_enabled', 1) if (user := await self.db.get_user(user_id)) else 1
            text = f"🎲 **КОСТИ**\n\nРезультат: {result['result']}\nМножитель: x{result['base_mult']:.2f}\nСтавка: {bet} ⭐\nВыигрыш: {win} ⭐"
            if user_pf:
                text += f"\n\n🔐 Provably Fair: `{result['hash']}`"
            jackpot = await self.db.get_jackpot()
            text += f"\n💰 Джекпот: {jackpot} ⭐"
            kb = self.get_game_keyboard(game_type, lang=lang)
            await callback.message.edit_text(text, reply_markup=kb)

        elif game_type == "roulette":
            result = game.generate_result(bet, user_id)
            base_win = game.calculate_base_win(bet, result, kwargs.get("bet_type"), kwargs.get("bet_number"))
            if base_win == 0:
                await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
                await callback.message.edit_text(f"❌ Вы проиграли! Выпало {result['number']} {result['color']}", reply_markup=self.get_game_keyboard(game_type, lang=lang))
                return
            win = await game.finalize_win(base_win, bet, user_id)
            await self.db.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await self.db.add_game_history(user_id, game_type, bet, win, result)
            await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
            jackpot = await self.db.get_jackpot()
            user_pf = user.get('pf_enabled', 1) if (user := await self.db.get_user(user_id)) else 1
            text = f"🎡 **РУЛЕТКА**\n\nВыпало: {result['number']} {result['color']}\nСтавка: {bet} ⭐\nВыигрыш: {win} ⭐"
            if user_pf:
                text += f"\n\n🔐 Provably Fair: `{result['hash']}`"
            text += f"\n💰 Джекпот: {jackpot} ⭐"
            await callback.message.edit_text(text, reply_markup=self.get_game_keyboard(game_type, lang=lang))

        elif game_type == "plinko":
            result = game.generate_result(bet, user_id, kwargs.get("risk", "medium"))
            base_win = game.calculate_base_win(bet, result)
            win = await game.finalize_win(base_win, bet, user_id)
            await self.db.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await self.db.add_game_history(user_id, game_type, bet, win, result)
            await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
            jackpot = await self.db.get_jackpot()
            user_pf = user.get('pf_enabled', 1) if (user := await self.db.get_user(user_id)) else 1
            text = f"📌 **PLINKO**\n\nПозиция: {result['final_position']}\nМножитель: x{result['base_mult']:.2f}\nСтавка: {bet} ⭐\nВыигрыш: {win} ⭐"
            if user_pf:
                text += f"\n\n🔐 Provably Fair: `{result['hash']}`"
            text += f"\n💰 Джекпот: {jackpot} ⭐"
            await callback.message.edit_text(text, reply_markup=self.get_game_keyboard(game_type, lang=lang))

        elif game_type == "keno":
            picks = kwargs.get("picks", [])
            result = game.generate_result(bet, user_id)
            base_win = game.calculate_base_win(bet, result, picks)
            if base_win == 0:
                await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
                await callback.message.edit_text(f"❌ Проигрыш! Угадано {sum(1 for p in picks if p in result['winning'])} из {len(picks)}", reply_markup=self.get_game_keyboard(game_type, lang=lang))
                return
            win = await game.finalize_win(base_win, bet, user_id)
            await self.db.update_balance(user_id, win, f"Выигрыш в {game_type}")
            await self.db.add_game_history(user_id, game_type, bet, win, result)
            await self.db.update_jackpot(int(bet * JACKPOT_PERCENT))
            jackpot = await self.db.get_jackpot()
            user_pf = user.get('pf_enabled', 1) if (user := await self.db.get_user(user_id)) else 1
            text = f"🎯 **КЕНО**\n\nУгадано: {sum(1 for p in picks if p in result['winning'])} из {len(picks)}\nСтавка: {bet} ⭐\nВыигрыш: {win} ⭐"
            if user_pf:
                text += f"\n\n🔐 Provably Fair: `{result['hash']}`"
            text += f"\n💰 Джекпот: {jackpot} ⭐"
            await callback.message.edit_text(text, reply_markup=self.get_game_keyboard(game_type, lang=lang))

        else:
            await callback.answer("Игра не реализована")

    # ---------- Вспомогательные методы для админки (редактор слотов) ----------
    async def edit_slot(self, callback: types.CallbackQuery, state: FSMContext, slot_type: str):
        settings = await self.db.get_game_settings(slot_type)
        text = (
            f"🎰 Редактирование {slot_type}\n\n"
            f"Текущие настройки:\n"
            f"Символы: {settings.get('symbols', [])}\n"
            f"Веса: {settings.get('weights', [])}\n"
            f"Значения: {settings.get('values', [])}\n"
            f"Wild: {settings.get('wild', '')}\n"
            f"Scatter: {settings.get('scatter', '')}\n"
            f"RTP: {settings.get('rtp', 76.82)}\n"
            f"Волатильность: {settings.get('volatility', 0.15)}\n\n"
            f"Выберите параметр для изменения:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Символы", callback_data=f"edit_{slot_type}_symbols"),
             InlineKeyboardButton(text="Веса", callback_data=f"edit_{slot_type}_weights")],
            [InlineKeyboardButton(text="Значения", callback_data=f"edit_{slot_type}_values"),
             InlineKeyboardButton(text="RTP", callback_data=f"edit_{slot_type}_rtp")],
            [InlineKeyboardButton(text="Волатильность", callback_data=f"edit_{slot_type}_volatility")],
            [InlineKeyboardButton(text="🏠 Назад", callback_data="admin_slot_edit")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)

    # ... (методы show_settings, show_tournaments, show_bonuses, claim_daily, claim_faucet, show_stats, show_referrals, show_history) аналогичны предыдущим версиям, с отключением daily и турниров ...
    # Для краткости они не повторяются, но в реальном файле должны быть.

# ---------- Инициализация и запуск ----------
casino = CasinoBot(db)

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await casino.cmd_start(message)

@dp.message(Command("balance"))
async def balance_cmd(message: types.Message):
    await casino.cmd_balance(message)

@dp.callback_query()
async def callback_query(callback: types.CallbackQuery, state: FSMContext):
    await casino.callback_handler(callback, state)

# ---------- Обработчики ввода ----------
# (полностью аналогичны предыдущим, включая handle_custom_bet и все админские обработчики)
# Они уже были представлены ранее, здесь не дублируются для экономии места.

# ---------- HTTP-сервер и фоновые задачи ----------
async def run_http_server():
    app = web.Application()
    async def handle(request):
        return web.Response(text="Casino bot running")
    app.router.add_get('/', handle)
    app.router.add_get('/health', handle)
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"HTTP сервер на порту {port}")

async def on_startup():
    await db.init_db()
    asyncio.create_task(run_http_server())
    logger.info("Бот запущен")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
