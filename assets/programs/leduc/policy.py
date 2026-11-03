"""Mixed, rank-based rules for two-round limit poker.

The same rules cover different deck sizes, bet sizes and raise caps.  They use
only the current information set.  Hand strength is a rank in [0, 1]: preflop
the hole rank, postflop the rank among the unpaired hands (`nonpair`).  Within
each method the rules are grouped by betting history; their order matters
because most of them clamp the probability to [0, 1].
"""


# Knobs found by group finite differences (see NOTES.md).
K_STAB = 0.15     # stab bluff with weak unpaired hands when the preflop raiser checks
K_HICHK = 0.10    # check strong unpaired hands first to act after a raised preflop
K_CCDEF = 0.10    # call a bet with middle unpaired hands after a checked preflop
K_RRMID = 0.10    # fold middle ranks more against a reraise of our open
K_CRLO = 0.10     # fold the lowest ranks more after check-raise preflop (4-5 ranks)
K_MECR = 0.10     # as preflop raiser who checked, fold middle unpaired to a bet (4-5 ranks)
K_LO3B = 0.04     # preflop reraise bluff with the lowest rank against an open
K_OPPLEAD = 0.15  # fold middle unpaired when the preflop raiser leads a mid/high board
K_MECRHI = 0.10   # as preflop raiser who checked, fold top unpaired to a bet on a middle board
K_CRRHI = 0.15    # facing the preflop raiser's check-raise, fold top unpaired on a middle board
K_MEHIB = 0.10    # as preflop raiser checked to on a high board, bet unpaired hands more


def clamp(value):
    return max(0.0, min(1.0, value))


def hump(x):
    """Weight that peaks at 1 for x = 0.5 and vanishes at 0 and 1."""
    return 4 * x * (1 - x)


def defend_actions(legal, defend, raise_probability):
    """Split a defending range into calls and raises, folding the remainder."""
    raise_probability = min(raise_probability, defend) if 'raise' in legal else 0.0
    actions = {'fold': 1.0 - defend, 'call': defend - raise_probability}
    if 'raise' in legal:
        actions['raise'] = raise_probability
    return actions


def bet_or_check(raise_probability):
    return {'call': 1 - raise_probability, 'raise': raise_probability}


