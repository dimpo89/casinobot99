import secrets
from typing import List, Dict
from .base_game import BaseGame, ProvablyFair

class KenoGame(BaseGame):
    def __init__(self):
        super().__init__("keno")

    async def load_settings(self, db):
        await super().load_settings(db)
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
                "max_mult": 15000,
                "rtp": 76.82,
                "volatility": 0.1
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)

        nums = list(range(1,81))
        winning = []
        for i in range(20):
            seed = ProvablyFair.get_hash(server, client, nonce + i)
            idx = ProvablyFair.get_random_number(seed, 0, len(nums)-1)
            winning.append(nums.pop(idx))

        return {
            "winning": winning,
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
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
