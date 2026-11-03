"""Mixed, rank-based rules for two-round limit poker.

The same rules cover different deck sizes, bet sizes and raise caps.  They use
only the current information set and do not depend on the order of calls.
"""


def clamp(value):
    return max(0.0, min(1.0, value))


def defend_actions(legal, defend, raise_probability):
    """Split a defending range into calls and raises, folding the remainder."""
    raise_probability = min(raise_probability, defend) if 'raise' in legal else 0.0
    actions = {'fold': 1.0 - defend, 'call': defend - raise_probability}
    if 'raise' in legal:
        actions['raise'] = raise_probability
    return actions


class Policy:
    def __init__(self, spec):
        game = spec['game']
        self.ranks = game['ranks']
        self.suit_count = len(game['suits'])
        self.raise_cap = game['max_raises']
        self.preflop_bet = game['raise_sizes'][0]
        self.ante = game['ante']
        second_bet = game['raise_sizes'][1]
        self.small_second_bet = second_bet <= 2 * self.ante
        self.low_implied_odds = second_bet <= self.preflop_bet
        # Larger second-round bets require a stronger unpaired calling hand.
        self.showdown_exponent = 1 + min(
            1.0, max(0.0, (second_bet / (2 * self.ante) - 1) * 0.5)
        )

    def reset(self):
        pass

    def act(self, obs, info):
        legal = obs['legal']
        rank = self.ranks.index(obs['hole'][:-1])
        rank_count = len(self.ranks)
        strength = rank / (rank_count - 1)
        history = obs['betting'][obs['round']]
        raises = history.count('r')
        facing_bet = obs['to_call'] > 0

        if obs['round'] == 0:
            if not facing_bet:
                # Mix in low-card bluffs while raising stronger ranks more.
                low_rate = 0.3 if rank_count == 3 else 0.25
                high_increment = 0.45 if rank_count == 3 else 0.50
                exponent = min(2.0, 0.5 + 0.75 * (rank_count - 3))
                raise_probability = low_rate + high_increment * strength ** exponent
                if (not history and rank_count > 3 and self.preflop_bet > self.ante
                        and self.raise_cap[0] > 1):
                    # Middle ranks retain useful showdown and drawing value.
                    raise_probability -= 0.2 * 4 * strength * (1 - strength)
                if history == 'c' and self.raise_cap[0] > 1 and not self.low_implied_odds:
                    # Bet top hands and mix in bluffs when opening cheaply.
                    raise_probability += 0.20 * strength ** 4
                    if rank_count > 3 and self.preflop_bet <= self.ante:
                        raise_probability += 0.15 * (1 - strength) ** 4
                if history == 'c' and self.raise_cap[0] == 1:
                    raise_probability = min(1.0, 0.3 + 0.9 * raise_probability)
                if 'raise' not in legal:
                    return 'call'
                return {'call': 1 - raise_probability, 'raise': raise_probability}

            # This is a smoothed price index: the reported pot already includes
            # the outstanding call.  Smaller values represent cheaper calls.
            price = obs['to_call'] / (obs['pot'] + obs['to_call'])
            cheap_open = self.preflop_bet <= self.ante
            base = 0.25 if rank_count == 3 or cheap_open else 0.15
            if rank_count == 3 and self.small_second_bet:
                rank_weight = 1.3
            elif (rank_count > 3 and self.preflop_bet >= 2 * self.ante
                  and self.raise_cap[0] >= 2):
                rank_weight = 0.85
            else:
                rank_weight = 1.05
            defend = clamp(base + rank_weight * strength + (0.33 - price))
            if raises == 1 and cheap_open:
                defend = max(defend, max(0.2, 0.8 - 0.3 * (rank_count - 3)))
            pair_draw = (self.suit_count - 1) / (rank_count * self.suit_count - 2)
            if history == 'r' and cheap_open and pair_draw >= 0.2:
                defend = min(1.0, defend + 0.25 * (1 - strength))
            # Defend some weak hands against an opening raise: they can
            # improve on the board, especially when later bets are larger.
            if history == 'r' and (rank_count == 3 or not self.low_implied_odds):
                defend = clamp(defend + (0.25 if rank_count == 3 else 0.15)
                               * (1 - strength) ** 3)
            if raises >= 2:
                # Once committed, protect the money already in the pot.
                defend = max(defend, max(0.6, 1.0 - 0.15 * (rank_count - 3)))
            if history == 'cr' and rank_count > 3 and cheap_open:
                # A raise after our check tends to be a narrower range.
                defend = clamp(defend - 0.25 * (1 - strength) ** 2)
            if raises == 1 and rank_count > 3 and self.low_implied_odds and not cheap_open:
                # With less upside from later bets, defend stronger middle
                # ranks more and weaker middle ranks less.
                defend = clamp(defend - 0.2 * (1 - strength) ** 2)
                defend = clamp(defend + 0.8 * (strength - 0.5)
                               * 4 * strength * (1 - strength))
            if raises >= 2 and rank_count > 4 and not cheap_open:
                # Multiple bets represent a narrower range in larger decks.
                defend = clamp(defend - 0.5 * (1 - strength) ** 2)
            # Reraise top ranks more often when larger preflop bets make
            # calling ranges narrower; keep more calls in small, cheap games.
            raise_rate = 0.6 if rank_count > 3 and self.suit_count > 2 else 0.4
            if rank_count == 3 and self.small_second_bet:
                raise_rate -= 0.2
            if rank_count > 3 and self.preflop_bet >= 2 * self.ante:
                raise_rate += 0.2
            exponent = 3 if raises == 1 and rank_count > 3 and cheap_open else 5
            return defend_actions(legal, defend, raise_rate * strength ** exponent)

        board = self.ranks.index(obs['board'][0][:-1])
        preflop = obs['betting'][0]
        if rank == board:
            # Strong pairs bet frequently.  In larger decks mix some checks
            # from first position to protect the checking range.
            if 'raise' not in legal:
                return 'call'
            slow_play = (rank_count > 3 and not facing_bet and not history
                         and preflop != 'rc')
            slow_rate = 0.6 if self.small_second_bet else 0.3
            if facing_bet or history == 'c':
                raise_probability = 1.0
            else:
                raise_probability = slow_rate if slow_play else 0.92
            if preflop == 'cc' and not history and rank_count == 3:
                # In small decks, protect checks more often on a low board.
                raise_probability = 0.2 + 0.7 * board / (rank_count - 1)
            return {'call': 1 - raise_probability, 'raise': raise_probability}

        # Rank among the non-pair hands, from weakest (0) to strongest (1).
        nonpair = (rank - (rank > board)) / max(1, rank_count - 2)
        if not facing_bet:
            base = (0.20 if self.small_second_bet
                    and (rank_count > 3 or self.suit_count > 2) else 0.12)
            # A strong unpaired hand can bet for value after a check, but
            # first to act it also helps protect the checking range.
            if self.raise_cap[1] == 1:
                value_rate = 0.33
            else:
                value_rate = 0.10 if history == 'c' else 0.0
            raise_probability = base + value_rate * nonpair ** 3
            if history == 'c' and preflop == 'rc' and self.raise_cap[1] > 1:
                # A preflop raiser who checks the board can be challenged
                # for value, particularly when we block the higher ranks.
                raise_probability += 0.30 * (1 - board / (rank_count - 1)) * nonpair ** 3
            if history == 'c' and rank_count > 3:
                raise_probability += 0.10 * (1 - nonpair) ** 3
            if history == 'c' and self.raise_cap[1] > 1 and rank_count > 3:
                raise_probability += 0.20 * nonpair ** 3
            if self.raise_cap[1] > 1:
                # Intermediate hands are useful checks against a raise.
                raise_probability = max(0.0, raise_probability - 0.16 * 4 * nonpair * (1 - nonpair))
            if 'r' in preflop and preflop.rfind('r') % 2 == obs['seat']:
                bluff = min(0.30, 0.05 + 0.25 * (rank_count - 3))
                if rank_count == 3 and self.raise_cap[1] > 1:
                    bluff = 0.23
                raise_probability += bluff * (1 - nonpair) ** 3
            if (preflop == 'rc' and not history
                    and (rank_count == 3 or self.preflop_bet <= self.ante)):
                # A high board favors the preflop raiser's continuation bluff;
                # on a low board a weak hand has less reason to bet.
                board_strength = board / (rank_count - 1)
                raise_probability = clamp(raise_probability + 0.15
                                          * (2 * board_strength - 1) * (1 - nonpair) ** 3)
            if preflop == 'cc' and not history and rank_count == 3:
                # Balance the pair checks with fewer bets on low boards.
                board_strength = board / (rank_count - 1)
                raise_probability = min(1.0, 2 * board_strength) * (
                    0.1 + 0.3 * board_strength * nonpair
                    + 0.25 * (1 - board_strength) * (1 - nonpair))
            if 'raise' not in legal:
                return 'call'
            return {'call': 1 - raise_probability, 'raise': raise_probability}

        price = obs['to_call'] / (obs['pot'] + obs['to_call'])
        base = -0.04 if self.small_second_bet else -0.10
        if rank_count == 3 and self.suit_count == 2:
            base -= 0.06
        rank_weight = max(0.65, min(0.91, 0.91 - 7.2 * (price - 0.25)))
        defend = clamp(base + rank_weight * nonpair ** self.showdown_exponent
                       + (1.3 if rank_count > 3 else 0.8) * (0.25 - price) - 0.05 * max(0, raises - 1))
        if raises > 1 and rank_count > 3 and not self.low_implied_odds:
            # Larger later bets make repeated raises more costly to call.
            defend = clamp(defend - 0.10 * (raises - 1))
        # In a small deck, distinguish a bet into the player from a bet
        # after the player checked; a reraise is a still stronger signal.
        if (raises == 1 and rank_count == 3
                and (not self.small_second_bet or self.suit_count == 2)):
            defend = clamp(defend + (0.1 if history == 'cr' else -0.1) * nonpair)
        if raises > 1 and rank_count == 3 and (not self.small_second_bet or self.suit_count == 2):
            defend = clamp(defend - 0.15 * (raises - 1))
        if (preflop == 'rc' and history == 'r' and rank_count > 4
                and self.small_second_bet and not self.low_implied_odds):
            # Prefer stronger marginal hands when facing the preflop raiser.
            defend = clamp(defend + 0.5 * (nonpair - 0.5) * 4 * nonpair * (1 - nonpair))
        if (preflop == 'rc' and history == 'cr' and rank_count == 3
                and not self.low_implied_odds and self.raise_cap[1] > 1):
            defend = clamp(defend - 0.15 * nonpair ** 2)
        if preflop == 'cc' and history == 'cr' and rank_count == 3:
            # After two checks, a bet into the low board is more pair-heavy.
            defend = clamp(defend - 0.6 * (1 - board / (rank_count - 1)) * nonpair ** 2)
        if preflop == 'cc' and history == 'cr' and rank_count > 3 and self.small_second_bet:
            defend = clamp(defend + 0.2 * (rank_count - 3) * nonpair ** 2)
        if preflop == 'cc':
            # An opponent who checked preflop is more likely to pair a low board.
            board_bias = 0.2 * (2 * board / (rank_count - 1) - 1) * nonpair ** 2
            defend = clamp(defend + board_bias)
        value_raise = 0.0
        if preflop == 'rc' and history == 'r' and rank_count > 3 and self.small_second_bet:
            # Occasionally raise strong unpaired hands for value on low boards.
            value_raise = 0.30 * nonpair ** 4 * (1 - board / (rank_count - 1)) ** 2
        return defend_actions(legal, defend, 0.03 * (1 - nonpair) + value_raise)
