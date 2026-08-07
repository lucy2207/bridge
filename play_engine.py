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


def suggest_card(hand, trick_so_far, trump_strain):
    """hand: remaining (rank, suit) cards for whoever is on play.
    trick_so_far: (seat, (rank, suit)) already played this trick.
    Returns (card, explanation)."""
    if not hand:
        return None, ""

    if not trick_so_far:
        suit = max(
            {s for _, s in hand},
            key=lambda s: sum(1 for r, s2 in hand if s2 == s),
        )
        cards_in_suit = sorted((c for c in hand if c[1] == suit),
                                key=lambda c: -RANK_VALUE[c[0]])
        card = cards_in_suit[0]
        return card, f"On lead: top of your longest suit ({suit}) to start establishing it."

    led_suit = trick_so_far[0][1][1]
    same_suit = [c for c in hand if c[1] == led_suit]

    if same_suit:
        best_in_trick = max((c for _, c in trick_so_far if c[1] == led_suit),
                             key=lambda c: RANK_VALUE[c[0]])
        trumped_already = any(
            trump_strain and c[1] == trump_strain and c[1] != led_suit
            for _, c in trick_so_far
        )
        if trumped_already:
            card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
            return card, "Someone already trumped this trick - play low, you can't win it in suit."
        winnable = [c for c in same_suit if RANK_VALUE[c[0]] > RANK_VALUE[best_in_trick[0]]]
        if winnable:
            card = min(winnable, key=lambda c: RANK_VALUE[c[0]])
            return card, "You can beat the trick - win it as cheaply as possible."
        card = min(same_suit, key=lambda c: RANK_VALUE[c[0]])
        return card, "You can't beat the trick in suit - play your lowest card."

    trumps = [c for c in hand if trump_strain and c[1] == trump_strain]
    already_trumped = any(trump_strain and c[1] == trump_strain for _, c in trick_so_far)
    if trumps and not already_trumped:
        card = min(trumps, key=lambda c: RANK_VALUE[c[0]])
        return card, "Out of the suit led - ruff with your lowest trump to take the trick."
    card = min(hand, key=lambda c: RANK_VALUE[c[0]])
    return card, "Can't follow suit or usefully trump - discard your lowest card."