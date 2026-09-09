"""Create a human-review packet from local OCR; it never auto-accepts facts."""
import html
import hashlib
import json
from pathlib import Path

from .rules import evidence
from .sources import utcnow


def _candidate(field, label, proposed, tile, visual_location, ocr_excerpt, note):
    return {
        "field": field, "label": label, "proposed_value": proposed,
        "status": "needs_human_confirmation", "certainty": "ocr_candidate",
        "tile": tile, "visual_location": visual_location,
        "ocr_excerpt": ocr_excerpt, "note": note,
    }


def hashoshanim_review_candidates():
    """Candidates transcribed from the visible permit form and its OCR evidence."""
    return [
        _candidate("address", "כתובת", "השושנים, הרצליה", "p1-r1-c11", "כותרת הטופס, שורת המיקום", "השושנים … הרצליה", "יש לאשר את מספר הבית ממקור הארכיון."),
        _candidate("gush", "גוש", "6529", "p1-r1-c11", "כותרת הטופס, עמודת גוש", "6529", "נראה בבירור; נדרש סימון אנושי לפני קליטה."),
        _candidate("parcel", "חלקה", "167", "p1-r1-c11", "כותרת הטופס, עמודת חלקה", "167", "נראה בבירור; נדרש סימון אנושי לפני קליטה."),
        _candidate("permit_date", "תאריך", "1970-04-12", "p1-r1-c11", "תחתית העמוד, חתימת מתכנן", "12.4.70", "הומר לפורמט ISO; יש לאשר שהחתימה היא תאריך ההיתר ולא תאריך התכנית."),
        _candidate("units", "יחידות דיור", "6", "p1-r1-c11", "טבלת 'השימוש בבניין', שורת סך הכול", "6", "ספירה חזותית; ה־OCR עצמו אינו אמין לטבלה זו."),
        _candidate("residential_floors", "קומות מגורים", "3", "p1-r1-c11", "טבלת שטח כולל של בניין: א׳, ב׳, ג׳", "187.97 × 3", "יש לאשר ששלוש השורות הן קומות מגורים."),
        _candidate("pilotis_area_m2", "שטח 148.50 מ״ר — סיווג השורה", "148.50", "p1-r1-c11", "טבלת שטח כולל של בניין, שורה מסומנת", "148.50", "אין להניח שמדובר בקומת עמודים. יש לזהות את כותרת השורה."),
        _candidate("main_residential_area_per_floor_m2", "שטח מגורים לקומה", "187.97", "p1-r1-c11", "טבלת שטח כולל של בניין, שלוש שורות מגורים", "187.97", "יש לאשר מול כותרת העמודה."),
        _candidate("stair_area_m2", "שטח חדר מדרגות", "14.68", "p1-r1-c11", "טבלת חלקי בניין אחרים", "14.68", "יש לאשר שהערך מיוחס לחדר מדרגות."),
        _candidate("shelter_area_m2", "שטח מקלט", "21.00", "p1-r1-c11", "טבלת מבנה הבניין / שטחים", "21.00", "יש לאשר את שיוך השטח למקלט."),
        _candidate("original_total_area_m2", "סך שטחים בהיתר", "748.09", "p1-r1-c11", "שורת סך הכול בטבלת השטחים", "748.09", "יש לאשר שהסך כולל את כל השורות הרלוונטיות."),
        _candidate("original_permit_number", "מספר היתר", None, "p1-r1-c11", "לא זוהה בטופס זה", "לא חולץ", "לא לקלוט. יש לבדוק בעמוד ההיתר או ברשומת הארכיון, שם הערך המאומת הוא 99."),
    ]


def build_review_packet(ocr_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = hashoshanim_review_candidates()
    packet = {
        "document": str(ocr_dir.parent.parent / "verification" / "hashoshanim-4" / "1970-plan.pdf"),
        "ocr_result": str(ocr_dir / "result.json"),
        "purpose": "Human confirmation before writing facts to the dossier database",
        "accepted_automatically": [],
        "candidates": candidates,
    }
    json_path = output_dir / "hashoshanim-4-ocr-human-review.json"
    json_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['label'])}</td><td>{html.escape(str(item['proposed_value'] or 'לא חולץ'))}</td>"
        f"<td>{html.escape(item['visual_location'])}<br><small>{html.escape(item['ocr_excerpt'])}</small></td>"
        f"<td>{html.escape(item['note'])}</td>"
        "<td><label><input type='radio' name='" + html.escape(item['field']) + "' value='approve'> מאשר/ת</label> "
        "<label><input type='radio' name='" + html.escape(item['field']) + "' value='reject'> דוחה</label><br>"
        "<input class='note' placeholder='תיקון או הערה'></td></tr>"
        for item in candidates
    )
    image = "../data/experiments/hashoshanim-4-1970-plan-local-ocr/tiles/p1-r1-c11.jpg"
    html_path = output_dir / "hashoshanim-4-ocr-human-review.html"
    html_path.write_text(f"""<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'>
<title>בדיקה אנושית — השושנים 4</title><style>
body{{font-family:Arial,sans-serif;max-width:1300px;margin:32px auto;background:#f5f7f5;color:#17231e;padding:0 20px;line-height:1.5}}h1{{margin-bottom:4px}}.warning{{background:#fff4dd;border:1px solid #d8bd78;padding:14px;border-radius:6px}}table{{border-collapse:collapse;width:100%;background:#fff;margin:24px 0}}th,td{{border:1px solid #ccd5cf;padding:10px;vertical-align:top;text-align:right}}th{{background:#e5ede6}}small{{color:#57665e}}.note{{width:95%;margin-top:8px}}img{{max-width:100%;border:1px solid #7d897f}}button{{padding:10px 15px;font:inherit}}@media print{{button{{display:none}}body{{margin:0}}}}</style>
<h1>בדיקה אנושית: השושנים 4, הרצליה</h1><p>מקור: תכנית היתר 1970. OCR מקומי בלבד, ללא API וללא עלות.</p>
<div class='warning'><b>לא נכתב אף ערך למסד הנתונים.</b> כל השורות ממתינות לאישור אנושי מול תמונת המקור. לאחר סימון, שמרי/הדפיסי ל־PDF ושלחי לי את התיקונים.</div>
<h2>ערכים מוצעים לבדיקה</h2><table><thead><tr><th>שדה</th><th>ערך מוצע</th><th>מיקום ו־OCR</th><th>הערה</th><th>החלטת בודק/ת</th></tr></thead><tbody>{rows}</tbody></table>
<button onclick='downloadDecisions()'>הורדת החלטות הבדיקה (JSON)</button> <button onclick='window.print()'>הדפסה / שמירה כ־PDF</button>
<script>function downloadDecisions(){{const rows={json.dumps(candidates, ensure_ascii=False)};const decisions=rows.map(x=>{{const selected=document.querySelector(`input[name="${{x.field}}"]:checked`);const notes=[...document.querySelectorAll(`input[name="${{x.field}}"]`)].map(e=>e.closest('td').querySelector('.note')).filter(Boolean);return {{field:x.field,proposed_value:x.proposed_value,decision:selected?selected.value:'pending',note:notes[0]?.value||''}}}});const blob=new Blob([JSON.stringify({{reviewed_document:'השושנים 4 — תכנית היתר 1970',decisions}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='hashoshanim-4-review-decisions.json';a.click();URL.revokeObjectURL(a.href);}}</script>
<h2>תמונת הראיה — אריח p1-r1-c11</h2><img src='{image}' alt='טופס היתר סרוק'><p><small>קובץ המכונה: {html.escape(str(json_path))}</small></p></html>""", encoding="utf-8")
    return {"json": json_path, "html": html_path, "candidates": len(candidates)}


