"""
Double-dummy card-play suggestions via Monte Carlo sampling + an exact solver.

Unlike play_engine.suggest_card (fixed heuristics: second-hand-low, third-
hand-high, etc), this module tries to find the objectively best card by:

  1. Repeatedly sampling a complete, legal deal for the hidden hand(s) -
     consistent with everyone's known card count and any suits they've
     already shown void in.
  2. Solving each sampled deal EXACTLY with a double-dummy solver (perfect
     information - given a specific, fully-known deal, trick-taking bridge
     has one objectively correct answer, no guessing).
  3. Averaging, across all samples, how many tricks your side makes with
     each card you could legally play right now, and recommending whichever
     scores highest on average.

Requires the `endplay` package: pip install endplay

This is intentionally isolated in its own module and wrapped in try/except
by the caller (main.py) - if endplay isn't installed, or a specific API
call doesn't match the installed version, the app falls back to the
heuristic engine in play_engine.py rather than crashing. Since I can't
verify the exact endplay API against a live install here, expect the
_solve_one_sample function specifically to need small adjustments - send
me the traceback and I'll fix the exact call.
"""
import random

PBN_RANK = {
    "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8",
    "9": "9", "10": "T", "J": "J", "Q": "Q", "K": "K", "A": "A",
}
PBN_RANK_ORDER = "AKQJT98765432"
SUIT_TO_PBN_LETTER = {"♠": "S", "♥": "H", "♦": "D", "♣": "C"}
PBN_LETTER_TO_SUIT = {v: k for k, v in SUIT_TO_PBN_LETTER.items()}
PBN_RANK_TO_OURS = {v: k for k, v in PBN_RANK.items()}


def endplay_available():
    try:
        import endplay  # noqa: F401
        return True
    except ImportError:
        return False


def _hand_to_pbn(cards):
    """cards: list of (rank, suit_symbol). Returns a PBN hand string like
    'AKQ2.T93.A2.QJT9' (suit order spades.hearts.diamonds.clubs)."""
    by_suit = {"♠": [], "♥": [], "♦": [], "♣": []}
    for rank, suit in cards:
        by_suit[suit].append(PBN_RANK[rank])
    parts = []
    for suit in ("♠", "♥", "♦", "♣"):
        ranks = sorted(by_suit[suit], key=lambda r: PBN_RANK_ORDER.index(r))
        parts.append("".join(ranks))
    return ".".join(parts)


def _sample_hidden_hands(hidden_unseen_pool, hidden_seat_counts, known_voids, max_attempts=300):
    """Randomly deals hidden_unseen_pool among the hidden seats, respecting
    each seat's exact remaining card count and any known voids. Returns
    {seat: [cards]} or None if no valid assignment was found (only happens
    with very tight void constraints)."""
    seats = list(hidden_seat_counts.keys())
    for _ in range(max_attempts):
        pool = list(hidden_unseen_pool)
        random.shuffle(pool)
        assignment = {s: [] for s in seats}
        remaining = dict(hidden_seat_counts)
        ok = True
        for card in pool:
            _, suit = card
            eligible = [s for s in seats if remaining[s] > 0 and suit not in known_voids.get(s, set())]
            if not eligible:
                ok = False
                break
            weights = [remaining[e] for e in eligible]
            chosen = random.choices(eligible, weights=weights)[0]
            assignment[chosen].append(card)
            remaining[chosen] -= 1
        if ok and all(v == 0 for v in remaining.values()):
            return assignment
    return None


def _solve_one_sample(hand, trick_so_far, trump_strain, acting_seat, known_hands, sampled_hidden):
    """Solves ONE fully-known sampled deal with the real double-dummy
    solver. Returns {(rank, suit_symbol): tricks_for_acting_side}.

    This is the one function most likely to need adjusting to match the
    exact installed endplay API - everything above/below it is our own
    logic and shouldn't need to change."""
    from endplay.types import Deal, Card, Denom, Player

    all_hands = dict(known_hands)
    all_hands[acting_seat] = hand
    all_hands.update(sampled_hidden)

    pbn = "N:" + " ".join(_hand_to_pbn(all_hands[s]) for s in ("north", "east", "south", "west"))
    deal = Deal(pbn)

    trump_map = {
        "♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds,
        "♣": Denom.clubs, None: Denom.nt,
    }
    deal.trump = trump_map[trump_strain]

    seat_map = {"north": Player.north, "east": Player.east, "south": Player.south, "west": Player.west}
    leader = trick_so_far[0][0] if trick_so_far else acting_seat
    deal.first = seat_map[leader]

    deal.curtrick = [
        Card(f"{PBN_RANK[r]}{SUIT_TO_PBN_LETTER[s]}") for _, (r, s) in trick_so_far
    ]

    from endplay.dds import solve_board
    solved = solve_board(deal)

    results = {}
    for card, tricks in solved.items():
        rank = PBN_RANK_TO_OURS[str(card)[0]]
        suit = PBN_LETTER_TO_SUIT[str(card)[1]]
        results[(rank, suit)] = tricks
    return results


def suggest_card_dds(hand, trick_so_far, trump_strain, acting_seat,
                      known_hands, hidden_unseen_pool, hidden_seat_counts,
                      known_voids, n_samples=20):
    """Main entry point. Raises on any failure (not installed, sampling
    failed, solver error) - callers should catch and fall back to
    play_engine.suggest_card. Returns (card, explanation)."""
    if not endplay_available():
        raise RuntimeError("endplay is not installed - run: pip install endplay")
    if not hand:
        raise RuntimeError("no cards to suggest from")

    scores = {card: [] for card in hand}
    successful_samples = 0
    last_error = None

    for _ in range(n_samples):
        sampled = _sample_hidden_hands(hidden_unseen_pool, hidden_seat_counts, known_voids)
        if sampled is None:
            continue
        try:
            result = _solve_one_sample(hand, trick_so_far, trump_strain, acting_seat, known_hands, sampled)
        except Exception as exc:  # noqa: BLE001 - want to keep trying other samples
            last_error = exc
            continue
        for card, tricks in result.items():
            if card in scores:
                scores[card].append(tricks)
        successful_samples += 1

    if successful_samples == 0:
        raise RuntimeError(f"DDS solving failed for every sample - last error: {last_error}")

    averaged = {c: sum(v) / len(v) for c, v in scores.items() if v}
    if not averaged:
        raise RuntimeError("solver ran but returned no usable results")

    best_card = max(averaged, key=averaged.get)
    best_score = averaged[best_card]
    return best_card, (
        f"Double-dummy simulation ({successful_samples} sampled deals): "
        f"expected {best_score:.1f} tricks for your side playing {best_card[0]}{best_card[1]}."
    )