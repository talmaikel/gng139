import base64
import json

import pytest

from app.openai_pipeline import PipelineError
from app.tel_aviv import (
    TARGETS,
    TelAvivArchiveCollector,
    TimingReport,
    build_pre_review_dossier,
    current_status_assessment,
    finalize_reviewed_dossier,
    is_relevant,
)


def manifest(documents=None):
    return {
        "city": "tel-aviv", "address": TARGETS[25]["address"], "house_number": 25,
        "street_code": 481, "building_file_number": "04810250",
        "parcels": [{"gush": 6111, "parcel": 899}],
        "source_url": "https://handasa.tel-aviv.gov.il/Pages/SearchResultsAnonPageNew.aspx?partialAddress=481_25",
        "retrieved_at": "2026-09-10T10:00:00+00:00", "collector": "playwright-msedge",
        "documents": documents or [],
    }


def test_target_identity_and_relevant_document_filter():
    assert TARGETS[23]["file_number"] == "04810230"
    assert TARGETS[23]["parcels"] == [(6111, 360), (6111, 375)]
    assert is_relevant("היתר-תכנית חתומה")
    assert is_relevant("מסמכים הנדסיים תמא 38")
    assert not is_relevant("הודעת שומה על היטל השבחה")
    assert not is_relevant("מכתבים/פניות,תכתובת פנימית,אחר")


def test_municipal_api_file_envelope_is_unwrapped():
    raw = b"%PDF-test"
    envelope = json.dumps(json.dumps({"fileName": "source.pdf", "buffer": base64.b64encode(raw).decode(), "Msg": None})).encode()
    data, filename = TelAvivArchiveCollector()._unwrap_api_file(envelope)
    assert data == raw
    assert filename == "source.pdf"


def test_current_permit_blocks_a_new_opportunity():
    docs = [{"document_id": "x", "document_type": "היתר (תכנית ומילולי) חתום דיגיטלית", "document_date": "9/7/2024", "request_number": "20220930"}]
    result = current_status_assessment(manifest(docs))
    assert result["status"] == "not_suitable_currently"
    assert result["evidence_document_ids"] == ["x"]


def test_pre_review_dossier_is_city_specific_and_not_final():
    draft = build_pre_review_dossier(manifest(), {"documents": [], "candidates": []})
    assert draft["city"] == "tel-aviv"
    assert draft["rule_version"].startswith("tel-aviv-")
    assert draft["status"] == "needs_verification"
    assert draft["human_review"]["state"] == "pending"
    assert "herzliya" not in draft["rule_version"]


def test_finalization_refuses_pending_human_review():
    draft = build_pre_review_dossier(manifest(), {"documents": [], "candidates": []})
    with pytest.raises(PipelineError, match="pending"):
        finalize_reviewed_dossier(draft, {"candidates": [{"approved": None}]})


def test_finalization_is_content_addressed_after_review():
    docs = [{"document_id": "doc", "document_type": "היתר-תכנית חתומה", "viewer_url": "https://handasa.tel-aviv.gov.il/API/Pages/DocViewer.aspx?id=doc", "document_date": "1/1/1960", "request_number": "", "download": {"state": "cached"}}]
    report = {"documents": [{"document_id": "doc", "state": "completed"}], "candidates": []}
    draft = build_pre_review_dossier(manifest(docs), report)
    decisions = {"candidates": [{"id": "c", "approved": True, "field": "units", "proposed_value": "8", "correction": None, "document_id": "doc", "page": 1, "tile": "p1", "quote": "8 יחד"}]}
    final = finalize_reviewed_dossier(draft, decisions)
    assert final["fields"]["units"]["value"] == 8
    assert final["fields"]["units"]["certainty"] == "manually_verified"
    assert len(final["id"]) == 24
