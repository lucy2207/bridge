"""
Generates training data for a card-play model: random deals, solved
exactly by a double-dummy solver, turned into (features, best_card) pairs.

This generates as many perfectly-labeled examples as you want.
Each example is one decision point (a hand, a trump suit, a partial
trick) paired with the objectively correct card, according to exact
search over the fully-known deal.

Requires: pip install endplay

Usage:
    python generate_training_data.py --deals 2000 --out training_data.jsonl

This writes one JSON line per decision point. A later script trains a
model on this file.
"""
import argparse
import json
import random

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
PBN_RANK = {r: ("T" if r == "10" else r) for r in RANKS}
PBN_RANK_ORDER = "AKQJT98765432"
SUITS = ["♠", "♥", "♦", "♣"]
STRAIN_TO_LETTER = {"♠": "S", "♥": "H", "♦": "D", "♣": "C"}


def make_shuffled_deck():
    deck = [(r, s) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def deal_hands(deck):
    """Splits a shuffled 52-card deck into 4 hands of 13, N/E/S/W order."""
    return {
        "N": deck[0:13], "E": deck[13:26], "S": deck[26:39], "W": deck[39:52],
    }


def hand_to_pbn(cards):
    by_suit = {s: [] for s in SUITS}
    for rank, suit in cards:
        by_suit[suit].append(PBN_RANK[rank])
    parts = []
    for suit in SUITS:
        ranks = sorted(by_suit[suit], key=lambda r: PBN_RANK_ORDER.index(r))
        parts.append("".join(ranks))
    return ".".join(parts)


def deal_to_pbn(hands):
    return "N:" + " ".join(hand_to_pbn(hands[seat]) for seat in ("N", "E", "S", "W"))


def hand_features(hand, trump_strain, trick_so_far, acting_seat):
    """A simple, expandable feature vector for one decision point. Start
    simple - you can enrich this once the pipeline works end to end."""
    lengths = {s: sum(1 for r, s2 in hand if s2 == s) for s in SUITS}
    hcp_map = {"A": 4, "K": 3, "Q": 2, "J": 1}
    hcp = sum(hcp_map.get(r, 0) for r, _ in hand)
    return {
        "acting_seat": acting_seat,
        "trump": trump_strain,
        "hcp": hcp,
        "lengths": lengths,
        "trick_position": len(trick_so_far),
        "led_suit": trick_so_far[0][1][1] if trick_so_far else None,
        "cards_in_hand": [f"{r}{STRAIN_TO_LETTER[s]}" for r, s in hand],
    }


def generate_one_deal(deal_index, trump_strain):
    """Generates one random deal, solves the OPENING LEAD decision (trick 1)
    for whichever seat leads, as a first, simple slice of the problem.
    Extend this to walk through more tricks once the basic pipeline works -
    each additional trick needs the previous ones' cards removed and the
    solver re-run on the reduced hands."""
    from endplay.types import Deal, Player
    from endplay.dds import solve_board

    deck = make_shuffled_deck()
    hands = deal_hands(deck)
    pbn = deal_to_pbn(hands)
    deal = Deal(pbn)

    from endplay.types import Denom
    trump_map = {"♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds,
                 "♣": Denom.clubs, None: Denom.nt}
    deal.trump = trump_map[trump_strain]

    leader = random.choice(["N", "E", "S", "W"])
    seat_map = {"N": Player.north, "E": Player.east, "S": Player.south, "W": Player.west}
    deal.first = seat_map[leader]

    solved = solve_board(deal)
    # solved maps each legal card to how many tricks the leader's side
    # makes by playing it - the best card is whichever maximizes that.
    best_card = max(solved, key=solved.get)

    features = hand_features(hands[leader], trump_strain, [], leader)
    return {
        "deal_index": deal_index,
        "trump": trump_strain,
        "leader": leader,
        "hand": features["cards_in_hand"],
        "hcp": features["hcp"],
        "lengths": features["lengths"],
        "best_card": str(best_card),
        "tricks_if_best": solved[best_card],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deals", type=int, default=500)
    parser.add_argument("--out", type=str, default="training_data.jsonl")
    args = parser.parse_args()

    trumps = list(SUITS) + [None]  # None = notrump
    written = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for i in range(args.deals):
            trump = random.choice(trumps)
            try:
                example = generate_one_deal(i, trump)
            except Exception as exc:
                if i == 0:
                    print(f"First deal failed - likely an endplay API mismatch: {exc}")
                    print("Send me this error and I'll fix generate_one_deal().")
                    raise
                continue
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            written += 1
            if (i + 1) % 100 == 0:
                print(f"{i + 1}/{args.deals} deals processed, {written} examples written")

    print(f"Done. {written} examples written to {args.out}")


if __name__ == "__main__":
    main()