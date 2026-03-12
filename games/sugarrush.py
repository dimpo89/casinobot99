import secrets
import io
from typing import List, Dict, Optional
from .base_game import BaseGame, ProvablyFair

class SugarRushGame(BaseGame):
    def __init__(self):
        super().__init__("sugarrush")
        self.rows = 7
        self.cols = 7

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "symbols": ["🍬", "🍭", "🍫", "🍩", "🍪", "🧁", "🍰", "🎂"],
                "weights": [100,80,60,40,20,10,5,2],
                "values": [2,3,4,5,8,12,20,30],
                "wild": "🍬",
                "scatter": "🍭",
                "cascade_multiplier": 1.5,
                "free_spins_count": 10,
                "max_mult": 2000,
                "rtp": 76.82,
                "volatility": 0.25
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

    def _generate_initial_matrix(self, server, client, nonce):
        matrix = []
        for i in range(self.rows):
            row = []
            for j in range(self.cols):
                seed = ProvablyFair.get_hash(server, client, nonce + i*self.cols + j)
                row.append(self._choose_symbol(seed))
            matrix.append(row)
        return matrix

    def _find_clusters(self, matrix):
        visited = [[False]*self.cols for _ in range(self.rows)]
        clusters = []
        for i in range(self.rows):
            for j in range(self.cols):
                if visited[i][j] or matrix[i][j] is None:
                    continue
                symbol = matrix[i][j]
                queue = [(i,j)]
                cluster = []
                while queue:
                    r,c = queue.pop(0)
                    if visited[r][c]:
                        continue
                    visited[r][c] = True
                    if matrix[r][c] == symbol:
                        cluster.append((r,c))
                        for dr,dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nr,nc = r+dr, c+dc
                            if 0<=nr<self.rows and 0<=nc<self.cols and not visited[nr][nc] and matrix[nr][nc] == symbol:
                                queue.append((nr,nc))
                if len(cluster) >= 3:
                    clusters.append(cluster)
        return clusters

    def _apply_gravity(self, matrix):
        for j in range(self.cols):
            col = [matrix[i][j] for i in range(self.rows) if matrix[i][j] is not None]
            col = [None]*(self.rows - len(col)) + col
            for i in range(self.rows):
                matrix[i][j] = col[i]
        return matrix

    def _fill_empty(self, matrix, server, client, offset):
        for i in range(self.rows):
            for j in range(self.cols):
                if matrix[i][j] is None:
                    seed = ProvablyFair.get_hash(server, client, offset + i*self.cols + j)
                    matrix[i][j] = self._choose_symbol(seed)

    def generate_result(self, bet: int, user_id: int = None, force_bonus: bool = False) -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = ProvablyFair.get_random_number(server, 0, 1000000)
        matrix = self._generate_initial_matrix(server, client, nonce)
        total_win = 0
        cascade_mult = 1.0
        cascade_count = 0
        while True:
            clusters = self._find_clusters(matrix)
            if not clusters:
                break
            step_win = 0
            for cluster in clusters:
                symbol = matrix[cluster[0][0]][cluster[0][1]]
                idx = self.settings['symbols'].index(symbol)
                step_win += len(cluster) * self.settings['values'][idx] * bet
            total_win += int(step_win * cascade_mult)
            for cluster in clusters:
                for r,c in cluster:
                    matrix[r][c] = None
            matrix = self._apply_gravity(matrix)
            self._fill_empty(matrix, server, client, nonce + cascade_count + 1)
            cascade_mult *= self.settings['cascade_multiplier']
            cascade_count += 1
        scatter_count = sum(row.count(self.settings['scatter']) for row in matrix)
        bonus_triggered = force_bonus or (scatter_count >= 3)
        return {
            "total_win": total_win,
            "cascade_count": cascade_count,
            "bonus_triggered": bonus_triggered,
            "scatter_count": scatter_count,
            "final_matrix": matrix,
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def calculate_base_win(self, bet: int, result: Dict) -> int:
        return result["total_win"]

    async def play_bonus_game(self, user_id: int, bet: int) -> int:
        total = 0
        for _ in range(10):
            result = self.generate_result(bet, user_id, force_bonus=False)
            win = result["total_win"] * 2
            total += win
        return total

    async def render(self, matrix: List[List[str]], win: int = 0) -> io.BytesIO:
        return await super().render(matrix, win)