class Policy:
    def __init__(self, spec):
        game = spec['game']
        self.ranks = game['ranks']
        self.rank_count = len(self.ranks)
        self.suit_count = len(game['suits'])
        ante = game['ante']
        preflop_bet, second_bet = game['raise_sizes']
        self.open_size = preflop_bet / ante             # preflop bet in antes
        self.cheap_open = self.open_size <= 1
        self.expensive = self.open_size >= 4
        self.can_reraise = game['max_raises'][0] > 1    # preflop
        self.multi_raise = game['max_raises'][1] > 1    # postflop
        self.small_second_bet = second_bet <= 2 * ante
        self.low_implied_odds = second_bet <= preflop_bet
        # Larger second-round bets require a stronger unpaired calling hand.
        self.showdown_exponent = 1 + min(1.0, max(0.0, (second_bet / (2 * ante) - 1) * 0.5))

    def reset(self):
        pass

    def act(self, obs, info):
        legal = obs['legal']
        rank = self.ranks.index(obs['hole'][:-1])
        history = obs['betting'][obs['round']]
        facing_bet = obs['to_call'] > 0

        if obs['round'] == 0:
            strength = rank / (self.rank_count - 1)
            if not facing_bet:
                return self.preflop_open(legal, history, strength)
            return self.preflop_defend(obs, legal, history, rank, strength)

        if 'raise' not in legal and not facing_bet:
            return 'call'
        board = self.ranks.index(obs['board'][0][:-1])
        board_strength = board / (self.rank_count - 1)
        preflop = obs['betting'][0]
        raiser = 'r' in preflop and preflop.rfind('r') % 2 == obs['seat']
        if rank == board:
            return self.play_pair(legal, history, preflop, board_strength)
        # Rank among the non-pair hands, from weakest (0) to strongest (1).
        nonpair = (rank - (rank > board)) / max(1, self.rank_count - 2)
        if not facing_bet:
            return self.unpaired_open(history, preflop, raiser, board_strength, nonpair)
        return self.unpaired_defend(obs, legal, history, preflop, raiser,
                                    board_strength, nonpair)

    # ----------------------------------------------------------------- preflop

    def preflop_open(self, legal, history, s):
        if 'raise' not in legal:
            return 'call'
        n = self.rank_count
        exponent = min(2.0, 0.5 + 0.75 * (n - 3))
        p = (0.3 if n == 3 else 0.25) + (0.45 if n == 3 else 0.50) * s ** exponent

        if not history:  # First to act.
            if n == 3:
                if self.can_reraise:
                    if self.expensive:
                        # Costly openings favor fewer, stronger hands.
                        p = 0.10 + 0.50 * s ** 3
                    else:
                        if self.low_implied_odds:
                            p -= 0.10 * (1 - s) ** 4
                        p -= (0.10 if self.low_implied_odds else 0.20) * hump(s)
                if self.suit_count > 2:
                    p -= 0.10 * s ** 4
            else:
                if n > 4 and self.cheap_open:
                    p -= 0.10
                if self.can_reraise:
                    if not self.cheap_open:
                        p -= 0.2 * hump(s)
                    if n > 4 and self.low_implied_odds:
                        p -= 0.30 * 4 * s ** 3 * (1 - s)
                    if n > 4 and self.expensive:
                        p *= 0.5
                    if self.expensive:
                        p -= 0.10 * hump(s)
                    if self.suit_count > 2 and self.open_size <= 2:
                        p -= 0.10 * s ** 4
                if self.suit_count > 2 and self.cheap_open:
                    p *= 1 - 0.10 * hump(s)
                if self.low_implied_odds:
                    p *= 1 - 0.20 * (1 - s) ** 4
            if self.suit_count == 2 and self.can_reraise:
                p *= 1 - 0.10 * (1 - s) ** 4

        elif not self.can_reraise:  # Opponent checked; a bet cannot be reraised.
            p = min(1.0, 0.3 + 0.9 * p)
        else:  # Opponent checked.
            if self.low_implied_odds:
                # Bet a more polarized range when later bets offer less upside.
                weak_bet = 0.10 if n == 3 else 0.15
                strong_bet = 0.15 if n == 3 else 0.20
                p += weak_bet * (1 - s) ** 4 + strong_bet * s ** 4 - weak_bet * hump(s)
            else:
                p += 0.20 * s ** 4
                if n > 3 and self.cheap_open:
                    p += (0.25 if self.suit_count > 2 else 0.15) * (1 - s) ** 4
            if n == 3:
                if self.expensive:
                    p -= (0.30 if self.suit_count == 2 else 0.10) * hump(s)
                elif not self.cheap_open and not self.low_implied_odds:
                    p -= 0.15 * hump(s)
            if n > 4 and self.expensive:
                p -= 0.4 * 4 * s ** 2 * (1 - s)
            if n > 3 and self.suit_count > 2:
                p += 0.10 * s ** 4
        return bet_or_check(clamp(p))

    def preflop_defend(self, obs, legal, history, rank, s):
        n = self.rank_count
        raises = history.count('r')
        # A smoothed price index: the reported pot already includes the
        # outstanding call.  Smaller values represent cheaper calls.
        price = obs['to_call'] / (obs['pot'] + obs['to_call'])
        base = 0.25 if n == 3 or self.cheap_open else 0.15
        if n == 3 and self.small_second_bet:
            rank_weight = 1.3
        elif n > 3 and self.open_size >= 2 and self.can_reraise:
            rank_weight = 0.85
        else:
            rank_weight = 1.05
        defend = clamp(base + rank_weight * s + (0.33 - price))

        if raises == 1:
            if n > 4 and not self.cheap_open and self.can_reraise:
                # Middle ranks have less equity against costly, reraisable opens.
                defend = clamp(defend - 0.05 * hump(s))
            if self.cheap_open:
                defend = max(defend, 0.2, 0.8 - 0.3 * (n - 3))
            if history == 'r':
                # Weak hands retain value from drawing to a pair.
                pair_draw = (self.suit_count - 1) / (n * self.suit_count - 2)
                if self.cheap_open and pair_draw >= 0.2:
                    defend = min(1.0, defend + 0.25 * (1 - s))
                if n == 3 or not self.low_implied_odds:
                    defend = clamp(defend + (0.25 if n == 3 else 0.15) * (1 - s) ** 3)
            if n > 3 and self.low_implied_odds and not self.cheap_open:
                # Less upside favors stronger middle ranks over weaker ones.
                defend = clamp(defend - 0.2 * (1 - s) ** 2)
                defend = clamp(defend + 1.2 * (s - 0.5) * hump(s))
            if history == 'cr':
                # A raise after our check tends to select a stronger range.
                if n == 3:
                    if self.can_reraise:
                        if self.cheap_open:
                            defend = clamp(defend - 0.20 * (1 - s) ** 2)
                        if self.suit_count > 2 and self.open_size <= 2:
                            defend = clamp(defend + 0.10 * (1 - s) ** 4)
                        if self.expensive:
                            defend = clamp(defend - 0.10 * hump(s))
                else:
                    if self.cheap_open:
                        defend = clamp(defend - 0.25 * (1 - s) ** 2)
                    weak_penalty = K_CRLO + (0.0 if self.small_second_bet else 0.30)
                    defend = clamp(defend - weak_penalty * (1 - s) ** 4)
                if self.expensive and self.can_reraise:
                    defend *= 1 - 0.20 * hump(s)
        else:
            # Once committed, protect the money already in the pot.
            defend = max(defend, 0.6, 1.0 - 0.15 * (n - 3))
            if n > 4 and not self.cheap_open:
                defend = clamp(defend - 0.5 * (1 - s) ** 2)
            if history == 'rr':
                # Give up some middle ranks when our opening raise is reraised.
                rr_penalty = K_RRMID + (0.05 if self.suit_count <= 2 else 0.0)
                defend = clamp(defend - rr_penalty * hump(s))

        if n == 3 and not self.can_reraise:
            # With no further raises, marginal hands can realize their draw.
            if not self.cheap_open:
                defend = clamp(defend + 0.10)
            if history == 'r':
                defend = clamp(defend + 0.10 * (1 - defend) * (1 - s) ** 2)
        if n > 4 and self.expensive and self.can_reraise:
            # Weak hands have less value when entering an expensive pot.
            defend = clamp(defend - 0.95 * (1 - s))

        # Reraise top ranks more often when larger preflop bets make
        # calling ranges narrower; keep more calls in small, cheap games.
        raise_rate = 0.6 if n > 3 and self.suit_count > 2 else 0.4
        if n == 3 and self.small_second_bet:
            raise_rate -= 0.2
        if n > 3 and self.open_size >= 2:
            raise_rate += 0.2
        exponent = 3 if raises == 1 and n > 3 and self.cheap_open else 5
        actions = defend_actions(legal, defend, raise_rate * s ** exponent)
        if history == 'r' and rank == 0 and 'raise' in legal:
            # Reraise the lowest rank as a bluff against an opening raise,
            # taking it from folds; it balances the value reraises.
            bluff = min(actions['fold'], K_LO3B)
            actions['fold'] -= bluff
            actions['raise'] += bluff
        return actions

    # ---------------------------------------------------------------- postflop

    def play_pair(self, legal, history, preflop, board_strength):
        if 'raise' not in legal:
            return 'call'
        if history:  # Facing a bet, or checked to: always raise.
            return 'raise'
        n = self.rank_count
        if n > 3 and preflop != 'rc':
            p = 0.6 if self.small_second_bet else 0.3  # slow play
        else:
            p = 0.92
        if preflop == 'crc' and self.multi_raise:
            if n > 3:
                # Protect checks on middle boards after calling a raise.
                p -= (0.30 if self.small_second_bet else 0.15) * hump(board_strength)
            elif not self.small_second_bet:
                p -= 0.25 * board_strength ** 3
        elif preflop == 'cc':
            if n > 4 and self.suit_count > 2 and self.small_second_bet:
                p = 0.85
            elif n == 4 and self.small_second_bet:
                p += 0.25 * board_strength ** 4
            elif n == 3:
                # Protect checks more often on low boards in small decks.
                p = 0.9 * board_strength
        if self.suit_count > 2 and not self.small_second_bet and not self.expensive:
            p *= 0.90
        return bet_or_check(p)

    def unpaired_open(self, history, preflop, raiser, board_strength, x):
        """Bet or check an unpaired hand of strength x when not facing a bet."""
        n = self.rank_count
        bs = board_strength
        small = self.small_second_bet
        if preflop == 'cc' and not history and n == 3:
            # Balance the pair checks with fewer bets on low boards.
            return bet_or_check(min(1.0, 2 * bs) * (
                0.1 + 0.3 * bs * x + 0.25 * (1 - bs) * (1 - x)
                + (0.10 if small else 0.0) * bs * (1 - x)))

        base = 0.20 if small and (n > 3 or self.suit_count > 2) else 0.12
        # A strong unpaired hand can bet for value after a check, but
        # first to act it also helps protect the checking range.
        if not self.multi_raise:
            value_rate = (0.47 if n == 3 and not small
                          else (0.15 if self.suit_count > 2 else 0.33))
        else:
            value_rate = (0.15 if n > 4 else 0.10) if history == 'c' else 0.0
        p = base + value_rate * x ** 3
        if history == 'c':
            if n > 3:
                p += (0.15 if self.suit_count > 2 and not self.multi_raise else 0.10) * (1 - x) ** 3
                if self.multi_raise:
                    p += 0.20 * x ** 3
                if preflop == 'crc' and small and self.low_implied_odds:
                    # Keep some weak hands for checking after the caller checks.
                    p -= 0.20 * (1 - x) ** 3
            elif preflop == 'cc' and self.suit_count > 2 and small:
                # Balance pair bets with weak hands after a low board is checked.
                p += 0.20 * (1 - bs) * (1 - x) ** 3
            if preflop == 'rc' and self.multi_raise:
                # A preflop raiser who checks the board can be challenged
                # for value, particularly when we block the higher ranks.
                p += 0.30 * (1 - bs) * x ** 3
        if self.multi_raise:
            # Intermediate hands are useful checks against a raise.
            p = max(0.0, p - 0.16 * hump(x))
        if raiser:
            if n == 3:
                bluff = (0.23 if self.low_implied_odds else 0.33) if self.multi_raise else 0.05
            else:
                # One-bet rounds have less room to balance later raises.
                bluff = 0.30 if self.multi_raise else 0.20
            p += bluff * (1 - x) ** 3

        if history == 'c':
            if 'r' in preflop and not raiser and not small and n > 3:
                # The preflop raiser checked the board: stab with the
                # weakest unpaired hands, which cannot win a showdown.
                p = clamp(p + K_STAB * (1 - x) ** 4)
            if raiser and self.multi_raise and (n == 3 or not self.low_implied_odds):
                # Checked to the preflop raiser on a high board: the board hits
                # the raiser's range, so bet more unpaired hands.
                p = clamp(p + K_MEHIB * bs ** 2)
        else:
            p = self.lead_adjustments(p, preflop, raiser, bs, x)
        if preflop.count('r') > 1 and n > 3 and small and self.low_implied_odds:
            # Large preflop pots give small bluffs less fold leverage.
            p = clamp(p - 0.08 * (1 - x) ** 3)
        if not history and n > 3 and self.suit_count == 2:
            # With few copies of each rank, keep more unpaired hands in checks.
            p *= 0.90
        return bet_or_check(p)

    def lead_adjustments(self, p, preflop, raiser, bs, x):
        """First to act postflop (after a raised preflop or 4-5 rank 'cc')."""
        n = self.rank_count
        small = self.small_second_bet
        if preflop == 'rc':
            # A cheap opening and fewer copies of each rank make a
            # continuation bluff more likely to face an unpaired hand.
            pair_draw = (self.suit_count - 1) / (n * self.suit_count - 2)
            if n > 3 and self.cheap_open and pair_draw <= 1 / 6:
                p = clamp(p + 0.05 * (1 - x) ** 3)
            if n > 3 and self.multi_raise and not small:
                # Strong unpaired hands can value bet a low board.
                p += (0.20 if self.cheap_open else 0.30) * x ** 3 * (1 - bs) ** 2
            if n == 3 or self.cheap_open:
                # A high board favors the preflop raiser's continuation bluff;
                # on a low board a weak hand has less reason to bet.
                p = clamp(p + 0.15 * (2 * bs - 1) * (1 - x) ** 3)
            if n == 3 and self.multi_raise:
                # Keep some non-pairs for checking on the middle board.
                p = clamp(p - 0.05 * hump(bs))
        elif preflop == 'cc' and small:
            if n > 4 and self.suit_count > 2:
                # Balance pair bets with some polarized non-pair bets.
                p += 0.15 * (x ** 3 + (1 - x) ** 3)
            if self.suit_count <= 2:
                # With a small bet, keep more weak hands for checking.
                p = clamp(p - 0.08 * (1 - x) ** 3)
        if 'r' in preflop:
            if not raiser or n == 3:
                # Check the best unpaired hands more to protect the checking
                # range.  As the preflop raiser this only pays in small decks,
                # where the top unpaired hand is the top rank.
                high_check = K_HICHK + (0.05 if small else 0.0)
                p = clamp(p - high_check * x ** 4)
            if raiser and n > 3 and self.low_implied_odds:
                # Value bet the strongest unpaired hands after raising preflop.
                p = clamp(p + 0.15 * x ** 4)
        if preflop == 'crc':
            if n > 3:
                # The preflop caller keeps more unpaired hands in checks,
                # with some balanced bets on intermediate boards.
                p *= 0.70
                if not small and self.multi_raise and not self.expensive:
                    p += 0.08 * hump(bs)
            elif not small and (self.multi_raise or self.expensive):
                p += (0.10 if self.expensive else 0.20) * hump(bs)
            elif small and not self.low_implied_odds and self.multi_raise:
                p += 0.10 * hump(bs)
        if n > 3 and preflop == 'crc' and small and self.low_implied_odds:
            # A small later bet into the preflop pot has less fold leverage.
            p = clamp(p - 0.05 * (1 - x) ** 3)
        return p

    def unpaired_defend(self, obs, legal, history, preflop, raiser, board_strength, x):
        """Fold, call or raise an unpaired hand of strength x facing a bet."""
        n = self.rank_count
        bs = board_strength
        small = self.small_second_bet
        raises = history.count('r')
        price = obs['to_call'] / (obs['pot'] + obs['to_call'])
        base = -0.04 if small else -0.10
        if n == 3 and self.suit_count == 2:
            base -= 0.06
        if n == 3 and self.expensive:
            # An expensive preflop pot tends to have stronger ranges.
            base -= 0.05
        if n > 3 and not small and self.multi_raise and self.open_size <= 2:
            # Defend a little more often against repeated large bets.
            base += 0.05
        rank_weight = max(0.65, min(0.91, 0.91 - 7.2 * (price - 0.25)))
        defend = clamp(base + rank_weight * x ** self.showdown_exponent
                       + (1.3 if n > 3 else 0.8) * (0.25 - price) - 0.05 * max(0, raises - 1))

        # In a small deck, distinguish a bet into the player from a bet after
        # the player checked; a reraise is a still stronger signal.  Larger
        # later bets make repeated raises more costly to call.
        small_deck_signal = n == 3 and (not small or self.suit_count == 2)
        if raises == 1:
            if small_deck_signal:
                defend = clamp(defend + (0.1 if history == 'cr' else -0.1) * x)
        elif n > 3 and not self.low_implied_odds:
            defend = clamp(defend - 0.10 * (raises - 1))
        elif small_deck_signal:
            defend = clamp(defend - 0.20 * (raises - 1))

        if history == 'r':
            if preflop == 'rc' and n > 4 and small and not self.low_implied_odds:
                # Prefer stronger marginal hands when facing the preflop raiser.
                defend = clamp(defend + 0.5 * (x - 0.5) * hump(x))
            if n > 3 and self.suit_count == 2 and 'r' in preflop and not raiser:
                # The preflop raiser leads into a middle or high board:
                # middle unpaired hands are dominated bluff-catchers.
                defend = clamp(defend - K_OPPLEAD * bs * hump(x))
            if preflop == 'cc' and n > 3 and not small:
                # A first-position bet after a checked preflop comes from a
                # wide range: middle unpaired hands can call it more often.
                call_bonus = K_CCDEF + (0.0 if self.multi_raise else 0.10)
                defend = clamp(defend + call_bonus * hump(x))
        elif history == 'cr':
            if preflop == 'rc' and n == 3 and not self.low_implied_odds and self.multi_raise:
                defend = clamp(defend - 0.15 * x ** 2)
            if preflop == 'cc':
                if n == 3:
                    # After two checks, a bet into the low board is more pair-heavy.
                    board_defense = 0.75 if self.expensive else 0.6
                    defend = clamp(defend - board_defense * (1 - bs) * x ** 2)
                elif small:
                    defend = clamp(defend + 0.2 * (n - 3) * x ** 2)
                    # Tighten strong non-pair calls on checked middle boards.
                    defend = clamp(defend - 0.15 * hump(bs) * x ** 2)
            if raiser:
                if n > 3:
                    # As the preflop raiser we checked; a bet into us is strong.
                    defend = clamp(defend - K_MECR * hump(x))
                else:
                    # Our check shows weakness; on a middle board the bet often
                    # holds a pair that beats our best unpaired hands.
                    defend = clamp(defend - K_MECRHI * hump(bs) * x ** 2)
        elif history == 'crr' and 'r' in preflop and not raiser and n * self.suit_count <= 9:
            # A check-raise from the preflop raiser on a middle board is
            # pair-heavy; our best unpaired hands were only betting for value.
            defend = clamp(defend - K_CRRHI * hump(bs) * x ** 2)

        if preflop == 'cc':
            # An opponent who checked preflop is more likely to pair a low board.
            board_weight = 0.3 if n == 3 and small else 0.2
            if n > 3 and small and self.low_implied_odds:
                # Costly preflop openings leave a broader checking range.
                board_weight -= 0.10
            defend = clamp(defend + board_weight * (2 * bs - 1) * x ** 2)
            if history == 'r' and small:
                # Strong non-pairs can call a small first bet on a low board.
                call_bonus = 0.15 if n == 3 else 0.20
                defend = clamp(defend + call_bonus * (1 - bs) * x ** 2)
        else:
            # Preflop raises shift ranges toward higher cards; size and
            # position determine how much the board changes calling value.
            board_weight = 0.0
            if not self.cheap_open and not self.low_implied_odds:
                board_weight = 0.10 + 0.025 * min(2.0, max(0.0, self.open_size - 2))
            if self.low_implied_odds:
                board_weight += 0.05
            if self.cheap_open and n > 3:
                board_weight += 0.05
            if self.can_reraise and (n == 3 or (small and self.low_implied_odds)):
                # A raiser's high-card range pairs high boards more often.
                board_weight *= 0.5 if raiser else 1.5
            defend = clamp(defend + board_weight * (1 - 2 * bs) * x ** 2)

        value_raise = 0.0
        if preflop == 'rc' and history == 'r':
            if n == 3 and not small and self.multi_raise:
                # A continuation bet can represent a pair on a middle board.
                defend = clamp(defend - 0.10 * hump(bs) * x ** 2)
            if n > 3 and small:
                # Occasionally raise strong unpaired hands for value on low boards.
                value_rate = 0.15 if n == 4 and not self.low_implied_odds else 0.30
                value_raise = value_rate * x ** 4 * (1 - bs) ** 2
        return defend_actions(legal, defend, 0.03 * (1 - x) + value_raise)
