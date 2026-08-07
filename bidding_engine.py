"""
Bridge bidding engine - Five Card Major (SEF / "Majeure 5eme") heuristics.

Grounded in the standard SEF (Systeme d'Enseignement Francais) reference:
- Opening 1-level: 12-17 HCP (up to ~22-23 with a strong two-suiter),
  longest suit, 5+ cards required to open a major.
- 1NT opening: 15-17 HCP, balanced.
- 2 clubs opening: strong artificial, forcing, 23+ HCP (or equivalent).
- Barrages (preempts): weak hand (5-10 HCP), long suit, level scales with
  suit length - 2 level for a 6-card major, 3 level for 7 cards, 4 level
  for 8 cards, 5 level for a 9-card minor. Designed to crowd opponents.
- Takeout double ("contre d'appel"): roughly opening values (12+, more at
  higher levels), short in opener's suit, support for the other suits.
  It is forcing - partner must bid, majors take priority.
- Simple overcall: ~8-16 HCP, a decent 5+ card suit.
- 1NT overcall: 15-18 HCP, balanced, a stopper in opener's suit.

This still simplifies plenty (no Stayman/transfers/Blackwood/negative
doubles/2-over-1 game-force yet) but every function below always returns
a concrete call - never "use your judgement" - falling back to sound
general principles (support first, then longest suit, then pass) when no
specific rule applies.
"""

RANK_VALUES = {"A": 4, "K": 3, "Q": 2, "J": 1}
STRAIN_RANK = {"♣": 0, "♦": 1, "♥": 2, "♠": 3, "NT": 4}
MAJORS = ("♠", "♥")
MINORS = ("♣", "♦")
SUIT_SYMBOL = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
SEATS = ["north", "east", "south", "west"]


def hand_stats(hand):
    lengths = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
    hcp = 0
    for rank, suit in hand:
        s = SUIT_SYMBOL[suit]
        lengths[s] += 1
        hcp += RANK_VALUES.get(rank, 0)
    shape = sorted(lengths.values(), reverse=True)
    balanced = shape in ([4, 3, 3, 3], [4, 4, 3, 2], [5, 3, 3, 2])
    return {"hcp": hcp, "lengths": lengths, "shape": shape, "balanced": balanced}


def format_hand_breakdown(stats):
    lengths = stats["lengths"]
    shape_str = "  ".join(f"{s} {lengths[s]}" for s in ("♠", "♥", "♦", "♣"))
    balance_str = "balanced" if stats["balanced"] else "unbalanced"
    return f"{stats['hcp']} HCP   |   {shape_str}   |   {balance_str}"


def choose_opening_suit(lengths):
    if lengths["♠"] >= 5 and lengths["♠"] >= lengths["♥"]:
        return "♠"
    if lengths["♥"] >= 5:
        return "♥"
    if lengths["♦"] > lengths["♣"]:
        return "♦"
    if lengths["♣"] > lengths["♦"]:
        return "♣"
    return "♦" if lengths["♦"] >= 4 else "♣"


# suit length -> barrage (preempt) level. Majors can open a weak 2;
# minors start barraging at the 3-level (2C/2D are reserved elsewhere).
_MAJOR_BARRAGE_LEVELS = {6: 2, 7: 3, 8: 4}
_MINOR_BARRAGE_LEVELS = {7: 3, 8: 4, 9: 5}


def suggest_opening(stats):
    hcp, lengths, balanced = stats["hcp"], stats["lengths"], stats["balanced"]
    if hcp >= 23:
        return "2♣", "Strong artificial, forcing: 23+ HCP (or equivalent playing strength)."
    if 15 <= hcp <= 17 and balanced:
        return "1NT", "15-17 HCP, balanced hand (no 5-card major, no singleton/void)."

    if hcp < 12:
        longest = max(lengths, key=lengths.get)
        length = lengths[longest]
        if 5 <= hcp <= 10:
            table = _MAJOR_BARRAGE_LEVELS if longest in MAJORS else _MINOR_BARRAGE_LEVELS
            level = table.get(length)
            if level:
                return (
                    f"{level}{longest}",
                    f"Barrage (preempt): {length}-card {longest}, {hcp} HCP - a weak hand "
                    f"designed to crowd the opponents' auction, not to invite anything.",
                )
        return "Pass", f"{hcp} HCP and no barrage shape (need a long suit): not enough to open."

    suit = choose_opening_suit(lengths)
    plural = "s" if lengths[suit] > 1 else ""
    return f"1{suit}", f"Opening bid: 12-17 HCP, {lengths[suit]} card{plural} in {suit}."


