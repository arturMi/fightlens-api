"""Elo ratings: rating fighters by whom they have beaten.

Everybody starts with 1500 points. After a fight the winner takes points from the loser:
only a few for beating a weaker opponent, a lot for an upset.
"""

START = 1500
K = 64  # how many points one fight can move. 64 predicted a bit better than the chess value 32.


def win_chance(elo_a, elo_b):
    """The chance that A beats B, between 0 and 1."""
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def update(elo_a, elo_b, score_a):
    """New ratings after a fight. score_a is 1 if A won, 0 if A lost and 0.5 for a draw."""
    change = K * (score_a - win_chance(elo_a, elo_b))
    return elo_a + change, elo_b - change


def recalculate(conn):
    """Go through all fights from old to new and work out every fighter's rating and record.

    On the way we also check how good the ratings are: before each fight between two
    fighters with at least 3 fights, did the one with the higher rating win?
    """
    fights = conn.execute(
        """
        SELECT f.id, f.fighter1_id, f.fighter2_id, f.result, f.division, e.date
        FROM fights f JOIN events e ON e.id = f.event_id
        ORDER BY e.date, f.bout_order DESC  -- on each night the main event comes last
        """
    ).fetchall()

    ratings = {}  # fighter id -> current rating
    fighters = {}  # fighter id -> record, division and date of the last fight
    elo_changes = []
    checked = correct = 0

    for fight in fights:
        a, b, result = fight["fighter1_id"], fight["fighter2_id"], fight["result"]
        for fighter_id in (a, b):
            if fighter_id and fighter_id not in fighters:
                fighters[fighter_id] = {
                    "id": fighter_id,
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "fights": 0,
                    "division": None,
                }

        # Ratings only change if we know both fighters. A no contest changes nothing.
        if a and b:
            elo_a, elo_b = ratings.get(a, START), ratings.get(b, START)
            if result != "no contest":
                if result != "draw" and fighters[a]["fights"] >= 3 and fighters[b]["fights"] >= 3:
                    checked += 1
                    correct += (elo_a > elo_b) == (result == "fighter1")
                score = {"fighter1": 1, "fighter2": 0, "draw": 0.5}[result]
                ratings[a], ratings[b] = update(elo_a, elo_b, score)
            else:
                ratings[a], ratings[b] = elo_a, elo_b
            elo_changes.append((elo_a, ratings[a], elo_b, ratings[b], fight["id"]))

        # Record, division and date of the last fight count even if the opponent is unknown.
        for fighter_id, side in ((a, "fighter1"), (b, "fighter2")):
            if not fighter_id:
                continue
            fighter = fighters[fighter_id]
            if result == side:
                fighter["wins"] += 1
            elif result in ("fighter1", "fighter2"):
                fighter["losses"] += 1
            elif result == "draw":
                fighter["draws"] += 1
            fighter["fights"] += 1
            fighter["last_fight"] = fight["date"]
            if fight["division"] not in (None, "Catch Weight", "Open Weight"):
                fighter["division"] = fight["division"]

    for fighter_id, fighter in fighters.items():
        fighter["elo"] = ratings.get(fighter_id)

    with conn.cursor() as cur:
        cur.executemany(
            """UPDATE fights SET elo1_before = %s, elo1_after = %s, elo2_before = %s,
               elo2_after = %s WHERE id = %s""",
            elo_changes,
        )
        cur.executemany(
            """UPDATE fighters SET wins = %(wins)s, losses = %(losses)s, draws = %(draws)s,
               division = %(division)s, elo = %(elo)s, last_fight = %(last_fight)s
               WHERE id = %(id)s""",
            list(fighters.values()),
        )

    return {
        "fights_checked": checked,
        "higher_rated_won": round(correct / checked, 3) if checked else None,
    }
