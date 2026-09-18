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
PARTNER_OF = {"north": "south", "south": "north", "east": "west", "west": "east"}


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


def suggest_splinter(hand, stats, suit):
    """Double jump-shift response to a major-suit opening: 4+ support, a
    singleton or void (not headed by an ace/king) in another suit, and
    about 13-15 points including distribution. Invites/forces slam."""
    if suit not in MAJORS:
        return None
    lengths = stats["lengths"]
    if lengths[suit] < 4:
        return None
    short_suits = [s for s in ("♠", "♥", "♦", "♣") if s != suit and lengths[s] <= 1]
    for short in short_suits:
        cards_in_short = [r for r, s in hand if s == short]
        if cards_in_short and cards_in_short[0] in ("A", "K"):
            continue
        short_bonus = 5 if lengths[short] == 0 else 3
        total = stats["hcp"] + short_bonus
        if 13 <= total <= 15:
            return f"4{short}", (
                f"Splinter: {lengths[suit]}-card {suit} support with a "
                f"{'void' if lengths[short] == 0 else 'singleton'} in {short} - "
                f"about {total} points including distribution, invites slam."
            )
    return None


def suggest_raise(stats, suit):
    hcp = stats["hcp"]
    support = stats["lengths"][suit]
    if support < 3:
        return None
    if hcp < 6:
        return "Pass", f"0-5 HCP: not enough to respond, even with {support}-card support."

    jump_length_needed = 4 if suit in MAJORS else 5

    if hcp <= 9:
        return f"2{suit}", f"Simple raise: 6-9 HCP, {support}-card support."
    if hcp <= 12:
        if support >= jump_length_needed:
            return f"3{suit}", (
                f"Limit raise (jump): 10-12 HCP, {support}-card support - a jump to the 3-level "
                f"promises {jump_length_needed}+ cards, which you have."
            )
        return f"2{suit}", (
            f"Simple raise: {hcp} HCP is good, but only {support}-card support - a jump raise needs "
            f"{jump_length_needed}+, so raise to 2 instead and let partner know you have more if they ask."
        )
    level = 4 if suit in MAJORS else 5
    return f"{level}{suit}", f"Game raise: 13+ HCP with {support}-card support."


def _min_length_for_new_suit(level):
    """The higher you introduce an unsupported suit for the first time, the
    longer/stronger it needs to be to justify the commitment - a new suit
    forced up to the 3-level or beyond should be a real 6-card suit, not
    just the 4-5 cards that's fine at the 1- or 2-level."""
    return 4 if level <= 2 else 6


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


