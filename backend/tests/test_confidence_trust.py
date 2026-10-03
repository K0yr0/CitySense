"""Confidence engine + contributor trust: the algorithm chart's scoring and feedback loop."""
from __future__ import annotations

import pytest

from backend.fusion import confidence as conf
from backend.fusion import trust

ANON = trust.DEFAULT_TRUST


def status(sev=(), misses=0, votes=()):
    a = conf.assess(sev, misses, votes)
    return conf.status_for(a.confidence, "candidate"), a


# ---------------------------------------------------------------------------- confidence engine


def test_single_report_is_a_candidate():
    s, a = status(votes=[(True, ANON)])
    assert s == "candidate"
    assert a.sensor_confidence is None and a.citizen_confidence == pytest.approx(a.confidence)


def test_a_few_reports_make_it_likely():
    assert status(votes=[(True, ANON)] * 3)[0] == "likely"


def test_crowd_alone_cannot_verify():
    s, a = status(votes=[(True, ANON)] * 100)
    assert s == "likely" and a.citizen_points == conf.CITIZEN_CAP and a.confidence < conf.VERIFIED_AT


def test_crowd_plus_one_vehicle_detection_verifies():
    """The verification loop: the next tram feels it and the incident becomes verified."""
    assert status(sev=[0.8], votes=[(True, ANON)] * 23)[0] == "verified"


def test_sensor_only_needs_several_rides():
    assert status(sev=[0.9])[0] == "candidate"
    assert status(sev=[0.9, 0.8])[0] == "likely"
    assert status(sev=[0.9, 0.8, 0.9])[0] == "verified"


def test_clean_passes_lower_confidence_until_dismissed():
    votes = [(True, ANON)] * 3
    confidences = [conf.assess([], misses, votes).confidence for misses in range(7)]
    assert confidences == sorted(confidences, reverse=True)
    assert status(misses=1, votes=votes)[0] == "candidate"
    assert status(misses=6, votes=votes)[0] == "dismissed"


def test_no_answers_count_against_and_can_dismiss():
    assert conf.citizen_points([(True, ANON), (False, ANON)]) == pytest.approx(0.0)
    assert status(votes=[(True, ANON)] + [(False, ANON)] * 3)[0] == "dismissed"


def test_severity_weights_hits():
    assert conf.sensor_points([1.0], 0) == pytest.approx(conf.SENSOR_HIT)
    assert conf.sensor_points([0.0], 0) == pytest.approx(conf.SENSOR_HIT / 2)
    assert conf.sensor_points([5.0, -1.0], 0) == pytest.approx(1.5 * conf.SENSOR_HIT)  # clamped


def test_trusted_contributors_weigh_more():
    assert conf.trust_weight(0.5) == 1.0 and conf.trust_weight(1.0) == 2.0 and conf.trust_weight(0.0) == 0.0
    assert conf.citizen_points([(True, 0.9)]) > conf.citizen_points([(True, 0.6)]) > conf.citizen_points([(True, 0.2)])


def test_status_thresholds_and_terminal_states():
    assert conf.status_for(conf.VERIFIED_AT, "likely") == "verified"
    assert conf.status_for(conf.LIKELY_AT, "candidate") == "likely"
    assert conf.status_for(conf.LIKELY_AT - 1e-9, "likely") == "candidate"     # can fall back
    assert conf.status_for(conf.DISMISSED_BELOW - 1e-9, "likely") == "dismissed"
    for terminal in ("verified", "dismissed", "closed"):
        assert conf.status_for(0.5, terminal) == terminal


def test_no_evidence_means_prior():
    a = conf.assess([], 0, [])
    assert a.confidence == pytest.approx(conf.PRIOR)
    assert a.sensor_confidence is None and a.citizen_confidence is None


# ---------------------------------------------------------------------------- trust feedback loop


