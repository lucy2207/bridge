"""
Persistent game log - one JSON object per line, appended to game_logs.jsonl
in the same folder as main.py. This is pure data collection: it doesn't
analyze anything itself, it just records what happened so it can be used
later (to tune the rules further, or eventually train something on).

What gets captured per game:
- The full deal: all 4 original 13-card hands. Yours and dummy's (and
  North's, if you played it) are known directly; the two truly hidden
  hands get reconstructed at the end of a completed deal from exactly
  what each of them played over the 13 tricks - no extra entry needed.
- The auction: every call, alongside what the engine suggested at that
  exact moment (null when it wasn't your decision to make).
- The play: every card, trick by trick, with the same suggested-vs-actual
  pairing, plus who won each trick.
- The final result: tricks won by each side, and the outcome.
- A status field: "completed" (played to the end), "passed out" (no
  contract), or "abandoned" (a new game was started before this one
  finished) - so future analysis can tell real results from partial ones.
"""
import json
import os
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_logs.jsonl")

SUIT_SYMBOL_TO_LETTER = {"♠": "S", "♥": "H", "♦": "D", "♣": "C"}
SUIT_KEY_TO_LETTER = {"spades": "S", "hearts": "H", "diamonds": "D", "clubs": "C"}


def _card_str(card):
    if card is None:
        return None
    rank, suit = card
    rank = "T" if rank == "10" else rank
    letter = SUIT_SYMBOL_TO_LETTER.get(suit) or SUIT_KEY_TO_LETTER.get(suit)
    return f"{rank}{letter}"


def _hand_to_strs(cards):
    return [_card_str(c) for c in cards]


class GameLog:
    """Accumulates one game's data as the app plays through it. Call
    finalize(status) once, at whatever point the game ends or is
    abandoned - further calls are ignored so a game is never logged twice."""

    def __init__(self):
        self.data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "first_bidder": None,
            "hands": {"north": None, "east": None, "south": None, "west": None},
            "auction": [],
            "contract": None,
            "dummy_seat": None,
            "play": [],
            "result": None,
            "status": "in_progress",
        }
        self._written = False

    def set_first_bidder(self, seat):
        self.data["first_bidder"] = seat

    def set_hand(self, seat, cards):
        if cards:
            self.data["hands"][seat] = _hand_to_strs(cards)

    def log_bid(self, seat, bid, suggested):
        self.data["auction"].append({"seat": seat, "bid": bid, "suggested": suggested})

    def set_contract(self, level, strain, declarer, dummy_seat):
        self.data["contract"] = {"level": level, "strain": strain, "declarer": declarer}
        self.data["dummy_seat"] = dummy_seat

    def start_trick(self, trick_no, leader):
        self.data["play"].append({"trick": trick_no, "leader": leader, "cards": [], "winner": None})

    def log_card(self, seat, card, suggested_card):
        if not self.data["play"]:
            self.start_trick(1, seat)
        self.data["play"][-1]["cards"].append({
            "seat": seat,
            "card": _card_str(card),
            "suggested": _card_str(suggested_card),
        })

    def finish_trick(self, winner):
        if self.data["play"]:
            self.data["play"][-1]["winner"] = winner

    def set_result(self, tricks_won, outcome):
        self.data["result"] = {"tricks_won": dict(tricks_won), "outcome": outcome}

    def finalize(self, status):
        if self._written:
            return
        self.data["status"] = status
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(self.data, ensure_ascii=False) + "\n")
        except Exception:
            pass  # logging must never break the app
        self._written = True

    def has_content(self):
        return bool(self.data["auction"]) or bool(self.data["play"])