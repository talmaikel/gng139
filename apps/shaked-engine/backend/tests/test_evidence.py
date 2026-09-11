import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.evidence import CONFLICT, Certainty, evidence, resolve_evidence, usable
from app.models.evidence import FieldEvidence

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def official(value, retrieved_at=NOW):
    return evidence(
        value, {"url": "https://example.org/source", "retrieved_at": retrieved_at.isoformat()}, Certainty.OFFICIAL, "page 1", "test"
    )


# ---- ported from POC/tests/test_core.py --------------------------------------


def test_conflicting_evidence_preserved():
    field = resolve_evidence([official(8), official(12)])
    assert field["certainty"] == CONFLICT and not usable(field, now=NOW)
    assert [o["value"] for o in field["observations"]] == [8, 12]


def test_missing_conflicting_community_and_stale_never_pass():
    for certainty in ["missing", CONFLICT, "community"]:
        field = official(5)
        field["certainty"] = certainty
        assert not usable(field, now=NOW)
    assert not usable(official(5, retrieved_at=NOW - timedelta(days=31)), now=NOW)


# ---- added with the port ---------------------------------------------------------


def test_machine_read_candidates_never_decide_until_reviewed():
    for certainty in [Certainty.OCR_CANDIDATE, Certainty.AI_CANDIDATE]:
        field = official(5)
        field["certainty"] = certainty.value
        assert not usable(field, now=NOW)
    reviewed = official(5)
    reviewed["certainty"] = Certainty.MANUALLY_VERIFIED.value
    assert usable(reviewed, now=NOW)


def test_agreeing_observations_resolve_to_the_value_and_keep_both():
    field = resolve_evidence([official(8), official(8)])
    assert field["value"] == 8 and usable(field, now=NOW) and len(field["observations"]) == 2


def test_no_observations_resolve_to_missing():
    field = resolve_evidence([evidence(None), evidence(None)])
    assert field["certainty"] == Certainty.MISSING.value and not usable(field, now=NOW)


def test_evidence_without_provenance_decides_nothing():
    no_location = official(5)
    no_location["location"] = None
    no_url = official(5)
    no_url["source"]["url"] = None
    naive_time = official(5)
    naive_time["source"]["retrieved_at"] = "2026-09-11T12:00:00"
    from_the_future = official(5, retrieved_at=NOW + timedelta(days=1))
    for field in [no_location, no_url, naive_time, from_the_future]:
        assert not usable(field, now=NOW)


def test_freshness_window_is_inclusive_up_to_its_edge():
    assert usable(official(5, retrieved_at=NOW - timedelta(days=30)), now=NOW)
    assert not usable(official(5, retrieved_at=NOW - timedelta(days=30, seconds=1)), now=NOW)


def test_stored_row_reads_back_as_an_observation_that_can_decide():
    row = FieldEvidence(
        field="parcel_area",
        value=742,
        certainty=Certainty.OFFICIAL,
        source_url="https://open.govmap.gov.il/geoserver/opendata/wfs",
        feature_url="https://open.govmap.gov.il/feature/Parcels_ITM.785443",
        retrieved_at=NOW - timedelta(days=1),
        source_updated_at="2026-08-31",
        content_sha256="ab" * 32,
        location="Parcels_ITM.785443.LEGAL_AREA",
        method="WFS",
    )
    observation = row.as_observation()
    assert observation["certainty"] == "official" and observation["source"]["sha256"] == "ab" * 32
    assert usable(observation, now=NOW)


def test_migration_certainties_match_the_code():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0002_field_evidence.py"
    spec = importlib.util.spec_from_file_location("migration_0002", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert set(migration.CERTAINTIES) == {c.value for c in Certainty}
