"""
Card-play engine for the trick-taking phase after the auction ends.

Covers: figuring out the contract/declarer/dummy from the auction,
determining who wins each trick, and suggesting a card to play. The
suggestion logic is deliberately simple standard-practice heuristics
(win as cheaply as possible / duck when you can't / ruff when void /
lead your longest suit) - not a double-dummy solver. It will not always
find the objectively best card in tricky end positions, but it reflects
sound general technique.
"""

RANK_ORDER_LIST = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER_LIST)}
SEATS = ["north", "east", "south", "west"]


def next_seat(seat):
    return SEATS[(SEATS.index(seat) + 1) % 4]


def partner_of(seat):
    return SEATS[(SEATS.index(seat) + 2) % 4]


def partnership_of(seat):
    return "NS" if seat in ("north", "south") else "EW"


def parse_contract(auction):
    """Returns (level, strain, declarer_seat) from a finished auction,
    or None if the hand was passed out."""
    last = None
    for seat, bid in auction:
        if bid not in ("Pass", "X", "XX"):
            last = (seat, bid)
    if last is None:
        return None
    final_seat, final_bid = last
    level, strain = int(final_bid[0]), final_bid[1:]
    partnership = {final_seat, partner_of(final_seat)}
    declarer = final_seat
    for seat, bid in auction:
        if seat in partnership and bid not in ("Pass", "X", "XX") and bid[1:] == strain:
            declarer = seat
            break
    return level, strain, declarer


def dummy_of(declarer):
    return partner_of(declarer)


def opening_leader(declarer):
    return next_seat(declarer)


def tricks_needed_for_contract(level):
    return 6 + level


def partner_bid_suit(auction, seat):
    """The first real suit partner bid during the auction, if any - used
    to prefer leading partner's suit on the opening lead."""
    partner = partner_of(seat)
    for s, b in auction:
        if s == partner and b not in ("Pass", "X", "XX") and b[1:] != "NT":
            return b[1:]
    return None


HONOR_RANKS = {"10", "J", "Q", "K", "A"}


def _top_sequence_length(ranks_desc):
    if not ranks_desc:
        return 0
    count = 1
    for i in range(len(ranks_desc) - 1):
        if RANK_VALUE[ranks_desc[i]] - RANK_VALUE[ranks_desc[i + 1]] == 1:
            count += 1
        else:
            break
    return count


def _lead_card_in_suit(cards_in_suit):
    """Standard opening-lead card selection within a chosen suit: top of a
    (possibly broken) sequence, else fourth-best from a long suit, else
    top of a doubleton, else low from a 3-card suit with an honor, else
    top of nothing."""
    ordered = sorted(cards_in_suit, key=lambda c: -RANK_VALUE[c[0]])
    ranks_desc = [c[0] for c in ordered]
    seq_len = _top_sequence_length(ranks_desc)
    if seq_len >= 2:
        return ordered[0], "top of your sequence"
    if len(ordered) >= 4:
        return ordered[3], "fourth-best"
    if len(ordered) == 2:
        return ordered[0], "top of your doubleton"
    if len(ordered) == 3 and any(r in HONOR_RANKS for r in ranks_desc):
        return ordered[-1], "low from your honor"
    return ordered[0], "top of nothing"


def _choose_opening_lead(hand, partner_suit):
    """The very first card of the deal, played by the defender to
    declarer's left. Prefers partner's bid suit; otherwise the longest
    suit, using proper lead-card technique within whichever is chosen."""
    suits_present = {s for _, s in hand}
    if partner_suit and partner_suit in suits_present:
        suit, source = partner_suit, "partner's suit"
    else:
        suit = max(suits_present, key=lambda s: sum(1 for _, s2 in hand if s2 == s))
        source = "your longest suit"
    cards_in_suit = [c for c in hand if c[1] == suit]
    card, technique = _lead_card_in_suit(cards_in_suit)
    return card, f"Opening lead: {technique} in {suit} ({source})."


def _best_discard(hand, trump_strain):
    """Prefer discarding from your shortest non-trump suit, to preserve
    length (and any strength) in your longer suits."""
    non_trump_suits = {s for _, s in hand if s != trump_strain}
    if not non_trump_suits:
        return min(hand, key=lambda c: RANK_VALUE[c[0]])
    shortest = min(non_trump_suits, key=lambda s: sum(1 for _, s2 in hand if s2 == s))
    candidates = [c for c in hand if c[1] == shortest]
    return min(candidates, key=lambda c: RANK_VALUE[c[0]])


def trick_winner(trick, trump_strain):
    """trick: list of (seat, (rank, suit)) in the order played."""
    led_suit = trick[0][1][1]

    def strength(card):
        rank, suit = card
        if trump_strain and trump_strain != "NT" and suit == trump_strain:
            return (2, RANK_VALUE[rank])
        if suit == led_suit:
            return (1, RANK_VALUE[rank])
        return (0, RANK_VALUE[rank])

    best_seat, best_card = trick[0]
    best_strength = strength(best_card)
    for seat, card in trick[1:]:
        s = strength(card)
        if s > best_strength:
            best_strength = s
            best_seat, best_card = seat, card
    return best_seat


