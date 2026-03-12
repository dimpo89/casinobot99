import math
import random
import logging
from typing import Dict, Optional

from config import MAX_WIN_MULTIPLIER, RTP_ACTUAL

logger = logging.getLogger(__name__)

class RTPManager:
    @staticmethod
    async def calculate_win(
        game_type: str,
        base_win: int,
        bet: int,
        user_id: int,
        db,
        game_settings: Optional[Dict] = None
    ) -> int:
        if game_settings is None:
            rtp_settings = await db.get_rtp_settings(game_type)
        else:
            rtp_settings = game_settings

        target_rtp = rtp_settings.get('current_rtp', RTP_ACTUAL) / 100.0
        volatility = rtp_settings.get('volatility', 0.15)

        stats = await db.get_user_game_stats(user_id, game_type)
        total_bets = stats.get('total_bets', 0)
        total_wins = stats.get('total_wins', 0)

        u1 = random.random()
        u2 = random.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        rtp_factor = target_rtp + volatility * z
        rtp_factor = max(0.3, min(2.5, rtp_factor))

        if total_bets > 10:
            current_rtp = total_wins / total_bets if total_bets > 0 else 0
            deviation = target_rtp - current_rtp
            correction = 1.0 + (deviation * 0.3)
            rtp_factor *= correction
            rtp_factor = max(0.3, min(2.5, rtp_factor))

        max_allowed = bet * MAX_WIN_MULTIPLIER
        final_win = int(base_win * rtp_factor)
        if final_win > max_allowed:
            final_win = max_allowed

        logger.debug(f"RTP {game_type}: base={base_win}, factor={rtp_factor:.3f}, final={final_win}")
        return final_win

    @staticmethod
    async def simulate_monte_carlo(
        game_type: str,
        iterations: int,
        bet: int,
        db,
        game_settings: Optional[Dict] = None,
        user_id: int = 0
    ) -> Dict:
        if game_settings is None:
            game_settings = await db.get_rtp_settings(game_type)

        total_wins = 0
        wins_list = []
        for _ in range(iterations):
            base_win = random.randint(0, bet * 50)
            win = await RTPManager.calculate_win(game_type, base_win, bet, user_id, db, game_settings)
            total_wins += win
            wins_list.append(win)

        mean_win = total_wins / iterations
        variance = sum((x - mean_win) ** 2 for x in wins_list) / iterations
        std_dev = math.sqrt(variance)
        total_bet = iterations * bet
        simulated_rtp = total_wins / total_bet * 100.0

        return {
            'iterations': iterations,
            'total_wins': total_wins,
            'mean_win': mean_win,
            'std_dev': std_dev,
            'simulated_rtp': simulated_rtp,
            'target_rtp': game_settings.get('current_rtp', 76.82)
      }
