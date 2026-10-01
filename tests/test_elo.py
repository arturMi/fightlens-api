import pytest

from fightlens.elo import START, update, win_chance


def test_equal_ratings_are_a_coin_flip():
    assert win_chance(1500, 1500) == 0.5


def test_400_points_more_means_10_to_1():
    assert win_chance(1900, 1500) == pytest.approx(10 / 11)


def test_winner_takes_points_from_loser():
    winner, loser = update(START, START, 1)
    assert winner > START > loser
    assert winner + loser == 2 * START


def test_upset_moves_more_points():
    favourite, _ = update(1700, 1500, 1)
    underdog, _ = update(1500, 1700, 1)
    assert underdog - 1500 > favourite - 1700
