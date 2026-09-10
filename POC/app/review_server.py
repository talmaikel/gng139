"""Interactive human-review server for Tel Aviv OCR candidates.

Serves an editable table of every OCR candidate for the three David Hamelech
dossiers, with the source tile image next to each proposed value. Approve /
reject / correct decisions are written straight back into
``review-decisions.json`` so ``scripts/finalize_tel_aviv_dossiers.py`` can
run once every candidate has a decision. Nothing here auto-approves a value;
a human must look at the image and choose.
"""
import html
import json
import mimetypes
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import DATA
from .tel_aviv import TARGETS

ROOT = DATA / "cities" / "tel-aviv" / "david-hamelech"
DECISIONS_PATH = ROOT / "review" / "review-decisions.json"
_lock = Lock()

app = FastAPI(title="Tel Aviv OCR review")


def _load_decisions() -> dict:
    return json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))


def _save_decisions(payload: dict) -> None:
    tmp = DECISIONS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DECISIONS_PATH)


def _address_by_document_id() -> dict:
    mapping = {}
    for house in TARGETS:
        dossier_path = ROOT / str(house) / "pre-review-dossier.json"
        if not dossier_path.exists():
            continue
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
        address = dossier["fields"]["address"]["value"]
        for doc in dossier["documents"]:
            mapping[doc["id"]] = {"address": address, "house": house}
    return mapping


@app.get("/", response_class=HTMLResponse)
def index():
    decisions = _load_decisions()
    address_map = _address_by_document_id()
    candidates = decisions["candidates"]
    for row in candidates:
        info = address_map.get(row["document_id"], {})
        row["address"] = info.get("address", "?")
        row["house"] = info.get("house", 0)
    candidates.sort(key=lambda r: (r["house"], r["document_type"], r["page"], r["field"]))
    payload = json.dumps(candidates, ensure_ascii=False)
    return HTMLResponse(_PAGE.replace("__CANDIDATES__", payload))


@app.get("/image/{candidate_id}")
def image(candidate_id: str):
    decisions = _load_decisions()
    row = next((c for c in decisions["candidates"] if c["id"] == candidate_id), None)
    if row is None:
        raise HTTPException(404, "unknown candidate")
    path = Path(row["image"]).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        raise HTTPException(403, "image outside review root")
    if not path.exists():
        raise HTTPException(404, "image file missing on disk")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@app.post("/api/save")
def save(body: dict):
    updates = {row["id"]: row for row in body.get("decisions", [])}
    if not updates:
        raise HTTPException(400, "no decisions in request body")
    with _lock:
        decisions = _load_decisions()
        matched = 0
        for row in decisions["candidates"]:
            update = updates.get(row["id"])
            if update is None:
                continue
            row["approved"] = update.get("approved")
            row["correction"] = update.get("correction") or None
            matched += 1
        pending = sum(1 for row in decisions["candidates"] if row.get("approved") is None)
        decisions["state"] = "pending_human_review" if pending else "completed"
        _save_decisions(decisions)
    return JSONResponse({"ok": True, "matched": matched, "pending": pending, "total": len(decisions["candidates"])})


@app.get("/api/status")
def status():
    decisions = _load_decisions()
    total = len(decisions["candidates"])
    pending = sum(1 for row in decisions["candidates"] if row.get("approved") is None)
    approved = sum(1 for row in decisions["candidates"] if row.get("approved") is True)
    rejected = sum(1 for row in decisions["candidates"] if row.get("approved") is False)
    return {"total": total, "pending": pending, "approved": approved, "rejected": rejected}