def suggest_raise(stats, suit):
    hcp = stats["hcp"]
    support = stats["lengths"][suit]
    if support < 3:
        return None
    if hcp < 6:
        return "Pass", f"0-5 HCP: not enough to respond, even with {support}-card support."
    if hcp <= 9:
        return f"2{suit}", f"Simple raise: 6-9 HCP, {support}-card support."
    if hcp <= 12:
        return f"3{suit}", f"Limit raise: 10-12 HCP, {support}-card support - invites game."
    level = 4 if suit in MAJORS else 5
    return f"{level}{suit}", f"Game raise: 13+ HCP with {support}-card support."


def suggest_new_suit_response(stats):
    hcp, lengths = stats["hcp"], stats["lengths"]
    candidates = [s for s in ("♠", "♥", "♦", "♣") if lengths[s] >= 4]
    candidates.sort(key=lambda s: (-lengths[s], s not in MAJORS))
    if candidates and hcp >= 6:
        suit = candidates[0]
        return f"1{suit}", f"New suit: 6+ HCP, {lengths[suit]}+ cards in {suit}."
    if hcp >= 6:
        return "1NT", "6-10 HCP, no 4-card suit to show at the 1-level."
    return "Pass", "Fewer than 6 HCP: not enough to respond."


def suggest_response_to_opening(stats, partner_bid):
    strain = partner_bid[1:]
    if strain == "NT":
        hcp = stats["hcp"]
        if hcp >= 17:
            return "4NT", "Quantitative slam try (very strong hand opposite 15-17)."
        if hcp >= 10:
            return "3NT", "Game values opposite a 15-17 HCP 1NT: bid game."
        if hcp >= 8:
            return "2NT", "About 11-12 combined HCP feel: invites game."
        return "Pass", "Not enough to move past partner's 1NT."
    if strain in MAJORS:
        raised = suggest_raise(stats, strain)
        if raised:
            return raised
    return suggest_new_suit_response(stats)


def suggest_overcall(stats, opener_bid):
    """Your first call, after an opponent opened (no bid from your side yet)."""
    hcp, lengths, balanced = stats["hcp"], stats["lengths"], stats["balanced"]
    opener_level = int(opener_bid[0])
    opener_strain = opener_bid[1:]

    shortness = lengths.get(opener_strain, 0) if opener_strain != "NT" else 99
    if opener_strain != "NT" and hcp >= 12 and shortness <= 2:
        return "X", (
            f"Takeout double: {hcp} HCP (opening values), only {shortness} card(s) in "
            f"{opener_strain} - forcing, asks partner to bid their best suit (majors first)."
        )

    if opener_strain != "NT" and 15 <= hcp <= 18 and balanced and lengths.get(opener_strain, 0) >= 2:
        level = opener_level
        return f"{level}NT", f"1NT overcall: 15-18 HCP, balanced, likely stopper in {opener_strain}."

    candidates = [s for s in ("♠", "♥", "♦", "♣") if s != opener_strain and lengths[s] >= 5]
    candidates.sort(key=lambda s: -lengths[s])
    if candidates and 8 <= hcp <= 16:
        suit = candidates[0]
        level = opener_level if STRAIN_RANK[suit] > STRAIN_RANK[opener_strain] else opener_level + 1
        return f"{level}{suit}", f"Overcall: {hcp} HCP, {lengths[suit]}-card {suit} suit."

    return "Pass", f"{hcp} HCP: not enough shape or strength to enter the auction over {opener_bid}."


def _legal_min_level(auction, suit):
    """Cheapest legal level for `suit` given the auction so far."""
    last_bid = next((b for _, b in reversed(auction) if b not in ("Pass", "X", "XX")), None)
    if last_bid is None:
        return 1
    last_level, last_strain = int(last_bid[0]), last_bid[1:]
    if STRAIN_RANK[suit] > STRAIN_RANK[last_strain]:
        return last_level
    return last_level + 1


def generic_fallback(stats, auction, my_seat, partner_seat):
    """Always returns a concrete call - used once the auction is more
    complex than the specific patterns above cover (later rounds,
    competitive sequences beyond the first overcall, etc)."""
    hcp, lengths = stats["hcp"], stats["lengths"]

    partner_suit_bids = [b[1:] for s, b in auction if s == partner_seat and b not in ("Pass", "X", "XX")]
    if partner_suit_bids:
        suit = partner_suit_bids[-1]
        if suit != "NT" and lengths.get(suit, 0) >= 3:
            raised = suggest_raise(stats, suit)
            if raised:
                return raised

    if hcp < 6:
        return "Pass", f"{hcp} HCP: too few values to bid on."

    candidates = [s for s in ("♠", "♥", "♦", "♣") if lengths[s] >= 5]
    candidates.sort(key=lambda s: (-lengths[s], s not in MAJORS))
    if candidates:
        suit = candidates[0]
        level = _legal_min_level(auction, suit)
        return f"{level}{suit}", f"{hcp} HCP with a {lengths[suit]}-card {suit} suit: bid it at the cheapest legal level."

    return "Pass", f"{hcp} HCP, no clear suit or fit to introduce: pass for now."


