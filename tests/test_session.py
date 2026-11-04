"""Tests for session and risk domain logic (riskmatris.session)."""

from app import compute_risk_stats, create_new_risk, generate_session_id

# ---------------------------------------------------------------------------
# generate_session_id
# ---------------------------------------------------------------------------


class TestGenerateSessionId:
    """Session IDs use the configured length (default 8 = 40 bits, sakerhetsrapport
    A01-3 raised it from 6 chars = ~30 bits), without confusable characters."""

    ALLOWED_CHARS = set("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")

    def test_length_matches_configured_default(self):
        import app as app_module

        assert app_module.SESSION_CODE_LENGTH == 8  # default: 8 chars from a 32-char alphabet = 40 bits
        sid = generate_session_id()
        assert len(sid) == app_module.SESSION_CODE_LENGTH

    def test_length_is_configurable(self, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CODE_LENGTH", 6)
        assert len(generate_session_id()) == 6
        monkeypatch.setattr(app_module, "SESSION_CODE_LENGTH", 12)
        assert len(generate_session_id()) == 12

    def test_only_allowed_chars(self):
        for _ in range(100):
            sid = generate_session_id()
            for ch in sid:
                assert ch in self.ALLOWED_CHARS, f"Disallowed character '{ch}' in {sid}"

    def test_no_ambiguous_chars(self):
        """0, O, 1, I, L must never occur."""
        forbidden = set("01OIL")
        for _ in range(200):
            sid = generate_session_id()
            for ch in sid:
                assert ch not in forbidden, f"Confusable character '{ch}' in {sid}"

    def test_uniqueness(self):
        """Generated IDs must be unique (at least among 1000 attempts)."""
        seen = set()
        for _ in range(1000):
            sid = generate_session_id()
            assert sid not in seen, f"Duplicate: {sid}"
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
        assert risk["label"] == "Brandrisk"  # whitespace stripped

    def test_empty_label_stripped(self):
        risk = create_new_risk(2, "   ")
        assert risk["label"] == ""


# ---------------------------------------------------------------------------
# compute_risk_stats
# ---------------------------------------------------------------------------


class TestComputeRiskStats:
    def _make_risk(self, votes=None, revealed=False, locked=False, final_prob=None, final_cons=None, label="Testrisk"):
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
        stats = compute_risk_stats(risk, threshold=4)
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
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["vote_count"] == 2
        assert stats["revealed"] is False
        # Averages must be hidden while not revealed
        assert stats["avg_probability"] is None
        assert stats["cell_counts"] == {}

    def test_votes_revealed_at_threshold(self):
        """When votes >= threshold: threshold_reached=True, the caller sets revealed=True."""
        votes = {
            "a": {"probability": 2, "consequence": 3, "updated_at": 0},
            "b": {"probability": 3, "consequence": 2, "updated_at": 0},
            "c": {"probability": 4, "consequence": 4, "updated_at": 0},
            "d": {"probability": 1, "consequence": 1, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["vote_count"] == 4
        assert stats["threshold_reached"] is True
        # Before the caller updates revealed: revealed is still False in stats
        assert stats["revealed"] is False

        # Simulate what build_client_payload does: set revealed=True on threshold_reached
        risk["revealed"] = True
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["revealed"] is True
        assert stats["threshold_reached"] is False  # already revealed
        assert stats["avg_probability"] == 2.5
        assert stats["avg_consequence"] == 2.5
        assert stats["suggested_probability"] == 3  # .5 rounds up
        assert stats["suggested_consequence"] == 3

    def test_cell_counts(self):
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 2, "consequence": 2, "updated_at": 0},
            "c": {"probability": 3, "consequence": 1, "updated_at": 0},
            "d": {"probability": 4, "consequence": 4, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, threshold=4)
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
        stats = compute_risk_stats(risk, threshold=4)
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
        """If final_probability is set, it must take precedence over the suggestion."""
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
        stats = compute_risk_stats(risk, threshold=4)
        # Averages become 1.5/1.5 -> suggestion 2/2, but final is 4/4
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
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["score"] == 6
        assert stats["level"] == "Medel"
        assert stats["color"] == "yellow"

    def test_threshold_auto_reveals(self):
        """When the vote count >= threshold, threshold_reached must be True.

        compute_risk_stats is now a pure function – no side effect on risk['revealed'].
        The caller (build_client_payload) is responsible for updating revealed.
        """
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
            "b": {"probability": 3, "consequence": 3, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        assert risk["revealed"] is False
        stats = compute_risk_stats(risk, threshold=2)
        # threshold_reached must be True, but risk['revealed'] must NOT have changed
        assert stats["threshold_reached"] is True
        assert risk["revealed"] is False  # pure function – no side effect
        assert stats["revealed"] is False  # is_revealed is based on risk['revealed']

    def test_no_side_effect_on_risk(self):
        """compute_risk_stats must not mutate the risk dict at all."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=False, locked=False)
        original = {k: v for k, v in risk.items() if k != "votes"}
        original_votes = dict(risk["votes"])
        compute_risk_stats(risk, threshold=1)
        # No change to risk after the call
        for k, v in original.items():
            assert risk[k] == v, f"risk['{k}'] changed: {risk[k]!r} != {v!r}"
        assert risk["votes"] == original_votes

    def test_threshold_not_reached_when_already_revealed(self):
        """threshold_reached must be False if the risk is already revealed."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes, revealed=True)
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["threshold_reached"] is False

    def test_threshold_not_reached_below_threshold(self):
        """threshold_reached must be False when votes < threshold."""
        votes = {
            "a": {"probability": 2, "consequence": 2, "updated_at": 0},
        }
        risk = self._make_risk(votes=votes)
        stats = compute_risk_stats(risk, threshold=4)
        assert stats["threshold_reached"] is False

    def test_threshold_not_reached_no_votes(self):
        """threshold_reached must be False when there are no votes."""
        risk = self._make_risk()
        stats = compute_risk_stats(risk, threshold=1)
        assert stats["threshold_reached"] is False


# ---------------------------------------------------------------------------
# Threshold semantics (auto-reveal at exactly N votes)
# ---------------------------------------------------------------------------


class TestThresholdSemantics:
    """The vote threshold is the exact auto-reveal count and is never lowered
    to match the number of connected participants.

    Regression: get_effective_threshold() used to compute
    min(threshold, connected participants), so the first participant to connect
    and vote revealed the result immediately – before the rest of the room
    had even joined.
    """

    def test_get_session_threshold_ignores_connected_participants(self, make_session):
        from app import get_session_threshold

        assert get_session_threshold(make_session(threshold=4)) == 4
        assert get_session_threshold(make_session(threshold=1)) == 1

    def test_two_votes_do_not_reveal_at_threshold_four(self, make_session):
        from app import compute_risk_stats

        session = make_session(threshold=4, votes=[(2, 2), (3, 3)])
        stats = compute_risk_stats(session["risks"][0], threshold=4)
        assert stats["threshold_reached"] is False
        assert stats["revealed"] is False

    def test_build_client_payload_does_not_lower_threshold(self, make_session):
        from app import ConnectionInfo, manager

        session = make_session(sid="THRESH1", threshold=4, votes=[(2, 2), (3, 3)])
        sid = session["session_id"]
        manager.connections[sid] = [
            ConnectionInfo(websocket=None, role="participant", client_id="p1", is_admin=False),  # type: ignore
            ConnectionInfo(websocket=None, role="participant", client_id="p2", is_admin=False),  # type: ignore
        ]
        try:
            payload = manager.build_client_payload(session)
            assert payload["threshold"] == 4
            assert payload["risks"][0]["revealed"] is False
            assert session["risks"][0]["revealed"] is False
        finally:
            manager.connections.pop(sid, None)

    def test_reveal_still_happens_at_exact_threshold(self, make_session):
        from app import compute_risk_stats

        votes = [(2, 2), (3, 3), (1, 4), (4, 1)]
        session = make_session(threshold=4, votes=votes)
        stats = compute_risk_stats(session["risks"][0], threshold=4)
        assert stats["threshold_reached"] is True


# ---------------------------------------------------------------------------
# Cell meta in the session payload (fas 7.2 – server is the single source of
# risk level/color so the frontend does not duplicate the thresholds)
# ---------------------------------------------------------------------------


class TestCellMetaPayload:
    def test_payload_contains_all_16_cells_matching_server_risk_levels(self, make_session):
        from app import get_risk_level, manager

        payload = manager.build_client_payload(make_session())
        cell_meta = payload["cell_meta"]
        assert len(cell_meta) == 16
        for p in range(1, 5):
            for c in range(1, 5):
                meta = cell_meta[f"{p}_{c}"]
                expected = get_risk_level(p * c)
                assert meta["score"] == p * c
                assert meta["level"] == expected["level"]
                assert meta["color"] == expected["color"]

    def test_payload_defaults_qr_visible_false(self, make_session):
        from app import manager

        payload = manager.build_client_payload(make_session())
        assert payload["qr_visible"] is False