def suggest_response_to_1nt(stats):
    """Stayman + Jacoby transfers, per the reference: 0-7 no major -> pass;
    0-7 with 5+ major -> transfer then pass; 8+ with a 4-card major (and no
    5+ major) -> Stayman; 8+ with a 5+ major -> transfer, then game/invite
    by point range; 8+ balanced/no major -> the NT ladder."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    long_majors = [s for s in MAJORS if lengths[s] >= 5]
    four_card_majors = [s for s in MAJORS if lengths[s] >= 4]

    if hcp < 8:
        if long_majors:
            suit = max(long_majors, key=lambda s: lengths[s])
            transfer_bid = "2♦" if suit == "♥" else "2♥"
            return transfer_bid, (
                f"Jacoby transfer to {suit}: 0-7 HCP, {lengths[suit]}+ cards - partner must bid "
                f"{suit}, then you pass."
            )
        return "Pass", f"{hcp} HCP, no 5-card major: not enough to respond to 1NT."

    if long_majors:
        suit = max(long_majors, key=lambda s: lengths[s])
        transfer_bid = "2♦" if suit == "♥" else "2♥"
        if lengths[suit] >= 6:
            if hcp >= 10:
                return transfer_bid, f"Transfer to {suit}: {hcp} HCP, 6+ cards - bid game in {suit} next."
            return transfer_bid, f"Transfer to {suit}: {hcp} HCP, 6+ cards - invite with 3{suit} next."
        if hcp >= 10:
            return transfer_bid, f"Transfer to {suit}: {hcp} HCP, 5 cards - bid 3NT next (partner corrects to {suit} with 3-card support)."
        return transfer_bid, f"Transfer to {suit}: {hcp} HCP, 5 cards - bid 2NT next to invite."

    if four_card_majors:
        return "2♣", f"Stayman: {hcp} HCP, a 4-card major - asks partner to bid a 4-card major if they have one."

    if hcp <= 9:
        return "2NT", f"{hcp} HCP, balanced, no major to show: invites game."
    if hcp <= 14:
        return "3NT", f"{hcp} HCP, balanced, no major to show: bid game."
    if hcp <= 16:
        return "4NT", f"{hcp} HCP: quantitative slam try - partner bids 6NT with a maximum (17), else passes."
    if hcp <= 18:
        return "6NT", f"{hcp} HCP: enough for a small slam opposite 15-17."
    return "7NT", f"{hcp} HCP: enough to try for a grand slam opposite 15-17."


def suggest_opener_reply_to_stayman(stats):
    lengths = stats["lengths"]
    if lengths["♥"] >= 4:
        return "2♥", "Stayman reply: shows 4+ hearts."
    if lengths["♠"] >= 4:
        return "2♠", "Stayman reply: shows 4+ spades."
    return "2♦", "Stayman reply: denies a 4-card major."


def suggest_opener_reply_to_transfer(transfer_bid, stats):
    suit = "♥" if transfer_bid == "2♦" else "♠"
    length = stats["lengths"][suit]
    if length >= 4 and stats["hcp"] >= 17:
        level = 3
        return f"{level}{suit}", f"Super-accept: completes the transfer with a jump - 4+ card support and a maximum (17)."
    return f"2{suit}", f"Completes the transfer, showing {suit} for partner (bid even if short in it)."


def count_aces(hand):
    return sum(1 for rank, _ in hand if rank == "A")


def suggest_blackwood_response(hand):
    aces = count_aces(hand)
    bid = {0: "5♣", 1: "5♦", 2: "5♥", 3: "5♠", 4: "5♣"}[aces]
    plural = "s" if aces != 1 else ""
    return bid, f"Blackwood response: {aces} ace{plural}."


def suggest_gerber_response(hand):
    aces = count_aces(hand)
    bid = {0: "4♦", 1: "4♥", 2: "4♠", 3: "4NT", 4: "4♦"}[aces]
    plural = "s" if aces != 1 else ""
    return bid, f"Gerber response: {aces} ace{plural}."


def _is_gerber_context(auction, partner_seat):
    """4C is Gerber (asking for aces) specifically as a jump right after a
    1NT/2NT opening - a natural club bid anywhere else is not Gerber."""
    real_calls = [(s, b) for s, b in auction if b not in ("Pass", "X", "XX")]
    if len(real_calls) < 2:
        return False
    if real_calls[0][1] not in ("1NT", "2NT"):
        return False
    return real_calls[-1] == (partner_seat, "4♣")


def _is_blackwood_context(auction, my_seat, partner_seat):
    """4NT is Blackwood (asking for aces) once a trump fit is agreed - but
    a bare 4NT as the very first response to a 1NT/2NT opening is
    quantitative instead, not Blackwood."""
    real_calls = [(s, b) for s, b in auction if b not in ("Pass", "X", "XX")]
    if len(real_calls) <= 2 and real_calls and real_calls[0][1] in ("1NT", "2NT"):
        return False
    my_suits = {b[1:] for s, b in auction if s == my_seat and b not in ("Pass", "X", "XX") and b[1:] != "NT"}
    partner_suits = {b[1:] for s, b in auction if s == partner_seat and b not in ("Pass", "X", "XX") and b[1:] != "NT"}
    return bool(my_suits & partner_suits)


def suggest_negative_double(stats, opener_suit, overcall_bid):
    """After partner's suit opening and an opponent's overcall: a double
    shows 4+ cards in the unbid major(s), with strength scaling by the
    level of the overcall (6+/8+/10+ HCP for 1/2/3+ level)."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    overcall_suit = overcall_bid[1:]
    unbid_majors = [s for s in MAJORS if s not in (opener_suit, overcall_suit) and lengths[s] >= 4]
    if not unbid_majors:
        return None
    overcall_level = int(overcall_bid[0])
    threshold = {1: 6, 2: 8}.get(overcall_level, 10)
    if hcp >= threshold:
        return "X", (
            f"Negative double: {hcp} HCP, shows 4+ cards in {' and '.join(unbid_majors)} "
            f"(the unbid major{'s' if len(unbid_majors) > 1 else ''})."
        )
    return None


