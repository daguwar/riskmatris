"""Enhetstester för kärnfunktioner i app.py."""

import math
import sys
import os

# Lägg till projektroten i sys.path så vi kan importera app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import (
    PROBABILITY_LABELS,
    CONSEQUENCE_LABELS,
    round_half_up,
    get_risk_level,
    generate_session_id,
    create_new_risk,
    compute_risk_stats,
    get_local_lan_ip,
    SESSIONS,
)


# ---------------------------------------------------------------------------
# round_half_up
# ---------------------------------------------------------------------------

class TestRoundHalfUp:
    """Avrundning enligt försiktighetsprincipen (.5 uppåt), begränsad till 1..4."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (1.0, 1),
            (1.4, 1),
            (1.5, 2),
            (1.6, 2),
            (2.0, 2),
            (2.5, 3),
            (3.0, 3),
            (3.5, 4),
            (4.0, 4),
            (4.4, 4),
            # Utom gränserna – ska begränsas
            (0.0, 1),
            (0.4, 1),
            (0.5, 1),
            (5.0, 4),
            (99.9, 4),
            (-1.0, 1),
        ],
    )
    def test_rounding(self, value, expected):
        assert round_half_up(value) == expected

    def test_exact_half_rounds_up(self):
        """.5 ska alltid avrundas uppåt."""
        assert round_half_up(2.5) == 3
        assert round_half_up(3.5) == 4

    def test_below_half_rounds_down(self):
        assert round_half_up(2.49) == 2
        assert round_half_up(3.49) == 3


# ---------------------------------------------------------------------------
# get_risk_level
# ---------------------------------------------------------------------------

class TestGetRiskLevel:
    """Riskvärde 1–16 mappas till nivå och färg."""

    @pytest.mark.parametrize(
        "score, expected_level, expected_color",
        [
            (1, "Låg", "green"),
            (2, "Låg", "green"),
            (3, "Medel", "yellow"),
            (4, "Medel", "yellow"),
            (6, "Medel", "yellow"),
            (8, "Hög", "orange"),
            (9, "Hög", "orange"),
            (12, "Mycket Hög", "red"),
            (16, "Mycket Hög", "red"),
        ],
    )
    def test_levels(self, score, expected_level, expected_color):
        result = get_risk_level(score)
        assert result["level"] == expected_level
        assert result["color"] == expected_color

    def test_boundary_green_to_yellow(self):
        assert get_risk_level(2)["level"] == "Låg"
        assert get_risk_level(3)["level"] == "Medel"

    def test_boundary_yellow_to_orange(self):
        assert get_risk_level(6)["level"] == "Medel"
        assert get_risk_level(8)["level"] == "Hög"

    def test_boundary_orange_to_red(self):
        assert get_risk_level(9)["level"] == "Hög"
        assert get_risk_level(12)["level"] == "Mycket Hög"


# ---------------------------------------------------------------------------
# generate_session_id
# ---------------------------------------------------------------------------

class TestGenerateSessionId:
    """Sessions-ID ska vara 6 tecken, utan förväxlingsbara tecken."""

    ALLOWED_CHARS = set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")

    def test_length_is_six(self):
        sid = generate_session_id()
        assert len(sid) == 6

    def test_only_allowed_chars(self):
        for _ in range(100):
            sid = generate_session_id()
            for ch in sid:
                assert ch in self.ALLOWED_CHARS, f"Otillåtet tecken '{ch}' i {sid}"

    def test_no_ambiguous_chars(self):
        """0, O, 1, I, L ska aldrig förekomma."""
        forbidden = set("01OIL")
        for _ in range(200):
            sid = generate_session_id()
            for ch in sid:
                assert ch not in forbidden, f"Förväxlingsbart tecken '{ch}' i {sid}"

    def test_uniqueness(self):
        """Genererade ID:n ska vara unika (åtminstone bland 1000 försök)."""
        seen = set()
        for _ in range(1000):
            sid = generate_session_id()
            assert sid not in seen, f"Dubblett: {sid}"
            seen.add(sid)


# ---------------------------------------------------------------------------
# create_new_risk
# ---------------------------------------------------------------------------

class TestCreateNewRisk:
    def test_defaults(self):
        risk = create_new_risk(1)
        assert risk["number"] == 1
        assert risk["label"] == ""
        assert risk["votes"] == {}
        assert risk["revealed"] is False
        assert risk["locked"] is False
        assert risk["final_probability"] is None
        assert risk["final_consequence"] is None

    def test_with_label(self):
        risk = create_new_risk(3, "  Brandrisk  ")
        assert risk["number"] == 3
        assert risk["label"] == "Brandrisk"  # whitespace strippad

    def test_empty_label_stripped(self):
        risk = create_new_risk(2, "   ")
        assert risk["label"] == ""


# ---------------------------------------------------------------------------
# compute_risk_stats
# ---------------------------------------------------------------------------

class TestComputeRiskStats:
    def _make_risk(self, votes=None, revealed=False, locked=False,
                   final_prob=None, final_cons=None, label="Testrisk"):
        risk = create_new_risk(1, label)
        if votes:
            risk["votes"] = votes
        risk["revealed"] = revealed
        risk["locked"] = locked
        risk["final_probability"] = final_prob
        risk["final_consequence"] = final_cons
        return risk

    def test_no_votes(self):
        risk = self._make_risk()
        stats = compute_risk_stats(risk, effective_threshold=4)
        assert stats["vote_count"] == 0
        assert stats["revealed"] is False
        assert stats["avg_probability"] is None
        assert stats["suggested_probability"] is None
        assert stats["cell_counts"] == {}

    def test_votes_hidden_when_below_threshold(self):
        votes = {
            "a": {"probability": 2, "consequence": 3, "updated_at": 0},
            "b": {"probability": 3, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, effective_threshold=4)
        assert stats["vote_count"] == 2
        assert stats["revealed"] is False
        # Snitt ska vara dolt när inte revealed
        assert stats["avg_probability"] is None
        assert stats["cell_counts"] == {}

    def test_votes_revealed_at_threshold(self):
        votes = {
            "a": {"probability": 2, "consequence": 3, "updated_at": 0},
            "b": {"probability": 3, "consequence": 2, "updated_at": 0},
            "c": {"probability": 4, "consequence": 4, "updated_at": 0},
            "d": {"probability": 1, "consequence": 1, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, effective_threshold=4)
        assert stats["vote_count"] == 4
        assert stats["revealed"] is True
        assert stats["avg_probability"] == 2.5
        assert stats["avg_consequence"] == 2.5
        assert stats["suggested_probability"] == 3  # .5 avrundas uppåt
        assert stats["suggested_consequence"] == 3

    def test_cell_counts(self):
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 2, "consequence": 2, "updated_at": 0},
            "c": {"probability": 3, "consequence": 1, "updated_at": 0},
            "d": {"probability": 4, "consequence": 4, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, effective_threshold=4)
        assert stats["cell_counts"]["2_2"] == 2
        assert stats["cell_counts"]["3_1"] == 1
        assert stats["cell_counts"]["4_4"] == 1
        assert len(stats["cell_counts"]) == 3

    def test_locked_risk_shows_final_values(self):
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(
            votes=votes,
            locked=True,
            final_prob=4,
            final_cons=3,
        )
        stats = compute_risk_stats(risk, effective_threshold=4)
        assert stats["locked"] is True
        assert stats["revealed"] is True
        assert stats["final_probability"] == 4
        assert stats["final_consequence"] == 3
        assert stats["effective_probability"] == 4
        assert stats["effective_consequence"] == 3
        assert stats["score"] == 12
        assert stats["level"] == "Mycket Hög"
        assert stats["color"] == "red"

    def test_final_overrides_suggested(self):
        """Om final_probability är satt ska den användas före förslaget."""
        votes = {
            "a": {"probability": 1, "consequence": 1, "updated_at": 0},
            "b": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(
            votes=votes,
            revealed=True,
            final_prob=4,
            final_cons=4,
        )
        stats = compute_risk_stats(risk, effective_threshold=4)
        # Snitt blir 1.5/1.5 -> förslag 2/2, men final är 4/4
        assert stats["suggested_probability"] == 2
        assert stats["suggested_consequence"] == 2
        assert stats["effective_probability"] == 4
        assert stats["effective_consequence"] == 4
        assert stats["score"] == 16

    def test_score_and_level_correct(self):
        votes = {
            "a": {"probability": 3, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, effective_threshold=1)
        assert stats["score"] == 6
        assert stats["level"] == "Medel"
        assert stats["color"] == "yellow"

    def test_threshold_auto_reveals(self):
        """När antal röster >= tröskel ska revealed sättas automatiskt."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 3, "consequence": 3, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        assert risk["revealed"] is False
        stats = compute_risk_stats(risk, effective_threshold=2)
        assert risk["revealed"] is True
        assert stats["revealed"] is True