def suggest_card(hand, trick_so_far, trump_strain, acting_seat, is_declaring_side=False,
                  known_voids=None, is_opening_lead=False, partner_suit=None):
    """hand: remaining (rank, suit) cards for whoever is on play.
    trick_so_far: (seat, (rank, suit)) already played this trick, in order.
    acting_seat: whose turn it is (needed to know who's "partner" vs "opponent").
    known_voids: {seat: set(suits)} - suits a seat has already shown out of
    this deal, used to avoid leading into a hand that can ruff for free.
    is_opening_lead / partner_suit: True and the auction's known suit,
    respectively, only for the very first lead of the deal by a defender -
    unlocks real opening-lead technique (partner's suit, sequences,
    fourth-best) instead of the general "longest suit" leading rule.
    Returns (card, explanation).

    Follows real technique rather than just "win if you can":
    - Never overtake your own partner's card that's already winning.
    - Second hand (1 card played, an opponent's): play low, keep options open.
    - Third hand (2 played, opponent still winning): play high - you don't
      know what the last player holds, so make them beat your best.
    - Last to play: win as cheaply as possible if you can, otherwise duck.
    - Don't lead a suit a defender is known void in (or NT) - leading into
      a hand that has nothing there is safe; leading into one with a
      trump lets them ruff it for free.
    """
    if not hand:
        return None, ""
    known_voids = known_voids or {}
    opponents = [s for s in SEATS if partnership_of(s) != partnership_of(acting_seat)]

    if not trick_so_far:
        if is_opening_lead and not is_declaring_side:
            return _choose_opening_lead(hand, partner_suit)

        suits_present = {s for _, s in hand}

        if trump_strain and is_declaring_side:
            trump_count = sum(1 for _, s in hand if s == trump_strain)
            singletons = [
                s for s in suits_present
                if s != trump_strain and sum(1 for _, s2 in hand if s2 == s) == 1
            ]
            if singletons and trump_count >= 2:
                suit = singletons[0]
                card = next(c for c in hand if c[1] == suit)
                return card, (
                    f"Leading your singleton {suit} - once it's gone, you can ruff "
                    f"that suit later with a trump (\"couper\")."
                )
            if trump_count >= 2:
                trumps = sorted((c for c in hand if c[1] == trump_strain),
                                 key=lambda c: -RANK_VALUE[c[0]])
                return trumps[0], (
                    f"Drawing trumps (\"faire tomber les atouts\"): leading {trump_strain} "
                    f"so the defense runs out and can't ruff your winners later."
                )

        # Avoid leading a suit a defender is known void in - they can ruff it away.
        risky_suits = set()
        if trump_strain:
            for opp in opponents:
                risky_suits |= known_voids.get(opp, set())
        ranked_suits = sorted(suits_present, key=lambda s: -sum(1 for _, s2 in hand if s2 == s))
        safe_suits = [s for s in ranked_suits if s not in risky_suits]
        suit = safe_suits[0] if safe_suits else ranked_suits[0]
        cards_in_suit = sorted((c for c in hand if c[1] == suit), key=lambda c: -RANK_VALUE[c[0]])
        card = cards_in_suit[0]
        note = " (your longest safe suit - a defender is known void elsewhere)" if safe_suits and safe_suits[0] != ranked_suits[0] else ""
        return card, f"On lead: top of your longest suit ({suit}) to start establishing it{note}."

    led_suit = trick_so_far[0][1][1]
    same_suit = [c for c in hand if c[1] == led_suit]
    n_played = len(trick_so_far)

    if same_suit:
        best_seat, best_card = trick_so_far[0]
        for seat, card in trick_so_far[1:]:
            if card[1] == led_suit and RANK_VALUE[card[0]] > RANK_VALUE[best_card[0]]:
                best_seat, best_card = seat, card
        trumped_already = any(
            trump_strain and c[1] == trump_strain and c[1] != led_suit for _, c in trick_so_far
        )
        if trumped_already:
            card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
            return card, "Someone already trumped this trick - play low, you can't win it in suit."

        partner_winning = partnership_of(best_seat) == partnership_of(acting_seat)
        if partner_winning:
            card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
            return card, "Your side is already winning this trick - play low and save your high cards."

        winnable = [c for c in same_suit if RANK_VALUE[c[0]] > RANK_VALUE[best_card[0]]]
        if n_played == 3:
            if winnable:
                card = min(winnable, key=lambda c: RANK_VALUE[c[0]])
                return card, "You're last to play and can beat it - win as cheaply as possible."
            card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
            return card, "You're last to play but can't beat it - play your lowest card."
        if n_played == 2:
            if winnable:
                card = max(same_suit, key=lambda c: RANK_VALUE[c[0]])
                return card, "Third hand high: play your best card - you don't know what's left for the last player."
            card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
            return card, "Even your best card can't beat this - play low and save your strength."
        card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
        return card, "Second hand low: don't commit your strength yet - let it come back to you or partner."

    trumps = [c for c in hand if trump_strain and c[1] == trump_strain]
    trumped_by = None
    best_trump = None
    for seat, c in trick_so_far:
        if trump_strain and c[1] == trump_strain:
            if best_trump is None or RANK_VALUE[c[0]] > RANK_VALUE[best_trump[0]]:
                best_trump, trumped_by = c, seat

    if trumps:
        if trumped_by is not None:
            if partnership_of(trumped_by) == partnership_of(acting_seat):
                card = _best_discard(hand, trump_strain)
                return card, "Partner already ruffed this trick - no need to overtrump, discard from your shortest suit."
            higher = [c for c in trumps if RANK_VALUE[c[0]] > RANK_VALUE[best_trump[0]]]
            if higher:
                card = min(higher, key=lambda c: RANK_VALUE[c[0]])
                return card, "An opponent ruffed - overtrump as cheaply as possible to take it back."
            card = _best_discard(hand, trump_strain)
            return card, "An opponent ruffed higher than you can beat - discard from your shortest suit instead."
        card = min(trumps, key=lambda c: RANK_VALUE[c[0]])
        return card, "Out of the suit led - ruff with your lowest trump to take the trick."

    card = _best_discard(hand, trump_strain)
    return card, "Can't follow suit or usefully trump - discard from your shortest suit to keep your length elsewhere."