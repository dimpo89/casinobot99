import math
import random
import logging
from typing import Dict, Optional

from config import MAX_WIN_MULTIPLIER, RTP_ACTUAL

logger = logging.getLogger(__name__)

class RTPManager:
    """
    Управление расчётом выигрыша с учётом целевого RTP, волатильности,
    истории игрока, открутки/подкрутки (tilt) и ограничений.
    """

    @staticmethod
    async def calculate_win(
        game_type: str,
        base_win: int,
        bet: int,
        user_id: int,
        db,
        game_settings: Optional[Dict] = None
    ) -> int:
        """
        Рассчитывает финальный выигрыш на основе базового выигрыша.

        :param game_type: тип игры (например, 'sugarrush')
        :param base_win: базовый выигрыш (рассчитанный по комбинациям, без учёта RTP)
        :param bet: ставка пользователя
        :param user_id: ID пользователя
        :param db: объект базы данных (с методами get_rtp_settings, get_user_game_stats, get_tilt)
        :param game_settings: настройки игры (опционально, если уже загружены)
        :return: итоговый выигрыш
        """
        # 1. Получаем настройки RTP для игры
        if game_settings is None:
            rtp_settings = await db.get_rtp_settings(game_type)
        else:
            rtp_settings = game_settings

        target_rtp = rtp_settings.get('current_rtp', RTP_ACTUAL) / 100.0
        volatility = rtp_settings.get('volatility', 0.15)  # среднеквадратическое отклонение

        # 2. Получаем историю пользователя по этой игре
        stats = await db.get_user_game_stats(user_id, game_type)
        total_bets = stats.get('total_bets', 0)
        total_wins = stats.get('total_wins', 0)

        # 3. Генерация фактора RTP по нормальному распределению (метод Бокса-Мюллера)
        u1 = random.random()
        u2 = random.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        rtp_factor = target_rtp + volatility * z
        rtp_factor = max(0.3, min(2.5, rtp_factor))  # защита от экстремальных значений

        # 4. Коррекция на основе истории (чтобы на длинной дистанции сходилось к target_rtp)
        if total_bets > 10:
            current_rtp = total_wins / total_bets if total_bets > 0 else 0
            deviation = target_rtp - current_rtp
            # Коррекция: если игрок недовыигрывает, слегка повышаем фактор, и наоборот
            correction = 1.0 + (deviation * 0.3)  # коэффициент усиления коррекции
            rtp_factor *= correction
            rtp_factor = max(0.3, min(2.5, rtp_factor))

        # 5. Применяем открутку/подкрутку (tilt) – множитель, установленный админом
        tilt = await db.get_tilt(game_type)
        rtp_factor *= tilt

        # 6. Ограничение максимального выигрыша (защита от багов)
        max_allowed = bet * MAX_WIN_MULTIPLIER
        final_win = int(base_win * rtp_factor)
        if final_win > max_allowed:
            final_win = max_allowed

        logger.debug(
            f"RTP {game_type}: base={base_win}, factor={rtp_factor:.3f}, "
            f"final={final_win}, max={max_allowed}, tilt={tilt}"
        )

        return final_win

    @staticmethod
    async def simulate_monte_carlo(
        game_type: str,
        iterations: int,
        bet: int,
        db,
        game_settings: Optional[Dict] = None,
        user_id: int = 0  # фиктивный пользователь для статистики (0 = без истории)
    ) -> Dict:
        """
        Симуляция Монте-Карло для оценки среднего выигрыша и дисперсии.
        Полезна для настройки параметров RTP и волатильности.

        :param game_type: тип игры
        :param iterations: количество симуляций
        :param bet: фиксированная ставка
        :param db: объект базы данных
        :param game_settings: настройки игры (если None, будут загружены из БД)
        :param user_id: ID пользователя (можно передать 0, чтобы игнорировать историю)
        :return: словарь со статистикой
        """
        if game_settings is None:
            game_settings = await db.get_rtp_settings(game_type)

        total_wins = 0
        wins_list = []
        for _ in range(iterations):
            # Генерируем случайный базовый выигрыш (для симуляции нам нужно знать распределение базовых выигрышей,
            # но это зависит от конкретной игры. Для обобщённой симуляции можно использовать
            # типичное распределение, например, логнормальное. Пока упростим:
            # будем считать, что базовый выигрыш распределён равномерно от 0 до bet*50.
            # В реальности нужно подставить реальную функцию генерации игры.
            base_win = random.randint(0, bet * 50)
            win = await RTPManager.calculate_win(
                game_type, base_win, bet, user_id, db, game_settings
            )
            total_wins += win
            wins_list.append(win)

        mean_win = total_wins / iterations
        # Дисперсия
        variance = sum((x - mean_win) ** 2 for x in wins_list) / iterations
        std_dev = math.sqrt(variance)

        # Оценка RTP на симуляции (общий выигрыш / общие ставки)
        total_bet = iterations * bet
        simulated_rtp = total_wins / total_bet * 100.0

        return {
            'iterations': iterations,
            'total_wins': total_wins,
            'mean_win': mean_win,
            'std_dev': std_dev,
            'simulated_rtp': simulated_rtp,
            'target_rtp': game_settings.get('current_rtp', RTP_ACTUAL)
        }