def test_trust_from_counts():
    assert trust.trust_from_counts(0, 0) == pytest.approx(0.6)
    assert trust.trust_from_counts(5, 0) == pytest.approx(0.8)
    assert trust.trust_from_counts(0, 3) == pytest.approx(0.375)
    assert trust.trust_from_counts(20, 0) > trust.trust_from_counts(5, 0) > trust.trust_from_counts(5, 5)


def test_trust_update_changes_future_answer_weight():
    """Chart: Contributor Trust Update -> affects future report weight."""
    newcomer = trust.trust_from_counts(0, 0)
    proven, unreliable = trust.trust_from_counts(8, 0), trust.trust_from_counts(0, 8)
    assert conf.citizen_points([(True, proven)]) > conf.citizen_points([(True, newcomer)])
    assert conf.citizen_points([(True, unreliable)]) < conf.citizen_points([(True, newcomer)]) / 2
    # one proven contributor answering NO outweighs one unreliable YES
    assert conf.citizen_points([(True, unreliable), (False, proven)]) < 0


def test_contributor_hash_is_salted_and_stable():
    h = trust.contributor_hash("browser-token-123")
    assert h == trust.contributor_hash("  browser-token-123 ") and len(h) == 64
    assert "browser-token-123" not in h and h != trust.contributor_hash("browser-token-124")


class Conn:
    def __init__(self, answers=None):
        self.answers, self.calls = answers or {}, []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def answer(self, conn, sql, params=None):
        self.calls.append((sql, params))
        a = self.answers.get(sql)
        return a(params) if callable(a) else a


@pytest.fixture
def conn(monkeypatch):
    c = Conn()
    monkeypatch.setattr(trust, "fetch_one", c.answer)
    monkeypatch.setattr(trust, "fetch_all", lambda cn, sql, params=None: c.answer(cn, sql, params) or [])
    return c


def test_contributor_for(conn):
    assert trust.contributor_for(conn, None) is None and trust.contributor_for(conn, "  ") is None
    with pytest.raises(ValueError):
        trust.contributor_for(conn, "x" * 500)
    conn.answers[trust.SQL_CONTRIBUTOR] = {"id": 7, "trust": 0.6, "correct": 0, "incorrect": 0}
    assert trust.contributor_for(conn, "token-abc")["id"] == 7
    assert conn.calls[-1][1] == {"hash": trust.contributor_hash("token-abc"), "trust": trust.DEFAULT_TRUST}


def test_record_vote_marks_late_answers_settled(conn):
    trust.record_vote(conn, 3, 7, True)
    trust.record_vote(conn, 3, 7, False, resolved=True)
    assert [p for s, p in conn.calls if s is trust.SQL_VOTE] == [
        {"incident_id": 3, "contributor_id": 7, "answer": True, "settled": False},
        {"incident_id": 3, "contributor_id": 7, "answer": False, "settled": True},   # no free trust points
    ]


def test_record_report_yes_known_and_anonymous(conn):
    conn.answers[trust.SQL_REPORT_CONTRIBUTOR] = lambda p: {"contributor_id": 7} if p["report_id"] == 1 else None
    trust.record_report_yes(conn, 3, 1)
    trust.record_report_yes(conn, 3, 2)
    assert [p for s, p in conn.calls if s is trust.SQL_REPORT_YES_KNOWN] == [
        {"incident_id": 3, "report_id": 1, "contributor_id": 7}]
    assert [p for s, p in conn.calls if s is trust.SQL_REPORT_YES_ANON] == [
        {"incident_id": 3, "report_id": 2, "contributor_id": None}]


def test_votes_and_settle(conn):
    conn.answers[trust.SQL_VOTES] = [{"answer": True, "trust": 0.8}, {"answer": False, "trust": 0.6}]
    assert trust.votes_for(conn, 3) == [(True, 0.8), (False, 0.6)]
    conn.answers[trust.SQL_SETTLE] = [{"id": 7}, {"id": 9}]
    assert trust.settle(conn, 3, real=False) == [7, 9]
    params = [p for s, p in conn.calls if s is trust.SQL_SETTLE][0]
    assert params == {"incident_id": 3, "real": False, "prior_correct": 3, "prior_incorrect": 2}
