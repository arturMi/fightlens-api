"""Read the UFC data and clean it up.

The data comes from https://github.com/Greco1899/scrape_ufc_stats: CSV files that are
copied from ufcstats.com every day. The list of fights only has the fighters' names, not
their ids, so we look the names up in the list of fighters (see find_fighter).
"""

import csv
import io
import re
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Weight limit of each division in pounds.
# "Light Heavyweight" has to come before "Heavyweight", see division().
WEIGHT_LIMITS = {
    "Strawweight": 115,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}

# The OUTCOME column is written from the first fighter's side: "W/L" means fighter 1 won.
RESULTS = {"W/L": "fighter1", "L/W": "fighter2", "D/D": "draw", "NC/NC": "no contest"}


def load(source):
    """Read all files and return the fighters, events and fights."""
    fighters = read_fighters(
        read_csv(source, "ufc_fighter_details.csv"), read_csv(source, "ufc_fighter_tott.csv")
    )
    events = read_events(read_csv(source, "ufc_event_details.csv"))
    fights, report = read_fights(read_csv(source, "ufc_fight_results.csv"), events, fighters)
    return {
        "fighters": list(fighters.values()),
        "events": events,
        "fights": fights,
        "report": report,
    }


def read_csv(source, name):
    """Read one CSV file, from the internet or from a folder."""
    if source.startswith("http"):
        with urllib.request.urlopen(f"{source}/{name}", timeout=60) as response:
            text = response.read().decode("utf-8")
    else:
        text = Path(source, name).read_text(encoding="utf-8")
    rows = csv.DictReader(io.StringIO(text))
    # Many values have spaces at the end, so we strip them all.
    return [{key: (value or "").strip() for key, value in row.items() if key} for row in rows]


def read_fighters(names, details):
    """Fighters by id. One file has the names, the other one height, weight and so on."""
    fighters = {}
    for row in names:
        fighter_id = last_part(row["URL"])
        fighters[fighter_id] = {
            "id": fighter_id,
            "name": f"{row['FIRST']} {row['LAST']}".strip(),
            "nickname": row["NICKNAME"] or None,
            "height_cm": None,
            "reach_cm": None,
            "weight_lbs": None,
            "stance": None,
            "birth_date": None,
        }
    for row in details:
        fighter = fighters.get(last_part(row["URL"]))
        if fighter:
            fighter["height_cm"] = height_in_cm(row["HEIGHT"])
            fighter["reach_cm"] = inches_to_cm(number(row["REACH"]))
            fighter["weight_lbs"] = number(row["WEIGHT"])
            fighter["stance"] = row["STANCE"] or None
            fighter["birth_date"] = to_date(row["DOB"], "%b %d, %Y")
    return fighters


def read_events(rows):
    return [
        {
            "id": last_part(row["URL"]),
            "name": row["EVENT"],
            "date": to_date(row["DATE"], "%B %d, %Y"),
            "location": row["LOCATION"] or None,
        }
        for row in rows
    ]


def read_fights(rows, events, fighters):
    """All fights, main event first, plus a short report of what could not be used."""
    event_ids = {event["name"]: event["id"] for event in events}
    fighters_by_name = defaultdict(list)
    for fighter in fighters.values():
        fighters_by_name[simple_name(fighter["name"])].append(fighter)

    fights = {}
    fights_per_event = defaultdict(int)
    skipped_rows = 0
    unmatched_names = set()

    for row in rows:
        fight_id = last_part(row["URL"])
        event_id = event_ids.get(row["EVENT"])
        # Renamed events show up twice, once under the old name. We skip those rows.
        if event_id is None or fight_id in fights or row["OUTCOME"] not in RESULTS:
            skipped_rows += 1
            continue

        name1, name2 = (name.strip() for name in row["BOUT"].split(" vs. ", 1))
        fight_division = division(row["WEIGHTCLASS"])
        fighter1_id = find_fighter(name1, fight_division, fighters_by_name)
        fighter2_id = find_fighter(name2, fight_division, fighters_by_name)
        if fighter1_id is None:
            unmatched_names.add(name1)
        if fighter2_id is None:
            unmatched_names.add(name2)

        fights[fight_id] = {
            "id": fight_id,
            "event_id": event_id,
            "bout_order": fights_per_event[event_id],
            "fighter1_id": fighter1_id,
            "fighter1": name1,
            "fighter2_id": fighter2_id,
            "fighter2": name2,
            "result": RESULTS[row["OUTCOME"]],
            "method": row["METHOD"],
            "round": number(row["ROUND"]),
            "time": row["TIME"] or None,
            "division": fight_division,
            "title_fight": is_title_fight(row["WEIGHTCLASS"]),
        }
        fights_per_event[event_id] += 1

    report = {"skipped_rows": skipped_rows, "unmatched_names": sorted(unmatched_names)}
    return list(fights.values()), report


def find_fighter(name, fight_division, fighters_by_name):
    """The id of the fighter with this name, or None if we can't tell.

    A few names belong to two people, for example a flyweight and a middleweight called
    Bruno Silva. Then we take the one whose weight is the limit of the fight's division.
    """
    candidates = fighters_by_name.get(simple_name(name), [])
    if len(candidates) > 1:
        limit = WEIGHT_LIMITS.get((fight_division or "").removeprefix("Women's "))
        candidates = [fighter for fighter in candidates if fighter["weight_lbs"] == limit]
    return candidates[0]["id"] if len(candidates) == 1 else None


def simple_name(name):
    """A name without accents, capital letters and word order: "José Aldo" == "aldo jose"."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(sorted(re.findall(r"[a-z0-9]+", plain.lower())))


def division(weight_class):
    """ "UFC Women's Flyweight Title Bout" -> "Women's Flyweight"."""
    for name in [*WEIGHT_LIMITS, "Catch Weight", "Open Weight"]:
        if name in weight_class:
            return f"Women's {name}" if "Women's" in weight_class else name
    return None  # the first tournaments had no divisions


def is_title_fight(weight_class):
    """Fights for a UFC belt. Tournament finals (like The Ultimate Fighter) don't count."""
    return "Title" in weight_class and "Tournament" not in weight_class


def last_part(url):
    """'http://ufcstats.com/fighter-details/93fe7332d16c6ad9' -> '93fe7332d16c6ad9'"""
    return url.rstrip("/").split("/")[-1]


def number(text):
    """The first number in a text: '155 lbs.' -> 155. None if there is no number."""
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def height_in_cm(text):
    """5' 11" -> 180"""
    match = re.match(r"(\d+)' (\d+)\"", text)
    return round((int(match[1]) * 12 + int(match[2])) * 2.54) if match else None


def inches_to_cm(inches):
    return round(inches * 2.54) if inches else None


def to_date(text, date_format):
    try:
        return datetime.strptime(text, date_format).date()
    except ValueError:
        return None
