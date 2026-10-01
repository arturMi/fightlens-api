"""Load the UFC data into PostgreSQL, update the Elo ratings and send new fights to Redis.

python -m fightlens.importer               # newest data from GitHub
python -m fightlens.importer tests/data    # or from a folder
"""

import json
import logging
import sys

import redis

from fightlens import config, dataset, db, elo

log = logging.getLogger("fightlens.importer")


class ImportRunning(Exception):
    pass


def run(source=None):
    """Import everything and return a short report."""
    data = dataset.load(source or config.DATASET_URL)
    with db.connect() as conn:
        # Only one import at a time. The lock is let go when the connection closes.
        if not conn.execute("SELECT pg_try_advisory_lock(42) AS free").fetchone()["free"]:
            raise ImportRunning("An import is already running")
        db.create_tables(conn)
        known_fights = {row["id"] for row in conn.execute("SELECT id FROM fights")}
        with conn.transaction():  # all or nothing
            save(conn, data)
            elo_check = elo.recalculate(conn)
        sent = send_new_fights(conn)

    return {
        "fighters": len(data["fighters"]),
        "events": len(data["events"]),
        "fights": len(data["fights"]),
        "new_fights": sum(1 for fight in data["fights"] if fight["id"] not in known_fights),
        "sent_to_redis": sent,
        **data["report"],
        "elo_check": elo_check,
    }


def save(conn, data):
    """Add new rows and update existing ones ("upsert"), so importing twice changes nothing."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO fighters (id, name, nickname, height_cm, reach_cm, weight_lbs, stance,
                                  birth_date)
            VALUES (%(id)s, %(name)s, %(nickname)s, %(height_cm)s, %(reach_cm)s,
                    %(weight_lbs)s, %(stance)s, %(birth_date)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, nickname = EXCLUDED.nickname,
                height_cm = EXCLUDED.height_cm, reach_cm = EXCLUDED.reach_cm,
                weight_lbs = EXCLUDED.weight_lbs, stance = EXCLUDED.stance,
                birth_date = EXCLUDED.birth_date
            """,
            data["fighters"],
        )
        cur.executemany(
            """
            INSERT INTO events (id, name, date, location)
            VALUES (%(id)s, %(name)s, %(date)s, %(location)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, date = EXCLUDED.date, location = EXCLUDED.location
            """,
            data["events"],
        )
        cur.executemany(
            """
            INSERT INTO fights (id, event_id, bout_order, fighter1_id, fighter1, fighter2_id,
                                fighter2, result, method, round, time, division, title_fight)
            VALUES (%(id)s, %(event_id)s, %(bout_order)s, %(fighter1_id)s, %(fighter1)s,
                    %(fighter2_id)s, %(fighter2)s, %(result)s, %(method)s, %(round)s,
                    %(time)s, %(division)s, %(title_fight)s)
            ON CONFLICT (id) DO UPDATE SET
                event_id = EXCLUDED.event_id, bout_order = EXCLUDED.bout_order,
                fighter1_id = EXCLUDED.fighter1_id, fighter1 = EXCLUDED.fighter1,
                fighter2_id = EXCLUDED.fighter2_id, fighter2 = EXCLUDED.fighter2,
                result = EXCLUDED.result, method = EXCLUDED.method, round = EXCLUDED.round,
                time = EXCLUDED.time, division = EXCLUDED.division,
                title_fight = EXCLUDED.title_fight
            """,
            data["fights"],
        )


def send_new_fights(conn):
    """Write all fights that were not sent yet to the Redis Stream, oldest first.

    A fight only counts as sent once Redis has taken it. If Redis is down, the import still
    works and the fights go out with the next import.
    """
    fights = conn.execute(
        """
        SELECT f.id, e.name AS event, e.date, f.division, f.title_fight, f.fighter1_id,
               f.fighter1, f.fighter2_id, f.fighter2, f.result, f.method, f.round, f.time
        FROM fights f JOIN events e ON e.id = f.event_id
        WHERE NOT f.published
        ORDER BY e.date, f.bout_order DESC
        """
    ).fetchall()
    if not fights:
        return 0
    try:
        with redis.Redis.from_url(config.REDIS_URL, socket_timeout=5).pipeline() as pipe:
            for fight in fights:
                pipe.xadd(config.STREAM, {"fight": json.dumps(fight, default=str)}, maxlen=20000)
            pipe.execute()
    except redis.RedisError as error:
        log.warning("Redis is not reachable, the fights will be sent next time: %s", error)
        return 0
    conn.execute(
        "UPDATE fights SET published = true WHERE id = ANY(%s)", [[f["id"] for f in fights]]
    )
    return len(fights)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    report = run(sys.argv[1] if len(sys.argv) > 1 else None)
    log.info("Import finished:\n%s", json.dumps(report, indent=2))