def apply_hashoshanim_review(decision_file: Path, store):
    """Save an immutable reviewed dossier snapshot, retaining rejected OCR as a conflict."""
    from .hashoshanim import build_hashoshanim_dossier

    decision_data = json.loads(decision_file.read_text(encoding="utf-8"))
    decisions = {item["field"]: item for item in decision_data.get("decisions", [])}
    dossier = build_hashoshanim_dossier()
    original_id = dossier["id"]
    review_source = {
        "url": f"local-review://{decision_file.name}", "retrieved_at": utcnow(),
        "local_evidence": str(decision_file),
        "sha256": hashlib.sha256(decision_file.read_bytes()).hexdigest(),
    }
    mappings = {
        "address": ("address", lambda item: item["note"].strip() + ", הרצליה" if item.get("note", "").strip() else item["proposed_value"]),
        "permit_date": ("permit_date", lambda item: item["proposed_value"]),
        "units": ("units", lambda item: int(item["proposed_value"])),
        "residential_floors": ("residential_floors", lambda item: int(item["proposed_value"])),
        "main_residential_area_per_floor_m2": ("main_residential_area_per_floor", lambda item: float(item["proposed_value"])),
        "stair_area_m2": ("stair_area", lambda item: float(item["proposed_value"])),
        "shelter_area_m2": ("shelter_area", lambda item: float(item["proposed_value"])),
        "original_total_area_m2": ("original_permitted_total_area", lambda item: float(item["proposed_value"])),
    }
    accepted, rejected = [], []
    for review_key, (field_key, converter) in mappings.items():
        item = decisions.get(review_key)
        if not item or item.get("decision") != "approve" or item.get("proposed_value") is None:
            continue
        value = converter(item)
        dossier["fields"][field_key] = evidence(
            value, review_source, "manually_verified", f"אישור בודק/ת: {review_key}", "human review after local OCR"
        )
        accepted.append({"field": field_key, "value": value, "decision": "approve"})
    rejected_item = decisions.get("pilotis_area_m2")
    if rejected_item and rejected_item.get("decision") == "reject":
        prior = dossier["fields"].get("open_pilotis_area")
        dossier["fields"]["open_pilotis_area"] = {
            **evidence(None, certainty="conflict"),
            "observations": [prior, {**evidence(rejected_item.get("proposed_value"), review_source, "rejected", "p1-r1-c11", "human review"), "note": rejected_item.get("note", "")}],
        }
        dossier["rights_analysis"]["excluded_from_base"] = [
            row for row in dossier["rights_analysis"]["excluded_from_base"] if row["label"] != "קומת עמודים מפולשת"
        ]
        dossier["gaps"].insert(0, "שטח 148.50 מ״ר בתכנית לא סווג כקומת עמודים: הבודק/ת סימן/ה 'מרפסות'. נדרשת בדיקת כותרת הטבלה לפני שימוש בשטח.")
        rejected.append({"field": "open_pilotis_area", "decision": "reject", "note": rejected_item.get("note", "")})
    for key in ("gush", "parcel", "original_permit_number"):
        item = decisions.get(key)
        if item:
            (accepted if item.get("decision") == "approve" and item.get("proposed_value") is not None else rejected).append(
                {"field": key, "value": item.get("proposed_value"), "decision": item.get("decision"), "note": item.get("note", "")}
            )
    dossier["human_review"] = {"source": review_source, "base_snapshot_id": original_id, "accepted": accepted, "not_accepted_or_rejected": rejected}
    dossier["created_at"] = utcnow()
    stable = dict(dossier); stable.pop("created_at")
    dossier["id"] = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    store.save_dossier(dossier)
    return dossier
