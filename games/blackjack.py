import secrets
from typing import List, Dict
from .base_game import BaseGame, ProvablyFair

class BlackjackGame(BaseGame):
    def __init__(self):
        super().__init__("blackjack")
        self.suits = ["♠", "♥", "♦", "♣"]
        self.ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        self.values = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":10,"Q":10,"K":10,"A":11}

    async def load_settings(self, db):
        await super().load_settings(db)
        if not self.settings:
            self.settings = {
                "decks": 4,
                "blackjack_payout": 1.5,
                "max_mult": 3,
                "rtp": 76.82,
                "volatility": 0.1
            }

    def generate_result(self, bet: int, user_id: int = None) -> Dict:
        server, client = ProvablyFair.generate_seeds()
        nonce = secrets.randbelow(1000000)
        deck = [(rank, suit) for suit in self.suits for rank in self.ranks] * self.settings['decks']
        shuffled = self._shuffle_deck(deck, server, client, nonce)
        player_hand = [shuffled[0], shuffled[2]]
        dealer_hand = [shuffled[1], shuffled[3]]
        remaining = shuffled[4:]
        player_score = self._hand_score(player_hand)
        dealer_up = dealer_hand[0]
        return {
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "deck": remaining,
            "player_score": player_score,
            "dealer_upcard": dealer_up,
            "server_seed": server,
            "client_seed": client,
            "nonce": nonce,
            "hash": ProvablyFair.get_hash(server, client, nonce)
        }

    def _shuffle_deck(self, deck, server, client, nonce):
        shuffled = deck.copy()
        for i in range(len(shuffled)-1, 0, -1):
            seed = ProvablyFair.get_hash(server, client, nonce + i)
            j = ProvablyFair.get_random_number(seed, 0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled

    def _hand_score(self, hand):
        score = 0
        aces = 0
        for rank,_ in hand:
            if rank == "A":
                aces += 1
                score += 11
            else:
                score += self.values[rank]
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    def dealer_play(self, dealer_hand, deck):
        score = self._hand_score(dealer_hand)
        while score < 17 and deck:
            dealer_hand.append(deck.pop(0))
            score = self._hand_score(dealer_hand)
        return dealer_hand

    def calculate_base_win(self, bet: int, player_hand, dealer_hand) -> int:
        player_score = self._hand_score(player_hand)
        dealer_score = self._hand_score(dealer_hand)
        if player_score > 21:
            return 0
        if dealer_score > 21:
            return bet * 2
        if player_score > dealer_score:
            return bet * 2
        if player_score == dealer_score:
            return bet
        return 0
