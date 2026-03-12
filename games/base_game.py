import hashlib
import secrets
from typing import Dict, List, Optional

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
        self.db = None  # будет установлен извне

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
