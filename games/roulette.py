import secrets
from .base_game import BaseGame, ProvablyFair

class RouletteGame(BaseGame):
    def __init__(self):
        super().__init__("roulette")
        self.numbers = list(range(0,37))
        self.colors = {0: "green"}
        for i in range(1,37):
            if i in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]:
                self.colors[i] = "red"
            else:
                self.colors[i] = "black"

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "straight": 36, "split": 18, "street": 12, "corner": 9, "sixline": 6,
                "column": 3, "dozen": 3,
                "red": 2, "black": 2, "even": 2, "odd": 2, "low": 2, "high": 2,
                "max_mult": 36,
                "rtp": 76.82,
                "volatility": 0.1
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)
        seed = ProvablyFair.get_hash(server, client, nonce)
        number = ProvablyFair.get_random_number(seed, 0, 36)
        return {
            "number": number,
            "color": self.colors[number],
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": seed
        }

    def calculate_base_win(self, bet: int, result: Dict, bet_type: str, bet_number: int = None) -> int:
        num = result["number"]
        if bet_type == "straight" and bet_number == num:
            mult = self.settings['straight']
        elif bet_type == "split" and bet_number and abs(bet_number - num) in [1,3]:
            mult = self.settings['split']
        elif bet_type == "street" and bet_number and (num-1)//3 == (bet_number-1)//3:
            mult = self.settings['street']
        elif bet_type == "corner" and bet_number and num in [bet_number, bet_number+1, bet_number+3, bet_number+4]:
            mult = self.settings['corner']
        elif bet_type == "sixline" and bet_number and (num-1)//3 in [bet_number, bet_number+1]:
            mult = self.settings['sixline']
        elif bet_type.startswith("column") and bet_number:
            cols = {1:[1,4,7,10,13,16,19,22,25,28,31,34],
                    2:[2,5,8,11,14,17,20,23,26,29,32,35],
                    3:[3,6,9,12,15,18,21,24,27,30,33,36]}
            if num in cols.get(bet_number, []):
                mult = self.settings['column']
            else:
                return 0
        elif bet_type.startswith("dozen") and bet_number:
            dozens = {1: range(1,13), 2: range(13,25), 3: range(25,37)}
            if num in dozens.get(bet_number, []):
                mult = self.settings['dozen']
            else:
                return 0
        elif bet_type == "red" and result["color"] == "red":
            mult = self.settings['red']
        elif bet_type == "black" and result["color"] == "black":
            mult = self.settings['black']
        elif bet_type == "even" and num > 0 and num % 2 == 0:
            mult = self.settings['even']
        elif bet_type == "odd" and num % 2 == 1:
            mult = self.settings['odd']
        elif bet_type == "low" and 1 <= num <= 18:
            mult = self.settings['low']
        elif bet_type == "high" and 19 <= num <= 36:
            mult = self.settings['high']
        else:
            return 0
        return bet * mult
