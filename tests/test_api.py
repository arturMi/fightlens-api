"""API tests with the made-up data in tests/data:

night 1  Stone beats Rivera · Brandt beats Sam Lee (135 lbs) · Kowalski and Novak draw
night 2  Rivera beats Kowalski · Sam Lee (185 lbs) and Ortiz: no contest
         · Brandt beats "Mystery Man", who is not in the fighter list
night 3  Stone beats Rivera again, in a title fight
"""

import psycopg
import pytest

from fightlens import config, elo, importer

STONE, RIVERA, KOWALSKI = "a1a1a1a1a1a1a1a1", "b2b2b2b2b2b2b2b2", "c3c3c3c3c3c3c3c3"
SMALL_SAM, BIG_SAM, BRANDT = "5a5a5a5a5a5a5a5a", "5b5b5b5b5b5b5b5b", "e5e5e5e5e5e5e5e5"
TOKEN = {"Authorization": "Bearer test-token"}


def expected_ratings():
    """The Elo ratings worked out by hand, night by night."""
    stone, rivera = elo.update(1500, 1500, 1)  # night 1 (the draw changes nothing)
    rivera, kowalski = elo.update(rivera, 1500, 1)  # night 2
    stone, rivera = elo.update(stone, rivera, 1)  # night 3
    return {"stone": stone, "rivera": rivera, "kowalski": kowalski}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_search_by_name_or_nickname(client):
    assert [f["name"] for f in client.get("/api/v1/fighters?search=ston").json()] == ["Alex Stone"]
    assert client.get("/api/v1/fighters?search=hammer").json()[0]["id"] == KOWALSKI


def test_fighter_with_fights(client):
    stone = client.get(f"/api/v1/fighters/{STONE}").json()
    assert (stone["wins"], stone["losses"], stone["draws"]) == (2, 0, 0)
    assert stone["elo"] == round(expected_ratings()["stone"])
    assert stone["division"] == "Lightweight"
    assert [fight["result"] for fight in stone["fights"]] == ["win", "win"]
    assert stone["fights"][0]["opponent"] == "Ben Rivera"
    assert stone["fights"][-1]["elo_before"] == 1500


def test_draws_and_catch_weight(client):
    kowalski = client.get(f"/api/v1/fighters/{KOWALSKI}").json()
    assert (kowalski["wins"], kowalski["losses"], kowalski["draws"]) == (0, 1, 1)
    assert kowalski["division"] == "Lightweight"  # the catch weight fight doesn't count


def test_two_fighters_with_the_same_name(client):
    small = client.get(f"/api/v1/fighters/{SMALL_SAM}").json()
    big = client.get(f"/api/v1/fighters/{BIG_SAM}").json()
    assert [fight["opponent"] for fight in small["fights"]] == ["Eli Brandt"]
    assert [fight["result"] for fight in big["fights"]] == ["no contest"]


def test_unknown_name_still_counts(client):
    assert client.get(f"/api/v1/fighters/{BRANDT}").json()["wins"] == 2
    night2 = client.get("/api/v1/events/e2e2e2e2e2e2e2e2").json()
    assert night2["fights"][2]["fighter1"] == "Mystery Man"
    assert night2["fights"][2]["fighter1_id"] is None


def test_event_with_fights(client):
    night1 = client.get("/api/v1/events/e1e1e1e1e1e1e1e1").json()
    assert [fight["fighter1"] for fight in night1["fights"]] == [
        "Alex Stone",
        "Sam Lee",
        "Carl Kowalski",
    ]
    assert len(client.get("/api/v1/events?year=2025").json()) == 2


def test_rankings(client):
    names = [f["name"] for f in client.get("/api/v1/rankings?division=Lightweight").json()]
    assert names == ["Alex Stone", "Ben Rivera", "Carl Kowalski"]


def test_predict(client):
    prediction = client.get(f"/api/v1/predict?fighter1={STONE}&fighter2={RIVERA}").json()
    ratings = expected_ratings()
    chance = elo.win_chance(ratings["stone"], ratings["rivera"])
    assert prediction["fighter1"]["chance"] == pytest.approx(chance, abs=0.01)
    assert prediction["fighter1"]["chance"] + prediction["fighter2"]["chance"] == pytest.approx(1)


def test_not_found(client):
    response = client.get("/api/v1/fighters/nobody")
    assert response.status_code == 404
    assert response.json() == {"detail": "Fighter not found"}


def test_import_needs_the_token(client):
    assert client.post("/api/v1/import").status_code in (401, 403)
    wrong = {"Authorization": "Bearer wrong"}
    assert client.post("/api/v1/import", headers=wrong).status_code == 401


def test_import_again_changes_nothing(client, sent_fights):
    report = client.post("/api/v1/import", headers=TOKEN).json()
    assert report["fights"] == 7
    assert report["new_fights"] == 0
    assert report["sent_to_redis"] == 0
    assert len(sent_fights()) == 7


def test_every_fight_is_sent_once(client, sent_fights):
    fights = sent_fights()
    assert len(fights) == len({fight["id"] for fight in fights}) == 7
    assert fights[0]["date"] == "2024-11-02"  # oldest first


def test_fights_wait_while_redis_is_down(client, sent_fights, monkeypatch):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE fights SET published = false WHERE id = 'f3000000000000a1'")

    monkeypatch.setattr(config, "REDIS_URL", "redis://localhost:1/0")  # nothing runs there
    assert importer.run()["sent_to_redis"] == 0
    monkeypatch.undo()

    assert importer.run()["sent_to_redis"] == 1
    assert sent_fights()[-1]["id"] == "f3000000000000a1"


def test_metrics(client):
    client.get(f"/api/v1/fighters/{STONE}")
    assert 'handler="/api/v1/fighters/{fighter_id}"' in client.get("/metrics").text
