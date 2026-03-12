import hashlib
import secrets
import io
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

class ProvablyFair:
    @staticmethod
    def generate_seeds() -> tuple[str, str]:
        server = secrets.token_hex(32)
        client = secrets.token_hex(16)
        return server, client

    @staticmethod
    def get_hash(server: str, client: str, nonce: int) -> str:
        combined = f"{server}:{client}:{nonce}"
        return hashlib.sha256(combined.encode()).hexdigest()

    @staticmethod
    def get_random_number(seed: str, min_val: int, max_val: int) -> int:
        hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        return min_val + (hash_val % (max_val - min_val + 1))

class BaseGame:
    def __init__(self, game_type: str):
        self.game_type = game_type
        self.settings = {}
        self.db = None

    async def load_settings(self, db):
        self.db = db
        self.settings = await db.get_game_settings(self.game_type)

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        raise NotImplementedError

    def generate_result(self, bet: int, user_id: int = None, **kwargs) -> Dict:
        raise NotImplementedError

    async def finalize_win(self, base_win: int, bet: int, user_id: int) -> int:
        from rtp import RTPManager
        return await RTPManager.calculate_win(self.game_type, base_win, bet, user_id, self.db, self.settings)

    async def render(self, matrix: List[List[str]], win: int = 0) -> io.BytesIO:
        """Базовый рендер с эмодзи (можно переопределить в наследниках)."""
        cell_size = 80
        rows = len(matrix)
        cols = len(matrix[0]) if rows else 0
        width = cols * cell_size
        height = rows * cell_size + 50
        img = Image.new('RGB', (width, height), color=(30,30,30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()
        for i, row in enumerate(matrix):
            for j, sym in enumerate(row):
                x = j * cell_size
                y = i * cell_size
                draw.rectangle([x, y, x+cell_size-2, y+cell_size-2], outline=(100,100,100), width=2)
                draw.text((x+20, y+20), sym, fill=(255,255,255), font=font)
        draw.text((10, height-40), f"Выигрыш: {win}", fill=(255,215,0), font=font)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