def suggest_response_to_opening(stats, partner_bid, hand=None):
    strain = partner_bid[1:]
    if strain == "NT" and partner_bid[0] == "1":
        return suggest_response_to_1nt(stats)
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
        if hand is not None:
            splinter = suggest_splinter(hand, stats, strain)
            if splinter:
                return splinter
        raised = suggest_raise(stats, strain)
        if raised:
            return raised
    return suggest_new_suit_response(stats)


def suggest_michaels(stats, opener_bid):
    """Direct cuebid of opponent's opened suit: shows 5+/5+ in both majors
    (over a minor) or the other major + an unspecified minor (over a
    major). Most useful 0-10 HCP - two-suited shape matters more than
    high cards here."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    opener_level, opener_strain = int(opener_bid[0]), opener_bid[1:]
    if opener_level != 1 or opener_strain == "NT" or hcp > 11:
        return None
    if opener_strain in MINORS:
        if lengths["♠"] >= 5 and lengths["♥"] >= 5:
            return f"2{opener_strain}", f"Michaels cuebid: {hcp} HCP, 5+/5+ in both majors."
        return None
    other_major = "♥" if opener_strain == "♠" else "♠"
    if lengths[other_major] >= 5:
        best_minor = max(MINORS, key=lambda s: lengths[s])
        if lengths[best_minor] >= 5:
            return f"2{opener_strain}", (
                f"Michaels cuebid: {hcp} HCP, 5+ {other_major} and an unspecified 5+ minor "
                f"(likely {best_minor})."
            )
    return None


def suggest_unusual_2nt(stats, opener_bid):
    """Direct jump to 2NT: shows the two lower-ranking unbid suits, 5+/5+,
    one always a minor. Most useful 0-10 HCP."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    opener_level, opener_strain = int(opener_bid[0]), opener_bid[1:]
    if opener_level != 1 or opener_strain == "NT" or hcp > 11:
        return None
    shown = {
        "♣": ("♦", "♥"), "♦": ("♣", "♥"), "♥": ("♣", "♦"), "♠": ("♣", "♦"),
    }.get(opener_strain)
    if shown and lengths[shown[0]] >= 5 and lengths[shown[1]] >= 5:
        return "2NT", f"Unusual 2NT: {hcp} HCP, 5+/5+ in {shown[0]} and {shown[1]}."
    return None


