"""FightLens API: UFC fighters, events and fights with Elo ratings.

Start it with `uvicorn fightlens.main:app --reload` and open http://localhost:8000/docs.
"""

import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_fastapi_instrumentator import Instrumentator

from fightlens import config, db, elo, importer
from fightlens.models import Event, EventDetail, Fighter, FighterDetail, Prediction


@asynccontextmanager
async def lifespan(app):
    with db.connect() as conn:
        db.create_tables(conn)
    yield


app = FastAPI(
    title="FightLens API",
    description="UFC fighters, events and fights with Elo ratings. Data from ufcstats.com.",
    version="1.0.0",
    lifespan=lifespan,
)
Instrumentator().instrument(app).expose(app, include_in_schema=False)  # metrics on /metrics

FIGHTER = "id, name, nickname, division, wins, losses, draws, round(elo)::int AS elo, last_fight"


def first_or_404(rows, what):
    if not rows:
        raise HTTPException(404, f"{what} not found")
    return rows[0]


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    """Is the API running and can it reach the database?"""
    db.query("SELECT 1")
    return {"status": "ok"}


@app.get("/api/v1/fighters", response_model=list[Fighter])
def list_fighters(
    search: str | None = None,
    division: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Fighters with the best rating first. Search works on name and nickname."""
    return db.query(
        f"""
        SELECT {FIGHTER} FROM fighters
        WHERE (%(search)s::text IS NULL OR name ILIKE %(like)s OR nickname ILIKE %(like)s)
          AND (%(division)s::text IS NULL OR division = %(division)s)
        ORDER BY elo DESC NULLS LAST, name
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "search": search,
            "like": f"%{search}%",
            "division": division,
            "limit": limit,
            "offset": offset,
        },
    )


@app.get("/api/v1/fighters/{fighter_id}", response_model=FighterDetail)
def get_fighter(fighter_id: str):
    """One fighter with all UFC fights, newest first."""
    rows = db.query(
        f"SELECT {FIGHTER}, height_cm, reach_cm, stance, birth_date FROM fighters WHERE id = %s",
        [fighter_id],
    )
    fighter = first_or_404(rows, "Fighter")
    fights = db.query(
        """
        SELECT f.*, e.name AS event, e.date
        FROM fights f JOIN events e ON e.id = f.event_id
        WHERE %(id)s IN (f.fighter1_id, f.fighter2_id)
        ORDER BY e.date DESC, f.bout_order
        """,
        {"id": fighter_id},
    )
    fighter["fights"] = [seen_by(fighter_id, fight) for fight in fights]
    return fighter


def seen_by(fighter_id, fight):
    """A fight from one fighter's side: who was the opponent, and was it a win or a loss?"""
    me, opponent = ("1", "2") if fight["fighter1_id"] == fighter_id else ("2", "1")
    if fight["result"] == f"fighter{me}":
        result = "win"
    elif fight["result"] == f"fighter{opponent}":
        result = "loss"
    else:
        result = fight["result"]  # draw or no contest
    return {
        "fight_id": fight["id"],
        "event": fight["event"],
        "date": fight["date"],
        "opponent": fight[f"fighter{opponent}"],
        "opponent_id": fight[f"fighter{opponent}_id"],
        "result": result,
        "method": fight["method"],
        "round": fight["round"],
        "time": fight["time"],
        "elo_before": rounded(fight[f"elo{me}_before"]),
        "elo_after": rounded(fight[f"elo{me}_after"]),
    }


def rounded(number):
    return None if number is None else round(number)


@app.get("/api/v1/rankings", response_model=list[Fighter])
def rankings(
    division: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
):
    """The highest rated fighters who fought in the last two years. No division = all."""
    return db.query(
        f"""
        SELECT {FIGHTER} FROM fighters
        WHERE elo IS NOT NULL
          AND last_fight >= (SELECT max(date) FROM events) - 730
          AND (%(division)s::text IS NULL OR division = %(division)s)
        ORDER BY elo DESC
        LIMIT %(limit)s
        """,
        {"division": division, "limit": limit},
    )


@app.get("/api/v1/predict", response_model=Prediction)
def predict(fighter1: str, fighter2: str):
    """Who would win? The chance of each fighter, based on their Elo ratings."""
    sql = f"SELECT {FIGHTER} FROM fighters WHERE id = %s"
    a = first_or_404(db.query(sql, [fighter1]), "Fighter")
    b = first_or_404(db.query(sql, [fighter2]), "Fighter")
    chance = elo.win_chance(a["elo"] or elo.START, b["elo"] or elo.START)
    a["chance"], b["chance"] = round(chance, 2), round(1 - chance, 2)
    return {"fighter1": a, "fighter2": b}


@app.get("/api/v1/events", response_model=list[Event])
def list_events(
    year: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Events, newest first."""
    return db.query(
        """
        SELECT id, name, date, location FROM events
        WHERE %(year)s::int IS NULL OR extract(year FROM date) = %(year)s::int
        ORDER BY date DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {"year": year, "limit": limit, "offset": offset},
    )


@app.get("/api/v1/events/{event_id}", response_model=EventDetail)
def get_event(event_id: str):
    """One event with all its fights, main event first."""
    rows = db.query("SELECT id, name, date, location FROM events WHERE id = %s", [event_id])
    event = first_or_404(rows, "Event")
    event["fights"] = db.query(
        """
        SELECT id, fighter1_id, fighter1, fighter2_id, fighter2, result, method, round, time,
               division, title_fight
        FROM fights WHERE event_id = %s
        ORDER BY bout_order
        """,
        [event_id],
    )
    return event


@app.post("/api/v1/import")
def run_import(token: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]):
    """Load the newest data (takes a few seconds). Send IMPORT_TOKEN as bearer token."""
    if not config.IMPORT_TOKEN or not secrets.compare_digest(
        token.credentials, config.IMPORT_TOKEN
    ):
        raise HTTPException(401, "Wrong token")
    try:
        return importer.run()
    except importer.ImportRunning:
        raise HTTPException(409, "An import is already running") from None
