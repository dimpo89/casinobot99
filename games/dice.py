from typing import Dict, Optional
from .base_game import BaseGame, ProvablyFair

class DiceGame(BaseGame):
    def __init__(self):
        super().__init__("dice")

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "single": {1:2, 2:1.5, 3:1.2, 4:1, 5:0.8, 6:0.5},
                "double": {2:3, 3:2, 4:1.5, 5:1.2, 6:1, 7:0.8, 8:1, 9:1.2, 10:1.5, 11:2, 12:3},
                "max_mult": 10,
                "rtp": 76.82,
                "volatility": 0.1
            }

    def generate_result(self, bet: int, user_id: int = None, mode: str = "single") -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = ProvablyFair.get_random_number(server, 0, 1000000)  # упростим
        if mode == "single":
            seed = ProvablyFair.get_hash(server, client, nonce)
            result = ProvablyFair.get_random_number(seed, 1, 6)
            base_mult = self.settings['single'][result]
        else:
            seed1 = ProvablyFair.get_hash(server, client, nonce)
            seed2 = ProvablyFair.get_hash(server, client, nonce+1)
            d1 = ProvablyFair.get_random_number(seed1, 1, 6)
            d2 = ProvablyFair.get_random_number(seed2, 1, 6)
            result = d1 + d2
            base_mult = self.settings['double'][result]
        return {
            "result": result,
            "base_mult": base_mult,
            "mode": mode,
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return int(bet * result["base_mult"])
