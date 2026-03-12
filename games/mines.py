import secrets
from typing import List, Dict
from .base_game import BaseGame, ProvablyFair

class MinesGame(BaseGame):
    def __init__(self):
        super().__init__("mines")

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "gold_bonus": 0.1,
                "difficulty_mult": {"easy":0.8, "medium":1.0, "hard":1.2, "extreme":1.5},
                "max_mult": 1000,
                "rtp": 76.82,
                "volatility": 0.15
            }

    def generate_result(self, bet: int, user_id: int = None, mines: int = 3, difficulty: str = "medium") -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        total_cells = 25
        all_cells = list(range(total_cells))
        mine_positions = []
        for i in range(mines):
            seed = ProvablyFair.get_hash(server, client, nonce + i)
            idx = ProvablyFair.get_random_number(seed, 0, len(all_cells)-1)
            mine_positions.append(all_cells.pop(idx))

        gold_positions = []
        for i in range(2):
            if all_cells:
                seed = ProvablyFair.get_hash(server, client, nonce + mines + i)
                idx = ProvablyFair.get_random_number(seed, 0, len(all_cells)-1)
                gold_positions.append(all_cells.pop(idx))

        return {
            "mine_positions": mine_positions,
            "gold_positions": gold_positions,
            "mines": mines,
            "difficulty": difficulty,
            "difficulty_mult": self.settings['difficulty_mult'].get(difficulty, 1.0),
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict, revealed: List[int]) -> int:
        if not revealed:
            return 0
        for cell in revealed:
            if cell in result["mine_positions"]:
                return 0
        safe = 25 - result["mines"]
        mult = safe / (safe - len(revealed) + 1)
        gold_bonus = 1 + self.settings.get('gold_bonus',0.1) * sum(1 for c in revealed if c in result["gold_positions"])
        diff_mult = result["difficulty_mult"]
        return int(bet * mult * gold_bonus * diff_mult)
