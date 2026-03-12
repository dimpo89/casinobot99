import secrets
import random
import io
from typing import List, Dict
from PIL import Image, ImageDraw, ImageFont
from .base_game import BaseGame, ProvablyFair

class DogHouseGame(BaseGame):
    def __init__(self):
        super().__init__("doghouse")
        self.rows = 3
        self.cols = 5
        self.symbols = ["🐶", "🐩", "🐕", "🏠", "💎", "7️⃣", "⭐", "🎰"]
        self.default_weights = [100,80,60,40,20,10,5,2]
        self.default_values = [2,3,4,5,8,12,20,30]
        self.wild = "⭐"
        self.scatter = "🏠"

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "symbols": self.symbols,
                "weights": self.default_weights,
                "values": self.default_values,
                "wild": self.wild,
                "scatter": self.scatter,
                "free_spins_count": 10,
                "wild_multipliers": [2,3,4,5],
                "max_mult": 500,
                "rtp": 76.82,
                "volatility": 0.2
            }
        cum = 0
        self.cum_weights = []
        for w in self.settings['weights']:
            cum += w
            self.cum_weights.append(cum)
        self.total_weight = cum

    def _choose_symbol(self, seed: str) -> str:
        r = ProvablyFair.get_random_number(seed, 1, self.total_weight)
        for idx, cw in enumerate(self.cum_weights):
            if r <= cw:
                return self.settings['symbols'][idx]
        return self.settings['symbols'][-1]

    def generate_result(self, bet: int, user_id: int = None, force_bonus: bool = False) -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)
        matrix = []
        for i in range(self.rows):
            row = []
            for j in range(self.cols):
                seed = ProvablyFair.get_hash(server, client, nonce + i*self.cols + j)
                row.append(self._choose_symbol(seed))
            matrix.append(row)
        scatter_count = sum(row.count(self.settings['scatter']) for row in matrix)
        bonus_triggered = force_bonus or (scatter_count >= 3)
        return {
            "matrix": matrix,
            "bonus_triggered": bonus_triggered,
            "scatter_count": scatter_count,
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        matrix = result["matrix"]
        wild = self.settings['wild']
        values = self.settings['values']
        symbols = self.settings['symbols']
        win = 0
        for row in matrix:
            if all(s == row[0] or s == wild for s in row):
                main = next((s for s in row if s != wild), wild)
                idx = symbols.index(main)
                win += bet * values[idx]
        return win

    async def play_bonus_game(self, user_id: int, bet: int) -> int:
        spins = self.settings['free_spins_count']
        sticky = []
        total_win = 0
        wild = self.settings['wild']
        for _ in range(spins):
            server, client = ProvablyFair.generate_seeds()
            nonce = secrets.randbelow(1000000)
            matrix = []
            for i in range(self.rows):
                row = []
                for j in range(self.cols):
                    if (i,j) in sticky:
                        row.append(wild)
                    else:
                        seed = ProvablyFair.get_hash(server, client, nonce + i*self.cols + j)
                        row.append(self._choose_symbol(seed))
                matrix.append(row)
            for i in range(self.rows):
                for j in range(self.cols):
                    if matrix[i][j] == wild and (i,j) not in sticky:
                        sticky.append((i,j))
            spin_win = 0
            for i in range(self.rows):
                if all(matrix[i][j] == wild or matrix[i][j] == matrix[i][0] for j in range(self.cols)):
                    main = next((matrix[i][j] for j in range(self.cols) if matrix[i][j] != wild), wild)
                    idx = self.settings['symbols'].index(main) if main in self.settings['symbols'] else 0
                    spin_win += bet * self.settings['values'][idx]
            sticky_mult = 1 + len(sticky) * 0.2
            if sticky_mult > 3.0:
                sticky_mult = 3.0
            total_win += int(spin_win * sticky_mult)
        return total_win

    async def render(self, matrix: List[List[str]], win: int = 0) -> io.BytesIO:
        cell_size = 100
        width = self.cols * cell_size
        height = self.rows * cell_size + 50
        img = Image.new('RGB', (width, height), color=(30,30,30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except:
            font = ImageFont.load_default()
        for i,row in enumerate(matrix):
            for j,sym in enumerate(row):
                x = j * cell_size
                y = i * cell_size
                draw.rectangle([x,y,x+cell_size-2,y+cell_size-2], outline=(100,100,100), width=2)
                draw.text((x+20,y+20), sym, fill=(255,255,255), font=font)
        draw.text((10, height-40), f"Выигрыш: {win}", fill=(255,215,0), font=font)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