_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>ביקורת OCR — דוד המלך 23, 25, 27</title>
<style>
:root{color-scheme:light}
body{font-family:Arial,sans-serif;margin:0;background:#f4f2ee;color:#14231f}
header{position:sticky;top:0;background:#14231f;color:#fff;padding:14px 20px;z-index:5;display:flex;gap:20px;align-items:center;flex-wrap:wrap}
header h1{font-size:18px;margin:0}
#progress{font-size:14px}
#progress b{color:#ffd27a}
.filters{display:flex;gap:8px;margin-inline-start:auto;flex-wrap:wrap}
.filters button{background:#2c4038;color:#fff;border:1px solid #45594f;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px}
.filters button.active{background:#70412c;border-color:#70412c}
main{padding:16px}
.card{background:#fff;border:1px solid #d9d3c8;border-radius:8px;margin-bottom:10px;padding:12px 14px;display:grid;grid-template-columns:120px 1fr 260px;gap:14px;align-items:start}
.card.decided{opacity:.55}
.card .thumb{width:120px;cursor:zoom-in;border:1px solid #ccc;border-radius:4px}
.meta{font-size:12px;color:#6b6357;margin-bottom:4px}
.field{font-weight:bold;font-size:14px}
.field-help{font-size:11px;color:#8a8272;font-weight:normal;margin-inline-start:6px}
.value{font-size:15px;margin:2px 0 6px}
.quote{font-size:12px;color:#3f463f;background:#f7f5f0;border-inline-start:3px solid #70412c;padding:6px 8px;border-radius:2px;white-space:pre-wrap}
.decide{display:flex;flex-direction:column;gap:6px}
.decide .row{display:flex;gap:6px}
.decide button{flex:1;border-radius:6px;border:1px solid #bbb;padding:6px 4px;cursor:pointer;font-size:13px;background:#fff}
.decide button.approve.sel{background:#25633c;color:#fff;border-color:#25633c}
.decide button.reject.sel{background:#9c3b2e;color:#fff;border-color:#9c3b2e}
.decide input{padding:5px;border:1px solid #bbb;border-radius:6px;font-size:13px}
.saved-tick{font-size:11px;color:#25633c;visibility:hidden}
.house-h{margin:18px 0 8px;font-size:16px;border-bottom:2px solid #70412c;padding-bottom:4px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:20}
#lightbox img{max-width:92%;max-height:92%}
</style></head>
<body>
<header>
  <h1>ביקורת OCR — דוד המלך 23, 25, 27</h1>
  <div id="progress">נבדקו <b id="p-done">0</b> מתוך <b id="p-total">0</b> (<span id="p-approved">0</span> אושרו, <span id="p-rejected">0</span> נדחו)</div>
  <div class="filters">
    <button data-filter="pending" class="active">ממתינים</button>
    <button data-filter="approved">אושרו</button>
    <button data-filter="rejected">נדחו</button>
    <button data-filter="all">הכל</button>
  </div>
</header>
<main id="list"></main>
<div id="lightbox"><img id="lightbox-img"></div>
<script>
const CANDIDATES = __CANDIDATES__;
const houseLabel = {23:"דוד המלך 23", 25:"דוד המלך 25", 27:"דוד המלך 27"};
const FIELD_LABEL = {
  permit_date: "תאריך היתר/בקשה",
  units: "מספר יחידות דיור",
  floors: "מספר קומות",
  area_m2: "שטח (מ״ר)",
  permit_number: "מספר היתר",
};
const FIELD_HELP = {
  permit_date: "תאריך שנמצא בהקשר של הגשה, אישור ועדה או תחילת עבודה. ייתכנו כמה תאריכים באותו מסמך (הגשה מול אישור) — יש לוודא לאיזה שלב הוא מתייחס.",
  units: "מספר יחידות הדיור (דירות) שנמצא סמוך למילה 'יח״ד'/'דירות'. ההקשר עלול לערבב בין מצב קיים, מבוקש ומותר לפי תוכנית — יש לבדוק זאת בתמונה.",
  floors: "מספר קומות שנמצא סמוך למילה 'קומות'/'קומה'. עלול להתייחס לבניין קיים, לבניין המבוקש או למספר מותר לפי תב״ע — יש לוודא הקשר בתמונה.",
  area_m2: "שטח במ״ר שנמצא סמוך למילה 'שטח'. עלול להיות שטח מגרש, שטח בנייה כולל או שטח יחידה בודדת — אין להסתמך על הערך בלי לבדוק לאיזה שטח הוא מתייחס.",
  permit_number: "המספר הרשמי של ההיתר/הבקשה כפי שמופיע במסמך.",
};
const FIELD_HELP_DEFAULT = "ערך שחולץ אוטומטית מה-OCR לפי דפוס טקסט קרוב; יש לאמת מול התמונה לפני אישור.";
let filter = "pending";

function counts(){
  const total = CANDIDATES.length;
  const approved = CANDIDATES.filter(c=>c.approved===true).length;
  const rejected = CANDIDATES.filter(c=>c.approved===false).length;
  const pending = total - approved - rejected;
  document.getElementById("p-total").textContent = total;
  document.getElementById("p-done").textContent = approved + rejected;
  document.getElementById("p-approved").textContent = approved;
  document.getElementById("p-rejected").textContent = rejected;
}

function matches(c){
  if (filter === "all") return true;
  if (filter === "pending") return c.approved === null || c.approved === undefined;
  if (filter === "approved") return c.approved === true;
  if (filter === "rejected") return c.approved === false;
}

function render(){
  const list = document.getElementById("list");
  list.innerHTML = "";
  let lastHouse = null;
  for (const c of CANDIDATES){
    if (!matches(c)) continue;
    if (c.house !== lastHouse){
      const h = document.createElement("div");
      h.className = "house-h";
      h.textContent = (houseLabel[c.house] || c.address) + " — " + c.address;
      list.appendChild(h);
      lastHouse = c.house;
    }
    list.appendChild(card(c));
  }
  if (!list.children.length){
    const empty = document.createElement("p");
    empty.textContent = "אין רשומות בסינון הנוכחי.";
    list.appendChild(empty);
  }
}

function card(c){
  const el = document.createElement("div");
  el.className = "card" + (c.approved === null || c.approved === undefined ? "" : " decided");
  el.dataset.id = c.id;

  const img = document.createElement("img");
  img.className = "thumb";
  img.loading = "lazy";
  img.src = "/image/" + c.id;
  img.onclick = () => openLightbox(img.src);
  el.appendChild(img);

  const mid = document.createElement("div");
  const label = FIELD_LABEL[c.field] || c.field;
  const help = FIELD_HELP[c.field] || FIELD_HELP_DEFAULT;
  mid.innerHTML = `<div class="meta">${escapeHtml(c.document_type)} · עמוד ${c.page} · אריח ${escapeHtml(c.tile)}</div>
    <div class="field">${escapeHtml(label)} <span class="field-help">(${escapeHtml(c.field)}) — ${escapeHtml(help)}</span></div>
    <div class="value">ערך מוצע: <b>${escapeHtml(String(c.proposed_value))}</b></div>
    <div class="quote">${escapeHtml(c.quote)}</div>`;
  el.appendChild(mid);

  const decide = document.createElement("div");
  decide.className = "decide";
  const row = document.createElement("div");
  row.className = "row";
  const approveBtn = document.createElement("button");
  approveBtn.className = "approve" + (c.approved === true ? " sel" : "");
  approveBtn.textContent = "✓ אשר";
  const rejectBtn = document.createElement("button");
  rejectBtn.className = "reject" + (c.approved === false ? " sel" : "");
  rejectBtn.textContent = "✗ דחה";
  row.appendChild(approveBtn); row.appendChild(rejectBtn);
  decide.appendChild(row);

  const correction = document.createElement("input");
  correction.placeholder = "תיקון (אופציונלי)";
  correction.value = c.correction || "";
  decide.appendChild(correction);

  const tick = document.createElement("span");
  tick.className = "saved-tick";
  tick.textContent = "נשמר ✓";
  decide.appendChild(tick);

  el.appendChild(decide);

  const commit = (approved) => {
    c.approved = approved;
    c.correction = correction.value || null;
    approveBtn.classList.toggle("sel", approved === true);
    rejectBtn.classList.toggle("sel", approved === false);
    el.classList.toggle("decided", approved !== null);
    save(c, tick);
    counts();
    if (filter !== "all") render();
  };
  approveBtn.onclick = () => commit(true);
  rejectBtn.onclick = () => commit(false);
  correction.onchange = () => { c.correction = correction.value || null; save(c, tick); };

  return el;
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
}

let saveTimer = null;
function save(candidate, tick){
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    tick.style.visibility = "hidden";
    const res = await fetch("/api/save", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({decisions: [{id: candidate.id, approved: candidate.approved, correction: candidate.correction}]})
    });
    if (res.ok){ tick.style.visibility = "visible"; }
  }, 150);
}

function openLightbox(src){
  document.getElementById("lightbox-img").src = src;
  document.getElementById("lightbox").style.display = "flex";
}
document.getElementById("lightbox").onclick = () => { document.getElementById("lightbox").style.display = "none"; };

document.querySelectorAll(".filters button").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".filters button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filter = btn.dataset.filter;
    render();
  };
});

counts();
render();
</script>
</body></html>"""