def suggest_bid(hand, auction, my_seat, partner_seat):
    """auction: list of (seat, bid_str) so far. Always returns (bid, explanation)."""
    stats = hand_stats(hand)
    opponents = [s for s in SEATS if s not in (my_seat, partner_seat)]

    if not auction:
        return suggest_opening(stats)

    partner_calls = [b for s, b in auction if s == partner_seat]
    opp_calls = [b for s, b in auction if s in opponents]
    my_calls = [b for s, b in auction if s == my_seat]

    opponents_have_bid = any(b != "Pass" for b in opp_calls)
    partner_has_bid = any(b != "Pass" for b in partner_calls)

    # Case 1: nobody at all has bid yet (all passes so far) -> it's an opening decision.
    if not opponents_have_bid and not partner_has_bid:
        return suggest_opening(stats)

    # Case 2: partner opened, no interference from opponents -> plain response.
    if partner_has_bid and not opponents_have_bid and partner_calls[-1] != "Pass":
        return suggest_response_to_opening(stats, partner_calls[-1])

    # Case 3: it's my first call, and an opponent opened before partner did anything.
    if not my_calls and opponents_have_bid and not partner_has_bid:
        last_opp_bid = next(b for b in reversed(opp_calls) if b != "Pass")
        return suggest_overcall(stats, last_opp_bid)

    # Case 4: partner opened, then an opponent doubled, now my first response.
    if partner_has_bid and not my_calls and auction and auction[-1][1] == "X" \
            and auction[-1][0] in opponents:
        if stats["hcp"] >= 10:
            return "XX", f"{stats['hcp']} HCP: redouble to show extra strength after their double."
        return suggest_response_to_opening(stats, partner_calls[-1])

    # Case 5: partner opened, an opponent overcalled (not doubled), my first response.
    if partner_has_bid and not my_calls and opponents_have_bid:
        bid, why = suggest_response_to_opening(stats, partner_calls[-1])
        if bid not in ("Pass", "X", "XX"):
            level, strain = int(bid[0]), bid[1:]
            min_level = _legal_min_level(auction, strain)
            if min_level > level:
                bid = f"{min_level}{strain}"
                why += " (bumped up to stay legal over their bid.)"
        return bid, why

    # Fallback: later rounds / sequences not covered above - still concrete.
    return generic_fallback(stats, auction, my_seat, partner_seat)


def explain_call(seat, bid, auction_before):
    if bid == "Pass":
        if all(b == "Pass" for _, b in auction_before):
            return "Passing as an early seat: fewer than 12 HCP, no opening shape."
        return "Pass: no extra values or fit to show right now."
    if bid == "X":
        if all(b == "Pass" for _, b in auction_before):
            return "Double (unusual as an opening call)."
        return "Double: shows opening-ish values and shortness in their suit - forcing, partner must bid (often takeout)."
    if bid == "XX":
        return "Redouble: usually shows extra strength after being doubled."

    level = int(bid[0])
    strain = bid[1:]
    is_opening = all(b == "Pass" for _, b in auction_before)
    if is_opening:
        if strain == "NT" and level == 1:
            return "Opening 1NT: 15-17 HCP, balanced."
        if strain == "NT" and level == 2:
            return "Opening 2NT: 20-21 HCP, balanced."
        if bid == "2♣":
            return "Strong artificial opening: 23+ HCP or equivalent playing strength."
        if level >= 2 and bid != "2♣":
            suit_len = {2: 6, 3: 7, 4: 8, 5: 9}.get(level)
            if suit_len:
                return (
                    f"Barrage (preempt): about {suit_len}-card {strain}, 5-10 HCP - "
                    f"crowds the opponents' auction rather than inviting anything."
                )
        if level == 1:
            return f"Opening bid: 12-17 HCP, 5+ cards in {strain} (or longest minor)."
        return f"Opening bid at the {level}-level in {strain}."

    same_seat_prior = [b for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX")]
    if same_seat_prior:
        prior_strain = same_seat_prior[-1][1:]
        if strain == prior_strain:
            return f"Raise in {strain}: extra support and values for that suit."

    # crude overcall/takeout-response heuristic: first call by this seat, after
    # an opponent's opening and no other bid from this partnership yet
    prior_by_partnership = [b for s, b in auction_before if s == seat]
    if not prior_by_partnership and any(b != "Pass" for _, b in auction_before):
        if strain == "NT":
            return f"{level}NT overcall: 15-18 HCP, balanced, stopper in their suit."
        return f"Overcall: roughly 8-16 HCP, a decent {strain} suit (5+ cards)."

    return f"Shows extra values or a new suit ({strain}) - check your notes for the exact range."