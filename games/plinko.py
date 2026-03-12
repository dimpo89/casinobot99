from typing import Dict, Optional
from .base_game import BaseGame, ProvablyFair

class PlinkoGame(BaseGame):
    def __init__(self):
        super().__init__("plinko")

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "low": [16,9,2,1.4,1.2,1.1,1,0.5,0.5,1,1.1,1.2,1.4,2,9,16],
                "medium": [22,12,3,1.8,1.4,1.2,0.8,0.3,0.3,0.8,1.2,1.4,1.8,3,12,22],
                "high": [33,18,5,2.5,1.8,1.3,0.5,0.2,0.2,0.5,1.3,1.8,2.5,5,18,33],
                "max_mult": 33,
                "rtp": 76.82,
                "volatility": 0.15
            }

    def generate_result(self, bet: int, user_id: int = None, risk: str = "medium") -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = ProvablyFair.get_random_number(server, 0, 1000000)
        rows = 16
        pos = rows / 2
        for step in range(rows):
            seed = ProvablyFair.get_hash(server, client, nonce + step)
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
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["base_mult"])
