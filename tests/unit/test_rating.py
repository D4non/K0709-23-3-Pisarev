"""
Unit tests for the three-level rating algorithm (app/services/rating.py).

All functions under test are pure (no DB/Redis calls), so no mocks needed
except lightweight MagicMock objects that simulate ORM model instances.
"""
import pytest
from unittest.mock import MagicMock

from app.services.rating import (
    _gender_score,
    _age_score,
    _interest_score,
    _completeness_score,
    calculate_level1,
    calculate_level2,
    calculate_combined,
)
from app.models.orm import CandidateBehavioralStats


# ─── _gender_score ────────────────────────────────────────────────────────────

def test_gender_score_exact_match():
    assert _gender_score("female", "female") == 1.0


def test_gender_score_mismatch():
    assert _gender_score("male", "female") == 0.0


def test_gender_score_no_preference_returns_neutral():
    assert _gender_score(None, "female") == 0.5
    assert _gender_score(None, "male") == 0.5


# ─── _age_score ───────────────────────────────────────────────────────────────

def test_age_score_below_range():
    assert _age_score(25, 35, 20) == 0.0


def test_age_score_above_range():
    assert _age_score(25, 35, 40) == 0.0


def test_age_score_at_center_is_max():
    assert _age_score(20, 30, 25) == pytest.approx(1.0)


def test_age_score_at_boundary_still_valid():
    score = _age_score(20, 30, 20)
    assert score >= 0.5


def test_age_score_equal_min_max():
    # Edge: min == max, candidate matches
    assert _age_score(25, 25, 25) == 1.0


# ─── _interest_score ──────────────────────────────────────────────────────────

def test_interest_score_full_overlap():
    assert _interest_score(["music", "sport"], ["music", "sport"]) == 1.0


def test_interest_score_no_overlap():
    assert _interest_score(["music"], ["sport"]) == 0.0


def test_interest_score_partial_overlap():
    # intersection=1 ("music"), union=3 → Jaccard = 1/3
    score = _interest_score(["music", "sport"], ["music", "books"])
    assert score == pytest.approx(1 / 3)


def test_interest_score_both_empty_returns_neutral():
    assert _interest_score([], []) == 0.5


def test_interest_score_case_insensitive():
    assert _interest_score(["Music"], ["music"]) == 1.0


# ─── _completeness_score ──────────────────────────────────────────────────────

def _make_candidate(has_bio=True, has_interests=True, has_photos=True):
    candidate = MagicMock()
    candidate.profile.bio = "bio text" if has_bio else None
    candidate.interests = [MagicMock()] if has_interests else []
    candidate.photos = [MagicMock()] if has_photos else []
    return candidate


def test_completeness_score_full_profile():
    assert _completeness_score(_make_candidate()) == pytest.approx(1.0)


def test_completeness_score_no_bio():
    score = _completeness_score(_make_candidate(has_bio=False))
    assert score == pytest.approx(0.6)  # interests 0.3 + photos 0.3


def test_completeness_score_empty_profile():
    score = _completeness_score(_make_candidate(has_bio=False, has_interests=False, has_photos=False))
    assert score == 0.0


# ─── calculate_level2 ─────────────────────────────────────────────────────────

def _make_stats(likes=0, skips=0, is_matched=False):
    s = MagicMock(spec=CandidateBehavioralStats)
    s.likes_given = likes
    s.skips_given = skips
    s.is_matched = is_matched
    return s


def test_level2_no_stats_returns_neutral():
    assert calculate_level2([]) == 0.5


def test_level2_all_likes_no_matches():
    # like_ratio=1.0, match_rate=0.5 (no matches but likes exist → 0/10=0 → wait...
    # match_rate = sum(1 for s if s.is_matched) / total_likes = 0/10 = 0
    # 0.6*1.0 + 0.4*0.0 = 0.6
    stats = [_make_stats(likes=10, skips=0, is_matched=False)]
    assert calculate_level2(stats) == pytest.approx(0.6)


def test_level2_all_likes_with_match():
    # like_ratio=1.0, match_rate = 1 matched row / 10 likes = 0.1
    # 0.6*1.0 + 0.4*0.1 = 0.64
    stats = [_make_stats(likes=10, skips=0, is_matched=True)]
    assert calculate_level2(stats) == pytest.approx(0.64)


def test_level2_all_skips():
    # like_ratio=0.0, match_rate defaults to 0.5 (no likes)
    # 0.6*0.0 + 0.4*0.5 = 0.2
    stats = [_make_stats(likes=0, skips=10, is_matched=False)]
    assert calculate_level2(stats) == pytest.approx(0.2)


def test_level2_equal_likes_and_skips():
    stats = [_make_stats(likes=5, skips=5, is_matched=False)]
    # like_ratio=0.5, match_rate=0.0
    # 0.6*0.5 + 0.4*0.0 = 0.3
    assert calculate_level2(stats) == pytest.approx(0.3)


# ─── calculate_combined ───────────────────────────────────────────────────────

def test_combined_zero_interactions_uses_only_level1():
    # behavioral_weight = 0 → combined = level1
    score = calculate_combined(level1=0.8, level2=0.0, interaction_count=0)
    assert score == pytest.approx(0.8)


def test_combined_50_interactions_caps_behavioral_at_60pct():
    # behavioral_weight = min(0.6, 50/50 * 0.6) = 0.6
    score = calculate_combined(level1=1.0, level2=0.0, interaction_count=50)
    assert score == pytest.approx(0.4 * 1.0 + 0.6 * 0.0)


def test_combined_exceeds_cap_still_60pct():
    score_50 = calculate_combined(1.0, 0.5, 50)
    score_100 = calculate_combined(1.0, 0.5, 100)
    assert score_50 == pytest.approx(score_100)


def test_combined_25_interactions():
    # behavioral_weight = 25/50 * 0.6 = 0.3, static = 0.7
    score = calculate_combined(level1=1.0, level2=0.0, interaction_count=25)
    assert score == pytest.approx(0.7)
