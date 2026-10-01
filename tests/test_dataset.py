from pathlib import Path

from fightlens import dataset
from fightlens.dataset import division, find_fighter, height_in_cm, is_title_fight, simple_name

TEST_DATA = str(Path(__file__).parent / "data")


def test_height_and_reach():
    assert height_in_cm("5' 11\"") == 180
    assert height_in_cm("--") is None
    assert dataset.inches_to_cm(dataset.number('74"')) == 188


def test_division_and_title():
    assert division("UFC Women's Flyweight Title Bout") == "Women's Flyweight"
    assert division("Light Heavyweight Bout") == "Light Heavyweight"
    assert division("UFC 2 Tournament Title Bout") is None
    assert is_title_fight("UFC Interim Lightweight Title Bout")
    assert not is_title_fight("Ultimate Fighter 33 Welterweight Tournament Title Bout")


def test_names_match_without_accents_or_word_order():
    assert simple_name("José Aldo") == simple_name("Jose  Aldo")
    assert simple_name("Magomed Bibulatov") == simple_name("Bibulatov Magomed")


def test_same_name_is_told_apart_by_weight():
    small = {"id": "small", "name": "Sam Lee", "weight_lbs": 135}
    big = {"id": "big", "name": "Sam Lee", "weight_lbs": 185}
    by_name = {"lee sam": [small, big]}
    assert find_fighter("Sam Lee", "Bantamweight", by_name) == "small"
    assert find_fighter("Sam Lee", "Middleweight", by_name) == "big"
    assert find_fighter("Sam Lee", "Catch Weight", by_name) is None  # could be either
    assert find_fighter("Nobody", "Lightweight", by_name) is None


def test_load_test_data():
    data = dataset.load(TEST_DATA)
    assert len(data["fighters"]) == 8
    assert len(data["events"]) == 3
    assert len(data["fights"]) == 7  # the row under the old event name is skipped
    assert data["report"] == {"skipped_rows": 1, "unmatched_names": ["Mystery Man"]}
    main_event = next(fight for fight in data["fights"] if fight["id"] == "f1000000000000a1")
    assert main_event["bout_order"] == 0  # listed first on its card
    assert main_event["method"] == "KO/TKO"  # spaces at the end are gone