def suggest_dont(stats):
    """Responding to an opponent's 1NT opening. A one-suited hand (6+)
    doubles (relay - partner bids 2C to ask); a two-suited hand (5-4+)
    bids the cheaper of its two suits."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    six_plus = [s for s in ("♠", "♥", "♦", "♣") if lengths[s] >= 6]
    if six_plus:
        suit = max(six_plus, key=lambda s: lengths[s])
        if suit == "♠":
            return "2♠", f"Natural: 6+ spades, shows this suit directly (stronger shape than Double-then-2S)."
        return "X", f"DONT: single-suited hand, 6+ cards in {suit} - partner bids 2♣ to ask which suit."

    two_suited = [s for s in ("♠", "♥", "♦", "♣") if lengths[s] >= 5]
    if len(two_suited) >= 2:
        two_suited.sort(key=lambda s: -lengths[s])
        a, b = two_suited[0], two_suited[1]
        cheapest = min((a, b), key=lambda s: STRAIN_RANK[s])
        return f"2{cheapest}", f"DONT: two-suited hand ({a} and {b}, 5+ each) - shows {cheapest} and a higher unbid suit."

    return None


def suggest_overcall(stats, opener_bid):
    """Your first call, after an opponent opened (no bid from your side yet)."""
    hcp, lengths, balanced = stats["hcp"], stats["lengths"], stats["balanced"]
    opener_level = int(opener_bid[0])
    opener_strain = opener_bid[1:]

    if opener_strain == "NT" and opener_level == 1:
        dont = suggest_dont(stats)
        if dont:
            return dont

    michaels = suggest_michaels(stats, opener_bid)
    if michaels:
        return michaels
    unusual = suggest_unusual_2nt(stats, opener_bid)
    if unusual:
        return unusual

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


def _controls_shown(auction, seat):
    """Suits this seat has already cue-bid (shown a control in): any suit
    bid at the 4-level or higher that isn't NT - a workable proxy without
    fully tracking cue-bid sequences round by round."""
    shown = set()
    for s, b in auction:
        if s != seat or b in ("Pass", "X", "XX"):
            continue
        level, strain = int(b[0]), b[1:]
        if level >= 4 and strain != "NT":
            shown.add(strain)
    return shown


def suggest_control_cue_bid(hand, auction, my_seat, partner_seat, trump_suit):
    """Cheapest new control to show once a fit is agreed and slam is in
    the picture: aces/voids (1st round) before kings/singletons (2nd
    round), never the trump suit itself, never one already shown."""
    already_shown = _controls_shown(auction, my_seat) | _controls_shown(auction, partner_seat)
    already_shown.discard(trump_suit)

    def control_level(suit):
        cards = [r for r, s in hand if s == suit]
        if not cards:
            return 1
        if "A" in cards:
            return 1
        if len(cards) == 1:
            return 2
        if "K" in cards:
            return 2
        return 0

    candidates = []
    for suit in ("♣", "♦", "♥", "♠"):
        if suit == trump_suit or suit in already_shown:
            continue
        lvl = control_level(suit)
        if lvl > 0:
            candidates.append((suit, lvl))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[1], STRAIN_RANK[c[0]]))
    suit, lvl = candidates[0]
    control_word = "first-round (ace/void)" if lvl == 1 else "second-round (king/singleton)"
    bid_level = _legal_min_level(auction, suit)
    return f"{bid_level}{suit}", (
        f"Control-showing cue-bid: {control_word} control in {suit} - cheapest new control, "
        f"slam try with {trump_suit} agreed."
    )


def generic_fallback(hand, stats, auction, my_seat, partner_seat):
    """Always returns a concrete call - used once the auction is more
    complex than the specific patterns above cover (later rounds,
    competitive sequences, continuing after a fit is found, etc).
    Reasons from everything partner has shown across the WHOLE auction
    (via infer_partner_profile), not just their most recent call, so a
    hand doesn't get "re-evaluated" in isolation once the auction has
    moved past round one."""
    hcp, lengths = stats["hcp"], stats["lengths"]
    p_min, p_max, p_suits = infer_partner_profile(auction, partner_seat)
    combined_min, combined_max = hcp + p_min, hcp + p_max

    last_bid = next((b for _, b in reversed(auction) if b not in ("Pass", "X", "XX")), None)
    last_level = int(last_bid[0]) if last_bid else 0

    partner_suit_bids = [b[1:] for s, b in auction if s == partner_seat and b not in ("Pass", "X", "XX")]
    fit_suit = None
    for suit in reversed(partner_suit_bids):
        if suit != "NT" and lengths.get(suit, 0) >= 3:
            fit_suit = suit
            break

    if fit_suit:
        game_level = 4 if fit_suit in MAJORS else 5
        already_cue_bidding = last_bid is not None and last_level >= game_level and last_bid[1:] != fit_suit
        slam_zone = combined_min >= 30 and last_level < 6

        if slam_zone or already_cue_bidding:
            cue = suggest_control_cue_bid(hand, auction, my_seat, partner_seat, fit_suit)
            if cue:
                return cue
            if already_cue_bidding:
                return (
                    f"{game_level}{fit_suit}" if last_level < game_level else "Pass",
                    f"No new control to show - return to {fit_suit} to discourage a slam try.",
                )

        if combined_min >= 25 and last_level < game_level:
            return (
                f"{game_level}{fit_suit}",
                f"Combined strength looks like game (~{combined_min}-{combined_max} HCP with a "
                f"{fit_suit} fit) - bid it.",
            )
        return (
            "Pass",
            f"You've already shown your hand; combined values (~{combined_min}-{combined_max} HCP) "
            f"don't clearly justify bidding higher than what's already on the table.",
        )

    if hcp < 6:
        return "Pass", f"{hcp} HCP: too few values to bid on."

    candidates = []
    for s in ("♠", "♥", "♦", "♣"):
        length = lengths[s]
        if length < 4:
            continue
        level = _legal_min_level(auction, s)
        if length >= _min_length_for_new_suit(level):
            candidates.append((s, length, level))
    candidates.sort(key=lambda t: (-t[1], t[0] not in MAJORS))
    if candidates:
        suit, length, level = candidates[0]
        return f"{level}{suit}", f"{hcp} HCP with a {length}-card {suit} suit: bid it at the cheapest legal level."

    return "Pass", f"{hcp} HCP: no suit is both legal and long enough to introduce safely at this level."


def call_constraints(seat, bid, auction_before):
    """Structured version of explain_call: returns a dict of what a call
    implies (hcp_min/hcp_max, suit + suit_min_len), or None if it doesn't
    narrow anything reliably. Used to infer partner's likely shape during
    the play phase, by intersecting constraints across all their calls."""
    if bid in ("Pass", "X", "XX"):
        if bid == "Pass" and all(b == "Pass" for _, b in auction_before):
            return {"hcp_max": 11}
        return None

    level, strain = int(bid[0]), bid[1:]
    is_opening = all(b == "Pass" for _, b in auction_before)
    if is_opening:
        if strain == "NT" and level == 1:
            return {"hcp_min": 15, "hcp_max": 17}
        if bid == "2♣":
            return {"hcp_min": 23, "hcp_max": 37}
        if level >= 2 and strain != "NT":
            suit_len = {2: 6, 3: 7, 4: 8, 5: 9}.get(level)
            if suit_len:
                return {"hcp_min": 5, "hcp_max": 10, "suit": strain, "suit_min_len": suit_len}
        if level == 1:
            return {
                "hcp_min": 12, "hcp_max": 17, "suit": strain,
                "suit_min_len": 5 if strain in MAJORS else 3,
            }
        return None

    same_seat_prior = [b for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX")]
    if same_seat_prior:
        prior_strain = same_seat_prior[-1][1:]
        if strain == prior_strain and strain != "NT":
            return {"suit": strain, "suit_min_len": 3}

    partner_seat = PARTNER_OF.get(seat)
    partner_prior_here = [b for s, b in auction_before if s == partner_seat and b not in ("Pass", "X", "XX")]
    if partner_prior_here and partner_prior_here[0][1:] == strain and strain != "NT":
        min_legal = _legal_min_level(auction_before, strain)
        if level > min_legal:
            if level >= (4 if strain in MAJORS else 5):
                return {"hcp_min": 13, "suit": strain, "suit_min_len": 4 if strain in MAJORS else 5}
            return {"hcp_min": 10, "hcp_max": 12, "suit": strain, "suit_min_len": 4 if strain in MAJORS else 5}
        return {"hcp_min": 6, "hcp_max": 9, "suit": strain, "suit_min_len": 3}

    if strain == "NT":
        return {"hcp_min": 6}
    return {"suit": strain, "suit_min_len": 4, "hcp_min": 6}


def infer_partner_profile(auction, partner_seat):
    """Combines every call partner has made so far into one estimate:
    (hcp_min, hcp_max, {suit: minimum known length})."""
    calls = [(s, b) for s, b in auction if s == partner_seat]
    hcp_min, hcp_max = 0, 37
    suit_min = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
    for i, (s, b) in enumerate(calls):
        idx_in_auction = [j for j, (ss, _) in enumerate(auction) if ss == s][i]
        c = call_constraints(s, b, auction[:idx_in_auction])
        if not c:
            continue
        if "hcp_min" in c:
            hcp_min = max(hcp_min, c["hcp_min"])
        if "hcp_max" in c:
            hcp_max = min(hcp_max, c["hcp_max"])
        if "suit" in c and c["suit"] in suit_min:
            suit_min[c["suit"]] = max(suit_min[c["suit"]], c.get("suit_min_len", 0))
    return hcp_min, hcp_max, suit_min


def _make_legal(auction, bid, why):
    """Final safety net: never return a call that's actually illegal given
    the whole auction so far. A gap of one level (e.g. an opponent's
    overcall ate a rung of bidding space) gets bumped up in the same suit,
    since that's still a sensible bid for the hand. A bigger gap (the
    auction has moved well past what this simple rule was reasoning
    about - like a partner who's since jumped to 5H) means the suggestion
    is stale, not just squeezed - pass instead of guessing something wild."""
    if bid in ("Pass", "X", "XX"):
        return bid, why
    level, strain = int(bid[0]), bid[1:]
    min_level = _legal_min_level(auction, strain)
    if min_level > level:
        if min_level - level <= 1:
            return f"{min_level}{strain}", why + " (bumped up one level to stay legal.)"
        return "Pass", (
            f"Your natural bid here would have been {bid}, but the auction has moved well past "
            f"that ({min_level}{strain} or higher is now needed) - pass rather than overbid."
        )
    return bid, why


def suggest_bid(hand, auction, my_seat, partner_seat):
    """auction: list of (seat, bid_str) so far. Always returns (bid, explanation)."""
    bid, why = _suggest_bid_core(hand, auction, my_seat, partner_seat)
    return _make_legal(auction, bid, why)


def _suggest_bid_core(hand, auction, my_seat, partner_seat):
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

    # Case 1b: I opened 1NT, and partner just replied with Stayman or a
    # transfer - I need to complete the convention, not treat this as a
    # fresh opening decision.
    my_last_own_bid = next((b for b in reversed(my_calls) if b != "Pass"), None)
    if my_last_own_bid == "1NT" and partner_calls and partner_calls[-1] != "Pass":
        p_last = partner_calls[-1]
        if p_last == "2♣":
            return suggest_opener_reply_to_stayman(stats)
        if p_last in ("2♦", "2♥"):
            return suggest_opener_reply_to_transfer(p_last, stats)

    # Case 1c: partner just asked Blackwood (4NT with an agreed trump fit).
    if partner_calls and partner_calls[-1] == "4NT" and _is_blackwood_context(auction, my_seat, partner_seat):
        return suggest_blackwood_response(hand)

    # Case 1d: partner just asked Gerber (4C right after a 1NT/2NT opening).
    if _is_gerber_context(auction, partner_seat):
        return suggest_gerber_response(hand)

    # Case 2: partner opened, no interference from opponents, and this is
    # genuinely my first call -> plain response. (If I've already bid
    # before, this is MY rebid after partner's raise, not a response to
    # an opening - that belongs in the fallback below, which knows how
    # to reason about a fit already found, including cue-bidding.)
    if partner_has_bid and not opponents_have_bid and partner_calls[-1] != "Pass" and not my_calls:
        return suggest_response_to_opening(stats, partner_calls[-1], hand)

    # Case 3: it's my first call, and an opponent opened before partner did anything.
    if not my_calls and opponents_have_bid and not partner_has_bid:
        last_opp_bid = next(b for b in reversed(opp_calls) if b != "Pass")
        return suggest_overcall(stats, last_opp_bid)

    # Case 4: partner opened, then an opponent doubled, now my first response.
    if partner_has_bid and not my_calls and auction and auction[-1][1] == "X" \
            and auction[-1][0] in opponents:
        if stats["hcp"] >= 10:
            return "XX", f"{stats['hcp']} HCP: redouble to show extra strength after their double."
        return suggest_response_to_opening(stats, partner_calls[-1], hand)

    # Case 5: partner opened, an opponent overcalled (not doubled), my first response.
    if partner_has_bid and not my_calls and opponents_have_bid:
        opener_bid = next(b for b in partner_calls if b != "Pass")
        last_opp_bid = next(b for b in reversed(opp_calls) if b != "Pass")
        if opener_bid[1:] != "NT" and last_opp_bid[1:] != "NT":
            neg_dbl = suggest_negative_double(stats, opener_bid[1:], last_opp_bid)
            if neg_dbl:
                return neg_dbl
        return suggest_response_to_opening(stats, partner_calls[-1], hand)

    # Fallback: later rounds / sequences not covered above - still concrete,
    # and reasons from everything partner has shown across the whole auction.
    return generic_fallback(hand, stats, auction, my_seat, partner_seat)


def explain_call(seat, bid, auction_before):
    partner_seat = PARTNER_OF[seat]

    if bid == "X":
        partner_prior_all = [b for s, b in auction_before if s == partner_seat and b not in ("Pass", "X", "XX")]
        if partner_prior_all:
            opener_bid = partner_prior_all[0]
            opp_calls_before = [
                b for s, b in auction_before if s not in (seat, partner_seat) and b not in ("Pass", "X", "XX")
            ]
            if opp_calls_before and opener_bid[1:] != "NT":
                return "Negative double: shows length in the unbid major(s), asks partner to pick one."
        own_prior_all_x = [b for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX")]
        opp_real_calls_x = [
            (s, b) for s, b in auction_before if s not in (seat, partner_seat) and b not in ("Pass", "X", "XX")
        ]
        if not own_prior_all_x and not partner_prior_all and opp_real_calls_x and opp_real_calls_x[0][1] == "1NT":
            return "DONT: single-suited hand (6+ cards) - partner bids 2♣ to ask which suit."
        if all(b == "Pass" for _, b in auction_before):
            return "Double (unusual as an opening call)."
        return "Double: shows opening-ish values and shortness in their suit - forcing, partner must bid (often takeout)."
    if bid == "Pass":
        if all(b == "Pass" for _, b in auction_before):
            return "Passing as an early seat: fewer than 12 HCP, no opening shape."
        return "Pass: no extra values or fit to show right now."
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

    partner_prior_all = [b for s, b in auction_before if s == partner_seat and b not in ("Pass", "X", "XX")]
    own_prior_all = [b for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX")]

    # Stayman / Jacoby transfer, as a response to partner's 1NT opening.
    if partner_prior_all == ["1NT"] and not own_prior_all:
        if bid == "2♣":
            return "Stayman: 8+ HCP, asks partner to bid a 4-card major if they have one."
        if bid in ("2♦", "2♥"):
            shown_suit = "♥" if bid == "2♦" else "♠"
            return f"Jacoby transfer: shows 5+ cards in {shown_suit}, asks partner to bid it."

    # Opener completing a Stayman/transfer sequence after their own 1NT opening.
    if own_prior_all == ["1NT"] and len(partner_prior_all) == 1:
        p = partner_prior_all[0]
        if p == "2♣" and strain in MAJORS:
            return f"Stayman reply: shows {'4+' if strain=='♥' else '4+'} cards in {strain}."
        if p == "2♣" and bid == "2♦":
            return "Stayman reply: denies a 4-card major."
        if p in ("2♦", "2♥"):
            expected = "♥" if p == "2♦" else "♠"
            if strain == expected and level == 3:
                return f"Super-accept: completes the transfer with a jump - 4+ card support and a maximum hand."
            if strain == expected:
                return f"Completes the transfer, showing {expected} for partner."

    # Splinter: double jump-shift response to partner's major opening.
    if partner_prior_all and len(partner_prior_all) == 1 and not own_prior_all:
        p_level, p_strain = int(partner_prior_all[0][0]), partner_prior_all[0][1:]
        if p_level == 1 and p_strain in MAJORS and strain != p_strain and strain != "NT":
            min_legal = _legal_min_level(auction_before, strain)
            if level >= min_legal + 2:
                return (
                    f"Splinter: shows {p_strain} support (4+) with a singleton or void in {strain} - "
                    f"invites/forces slam."
                )

    # Michaels cuebid / Unusual 2NT / DONT - first call after an opponent opened.
    prior_by_this_side = [b for s, b in auction_before if s in (seat, partner_seat)]
    opp_real_calls = [(s, b) for s, b in auction_before if s not in (seat, partner_seat) and b not in ("Pass", "X", "XX")]
    if not prior_by_this_side and opp_real_calls:
        opener_bid = opp_real_calls[0][1]
        opener_level, opener_strain = int(opener_bid[0]), opener_bid[1:]
        if opener_strain == "NT" and opener_level == 1:
            if bid == "2♠":
                return "DONT: natural, 6+ spades."
            if level == 2 and strain != "NT":
                return f"DONT: two-suited hand, shows {strain} and a higher unbid suit."
        elif opener_level == 1 and level == opener_level + 1 and strain == opener_strain and opener_strain != "NT":
            return f"Michaels cuebid: shows both majors (if {opener_strain} is a minor) or the other major + an unspecified minor."
        elif opener_level == 1 and bid == "2NT":
            return "Unusual 2NT: shows the two lower-ranking unbid suits, 5+/5+."

    # Blackwood ask and ace-count responses.
    if bid == "4NT":
        real_calls = [(s, b) for s, b in auction_before if b not in ("Pass", "X", "XX")]
        my_suits = {b[1:] for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX") and b[1:] != "NT"}
        partner_suits = {b[1:] for s, b in auction_before if s == partner_seat and b not in ("Pass", "X", "XX") and b[1:] != "NT"}
        if my_suits & partner_suits:
            return "Blackwood: asks partner how many aces they hold."
    if partner_prior_all and partner_prior_all[-1] == "4NT" and level == 5 and strain != "NT":
        ace_map = {"♣": "0 or 4", "♦": "1", "♥": "2", "♠": "3"}
        if strain in ace_map:
            return f"Blackwood response: shows {ace_map[strain]} ace(s)."

    # Gerber ask and ace-count responses.
    if bid == "4♣":
        real_calls = [(s, b) for s, b in auction_before if b not in ("Pass", "X", "XX")]
        if len(real_calls) == 1 and real_calls[0][0] == partner_seat and real_calls[0][1] in ("1NT", "2NT"):
            return "Gerber: asks partner how many aces they hold."
    if partner_prior_all and partner_prior_all[-1] == "4♣" and level == 4 and strain != "♣":
        real_calls = [(s, b) for s, b in auction_before if b not in ("Pass", "X", "XX")]
        if len(real_calls) >= 2 and real_calls[0][1] in ("1NT", "2NT"):
            ace_map = {"♦": "0 or 4", "♥": "1", "♠": "2", "NT": "3"}
            if strain in ace_map:
                return f"Gerber response: shows {ace_map[strain]} ace(s)."

    same_seat_prior = [b for s, b in auction_before if s == seat and b not in ("Pass", "X", "XX")]
    partner_prior = [b for s, b in auction_before if s == partner_seat and b not in ("Pass", "X", "XX")]

    if same_seat_prior:
        # This seat has bid before - this is a REBID, not a first-time call.
        # Check against everything they've shown so far, not just their most
        # recent call, so returning to an earlier suit (e.g. 1H-3S-4H) is
        # recognized as confirming that suit, not treated as a brand-new one.
        prior_strains = [b[1:] for b in same_seat_prior]
        is_jump = level > _legal_min_level(auction_before, strain)

        if strain in prior_strains:
            if is_jump:
                return (
                    f"Jump rebid in {strain}: extra length and extra strength (16-18+) - "
                    f"invites game, more than a minimum opener would show."
                )
            return (
                f"Rebid/return to {strain}: confirms that suit (often extra length there), "
                f"around a fairly minimum hand (12-14) unless extra strength was already shown."
            )
        if strain == "NT":
            level_range = {1: "12-14", 2: "18-19"}.get(level, "a balanced hand")
            return f"Rebid in NT: balanced shape, about {level_range} HCP - describes points now that a suit's been shown."
        if is_jump:
            return (
                f"Jump shift into {strain}: a strong second suit, well beyond minimum values - "
                f"forcing, a big hand."
            )
        return f"Second suit shown ({strain}): natural, gives partner more shape information."

    if partner_prior:
        # Raising or supporting whatever partner has shown so far.
        partner_last_strain = partner_prior[-1][1:]
        if strain == partner_last_strain:
            return f"Raise of partner's {strain}: support and extra values for that suit."

    # crude overcall/takeout-response heuristic: first call by this seat, after
    # an opponent's opening and no other bid from this partnership yet
    prior_by_partnership = [b for s, b in auction_before if s == seat]
    if not prior_by_partnership and any(b != "Pass" for _, b in auction_before):
        if strain == "NT":
            return f"{level}NT overcall: 15-18 HCP, balanced, stopper in their suit."
        return f"Overcall: roughly 8-16 HCP, a decent {strain} suit (5+ cards)."

    return f"Shows extra values or a new suit ({strain}) - check your notes for the exact range."