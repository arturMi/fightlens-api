"""What the API returns. FastAPI uses these classes for the docs on /docs."""

from datetime import date

from pydantic import BaseModel


class Fighter(BaseModel):
    id: str
    name: str
    nickname: str | None
    division: str | None
    wins: int
    losses: int
    draws: int
    elo: int | None
    last_fight: date | None


class FightOfFighter(BaseModel):
    """One fight, seen from one fighter's side."""

    fight_id: str
    event: str
    date: date
    opponent: str
    opponent_id: str | None
    result: str  # win, loss, draw or no contest
    method: str
    round: int | None
    time: str | None
    elo_before: int | None
    elo_after: int | None


class FighterDetail(Fighter):
    height_cm: int | None
    reach_cm: int | None
    stance: str | None
    birth_date: date | None
    fights: list[FightOfFighter]


class Fight(BaseModel):
    id: str
    fighter1_id: str | None
    fighter1: str
    fighter2_id: str | None
    fighter2: str
    result: str  # fighter1, fighter2, draw or no contest
    method: str
    round: int | None
    time: str | None
    division: str | None
    title_fight: bool


class Event(BaseModel):
    id: str
    name: str
    date: date
    location: str | None


class EventDetail(Event):
    fights: list[Fight]


class Contender(Fighter):
    chance: float  # chance to win, between 0 and 1


class Prediction(BaseModel):
    fighter1: Contender
    fighter2: Contender