# ---------------------------------------------------------------------------
# Konstanter
# ---------------------------------------------------------------------------

class TestLabels:
    def test_probability_labels_complete(self):
        assert set(PROBABILITY_LABELS.keys()) == {1, 2, 3, 4}
        assert PROBABILITY_LABELS[1] == "Osannolik"
        assert PROBABILITY_LABELS[4] == "Mycket sannolik"

    def test_consequence_labels_complete(self):
        assert set(CONSEQUENCE_LABELS.keys()) == {1, 2, 3, 4}
        assert CONSEQUENCE_LABELS[1] == "Försumbar"
        assert CONSEQUENCE_LABELS[4] == "Mycket allvarlig"


# ---------------------------------------------------------------------------
# get_local_lan_ip (cachad)
# ---------------------------------------------------------------------------

class TestGetLocalLanIp:
    def test_returns_valid_ip_string(self):
        ip = get_local_lan_ip()
        assert isinstance(ip, str)
        # Ska vara en IPv4-adress eller 127.0.0.1
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_is_cached(self):
        """Anrop två gånger ska returnera samma värde (cachat)."""
        ip1 = get_local_lan_ip()
        ip2 = get_local_lan_ip()
        assert ip1 == ip2

    def test_cache_info_hit(self):
        """Efter första anropet ska cache-info visa minst 1 hit eller miss."""
        get_local_lan_ip()  # säkerställ första anropet
        info = get_local_lan_ip.cache_info()
        assert info.hits + info.misses >= 1
