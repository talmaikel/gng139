'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={step:'define',package:null,center:null,selectingCenter:false,job:null,config:null,dossiers:[],timer:null,investorDemo:location.pathname.replace(/\/$/,'')==='/investor-demo'};
const statusName={ready:'מוכן למסירה',eligible:'עומד בכללי חלופת שקד',ineligible:'אינו עומד בכללים',needs_verification:'דורש אימות',rejected:'אינו מתאים לפי הנתונים',screened_out:'נשמר מחוץ לתור',primary_candidate:'מועמד ראשי',filtered_landuse:'סונן לפי ייעוד',metro:'מסלול מטרו',preservation:'שימור',existing_renewal_plan:'תכנית התחדשות קיימת',urban_renewal_compound:'מתחם התחדשות עירונית',queued:'ממתין לסריקה',running:'איסוף מקורות',completed:'הסריקה הסתיימה',failed:'הסריקה לא הושלמה'};
const fieldNames={address:'כתובת',eligibility_summary:'מסקנת בדיקת הסף',building_file_number:'מספר תיק בניין',gush:'גוש',parcel:'חלקה',parcel_area:'שטח חלקה',footprint_area:'שטח טביעת מבנה',building_use:'שימוש עיקרי',units:'דירות בהיתר',floors:'קומות לפי הגדרת המדיניות',floor_configuration:'תצורת קומות',permit_date:'מועד היתר מקורי',original_permit_number:'מספר היתר מקורי',strengthened:'נמצא היתר חיזוק סיסמי',engineer_opinion:'חוות דעת מהנדס לתנאי הגיל',residential_zoning:'ייעוד למגורים',zoning_designation:'ייעוד רשום בתיק',residential_share:'שיעור מגורים חוקי',main_residential_area:'שטח מגורים עיקרי',service_area:'שטחי שירות',stair_area:'חדר מדרגות',open_pilotis_area:'קומת עמודים מפולשת',shelter_area:'מקלט',original_permitted_total_area:'סך שטחים בהיתר',post_2005_addition_area:'תוספת שירות מ-2013',planning_lot:'מגרש תכנוני',planning_basis:'בסיס תכנוני לתרחיש',overriding_plans_checked:'בדיקת תכניות גוברות',existing_legal_area:'בסיס שטח חוקי מעל הקרקע',shaked_area_cap:'תקרת שטח ראשונית לפי 400%',indicative_unit_range:'טווח יחידות אינדיקטיבי',indicative_additional_units:'תוספת יחידות אינדיקטיבית',additional_balcony_area:'מרפסות נוספות — תקרה',tama70_zone:'סיווג תמ״א 70'};
const certainty={official:'רשמי',derived:'נגזר',community:'מקור קהילתי',missing:'חסר',conflict:'סתירה',manually_verified:'מאומת ידנית',ocr_candidate:'מועמד OCR — דורש אימות'};
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
async function api(path,options={}){const response=await fetch('/api'+path,{headers:{'Content-Type':'application/json'},...options});if(!response.ok){const e=await response.json().catch(()=>({detail:response.statusText}));throw Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail));}return response.json();}
function guarded(fn){return async()=>{notice('');try{await fn();}catch(e){notice(e.message);}}}
/* Gush, parcel, file and permit numbers are identifiers, not quantities.
   A thousands separator in "גוש 6,529" reads as an error to anyone who works
   with these numbers, so they are formatted as plain digits. */
const ID_FIELDS=new Set(['gush','parcel','building_file_number','original_permit_number','planning_lot']);
function value(d,key){const v=d.fields[key]?.value;if(v===null||v===undefined)return '—';if(typeof v==='boolean')return v?'כן':'לא';if(ID_FIELDS.has(key))return String(v);if(key==='residential_share'&&typeof v==='number')return (v*100).toLocaleString('he-IL',{maximumFractionDigits:1})+'%';return typeof v==='number'?v.toLocaleString('he-IL',{maximumFractionDigits:2}):String(v);}
/* ---------- identity ------------------------------------------------------
   A property is identified by its address, and failing that by gush/parcel —
   the reference a developer actually uses. The OSM way id is provenance, not
   a name, so it never leads. */
function parcelRef(d){return (d.parcels||[]).filter(p=>p.gush&&p.parcel).map(p=>'גוש '+p.gush+' · חלקה '+p.parcel).join(' / ');}
function heading(d){const a=value(d,'address'),r=parcelRef(d);
  if(a!=='—')return {title:a,sub:r||'שיוך חלקה חסר'};
  if(r)return {title:r,sub:'כתובת טרם אומתה'};
  return {title:d.building_id,sub:'שיוך חלקה וכתובת חסרים'};}

/* ---------- completeness --------------------------------------------------
   Absence is the normal state early in a scan. Showing how much of the record
   is already sourced turns a wall of dashes into a position on a path. */
function completeness(d){const f=Object.values(d.fields||{});
  const sourced=f.filter(x=>x.certainty&&x.certainty!=='missing').length;
  return {sourced,total:f.length,gaps:(d.gaps||[]).length,pct:f.length?Math.round(sourced/f.length*100):0};}
function completenessBar(d){const c=completeness(d);
  return `<div class="completeness"><div class="bar"><span style="width:${c.pct}%"></span></div><small>${c.sourced} מתוך ${c.total} שדות עם מקור${c.gaps?` · ${c.gaps} פערים פתוחים`:''}</small></div>`;}

/* ---------- certainty -----------------------------------------------------
   The certainty grade is what this product sells, so it is encoded and not
   merely spelled. Conflict is deliberately the loudest of the seven: two
   sources disagreeing is the case the dossier exists to resolve. */
const certaintyTone={official:'high',manually_verified:'high',derived:'mid',community:'mid',ocr_candidate:'check',conflict:'conflict',missing:'none'};

/* The sources API returns a Hebrew status sentence and no machine-readable
   grade, so the badge tone is derived here. Move this to the API the day that
   field exists. Failure is tested first: "זמינה; שאילתות נכשלו" is a failure. */
function sourceTone(label){const t=String(label||'');
  if(/נכשל|לא הושלם|חסום|שגיאה/.test(t))return 'ineligible';
  if(/חלקי|קהילתי|לא ראיית/.test(t))return '';
  if(/אומת|נאסף|רשמי/.test(t))return 'eligible';
  return '';}

/* ---------- the dossier, in parts ----------------------------------------
   Five parts, matching the dossier the product promises: who it is, whether
   it passes, what stands there now, what the permit allowed, what that opens.
   A key the API adds later still renders, under "שדות נוספים". */
const FIELD_GROUPS=[
  {title:'זהות הנכס',keys:['address','gush','parcel','building_file_number','planning_lot']},
  {title:'הכרעת תנאי הסף',keys:['eligibility_summary','permit_date','original_permit_number','strengthened','engineer_opinion','residential_zoning','zoning_designation','residential_share','overriding_plans_checked','tama70_zone']},
  {title:'המבנה היום',keys:['parcel_area','footprint_area','building_use','units','floors','floor_configuration']},
  {title:'שטחים בהיתר',keys:['main_residential_area','service_area','stair_area','open_pilotis_area','shelter_area','original_permitted_total_area','post_2005_addition_area','existing_legal_area']},
  {title:'פוטנציאל ראשוני',keys:['planning_basis','shaked_area_cap','indicative_unit_range','indicative_additional_units','additional_balcony_area']}];
const EVIDENCE_HEAD='<thead><tr><th>נתון</th><th>ערך</th><th>ודאות</th><th>ראיה</th></tr></thead>';
function fieldRow(d,k){const f=d.fields[k],tone=certaintyTone[f.certainty]||'mid';
  return `<tr><td>${esc(fieldNames[k]||k)}</td><td>${esc(value(d,k))}</td><td><span class="cert cert-${tone}">${esc(certainty[f.certainty]||f.certainty)}</span></td><td>${f.source?`<a href="${esc(f.source.feature_url||f.source.url)}" target="_blank" rel="noopener">פתיחת מקור<span class="ext">↗</span></a><small class="ev-meta">${esc(f.location)} · ${esc(f.source.retrieved_at)}</small>`:'טרם נמצא מקור מספק'}</td></tr>`;}
function fieldGroup(title,keys,d){return `<section class="field-group"><h4>${esc(title)}<small>${keys.length}</small></h4><table class="evidence-table">${EVIDENCE_HEAD}<tbody>${keys.map(k=>fieldRow(d,k)).join('')}</tbody></table></section>`;}
/* One tall document forces the reader to scroll past what they did not ask
   for. The POC split the dossier into tabs — זיהוי, מצב קיים, תכנון והתאמה,
   מקורות ופערים — and that division still fits the fields exactly. Its
   "כלכלה ראשונית" tab is left out on purpose: this product does not compute
   feasibility, and an empty tab is worse than no tab. */
const DOSSIER_TABS=[{k:'id',n:'זיהוי'},{k:'exist',n:'מצב קיים'},
  {k:'plan',n:'תכנון והתאמה'},{k:'pot',n:'פוטנציאל'},{k:'src',n:'מקורות ואיכות מידע'}];
function groupsHTML(d,titles,used){const out=[];
  for(const g of FIELD_GROUPS){if(!titles.includes(g.title))continue;
    const keys=g.keys.filter(k=>d.fields[k]);keys.forEach(k=>used.add(k));
    if(keys.length)out.push(fieldGroup(g.title,keys,d));}
  return out.join('');}
function leftoverHTML(d,used){
  const rest=Object.keys(d.fields||{}).filter(k=>!used.has(k));
  return rest.length?fieldGroup('שדות נוספים',rest,d):'';}

/* ---------- map ↔ list ----------------------------------------------------
   A parcel on the map and its card are the same object; hovering either one
   should say so. */
const featureLayers={};
const BUILDING_STYLE={color:'#c45f28',weight:3,fillColor:'#ee985e',fillOpacity:.72};
const BUILDING_HOT={color:'#7A3A12',weight:5,fillColor:'#EC9A5F',fillOpacity:.9};
function highlightFeature(id,on){const l=featureLayers[id];if(!l)return;
  l.setStyle(on?BUILDING_HOT:BUILDING_STYLE);if(on)l.bringToFront();}
function highlightCard(id,on){const c=document.querySelector(`[data-card="${id}"]`);if(!c)return;
  c.classList.toggle('is-hot',on);if(on)c.scrollIntoView({block:'nearest',behavior:'smooth'});}
/* ---------- the four stages ----------------------------------------------
   Definition, purchase, scan, delivery. The commercial shape of the product,
   from the original POC: you mark an area and set conditions, you buy a
   package, the pipeline runs, and what it produced is handed over. */
const STEPS=[{k:'define',n:'הגדרה'},{k:'buy',n:'רכישה'},{k:'scan',n:'סריקה והפקה'},{k:'deliver',n:'מסירה'}];

/* The phases below are the collector's real progress marks, not decoration:
   5 scope, 15 parcels, 25 buildings, 25-90 per-building evidence, 100 assembly.
   Renaming them here without changing app/collector.py would make them theatre. */
const PIPELINE=[{to:5,n:'אימות הפוליגון והיקף הסריקה'},
  {to:15,n:'שליפת חלקות מ־GovMap'},
  {to:25,n:'איתור מבנים במרחב'},
  {to:90,n:'תיקי בניין, ראיות והכרעת כללים'},
  {to:100,n:'הרכבת תיקים ובדיקת מוכנות למסירה'}];

function paintSteps(){const i=STEPS.findIndex(s=>s.k===state.step);
  $('steps').innerHTML=STEPS.map((s,j)=>`<li class="${j===i?'on':(j<i?'done':'')}"`+
    `${j===i?' aria-current="step"':''}><i aria-hidden="true">${j+1}</i>${s.n}`+
    `${j<i?'<span class="sr-only"> — הושלם</span>':''}</li>`).join('');}
function setStep(k){state.step=k;paintSteps();
  STEPS.forEach(s=>{const el=$('stage-'+s.k);if(el)el.hidden=s.k!==k;});
  if(k==='define')map?.invalidateSize();
  window.scrollTo({top:0,behavior:'smooth'});}

function paintPipeline(progress,failed){
  const at=PIPELINE.find(p=>progress<p.to)||PIPELINE[PIPELINE.length-1];
  $('pipeline').setAttribute('aria-label',failed?'הסריקה נעצרה':`שלב נוכחי: ${at.n}, ${progress}%`);
  $('pipeline').innerHTML=PIPELINE.map((p,i)=>{const prev=i?PIPELINE[i-1].to:0;
    const cls=progress>=p.to?'done':(progress>=prev?'on':'');
    return `<li class="${failed&&cls==='on'?'failed':cls}"><i></i><span>${p.n}</span></li>`;}).join('');}

async function paintBuy(){const pack=await api('/package');
  state.package=pack;
  $('buy-balance').textContent=pack.remaining+' / 3';
  $('buy-existing').hidden=!(pack.remaining>0);
  $('buy-confirm').textContent=pack.remaining>0?'רכישת חבילה נוספת ←':'אישור ורכישה ←';
  const r=radius();
  $('buy-scope-note').textContent=state.center
    ? `מעגל ברדיוס ${r} מטר · כ-${(Math.PI*r*r/1000).toLocaleString('he-IL',{maximumFractionDigits:1})} דונם. זהות ההזדמנויות נחשפת רק לאחר הרכישה.`
    : 'טרם נבחר מרכז.';}
/* ---------- status --------------------------------------------------------
   Some dossiers carry eligibility_status, others only the eligibility object
   the checks produced. A record that passed every core check must not badge
   as "requires verification" merely because the flat field was never set. */
function statusOf(d){if(d.eligibility_status)return d.eligibility_status;
  const e=d.eligibility;
  if(e&&e.total_core_checks&&e.passed_count===e.total_core_checks)return 'eligible';
  return d.status;}
function passedNote(d){const e=d.eligibility;
  return e&&e.total_core_checks?`${e.passed_count} מתוך ${e.total_core_checks} תנאי סף עברו`:'';}

/* ---------- the same building, twice --------------------------------------
   A parcel scanned live and the same parcel delivered from preserved evidence
   arrive under different ids. Until the backend resolves them into one entity,
   the vault at least says so instead of showing two unrelated cards. */
function parcelIndex(rows){const m={};
  (rows||[]).forEach(d=>(d.parcels||[]).forEach(p=>{const k=p.gush+'/'+p.parcel;
    (m[k]=m[k]||new Set()).add(d.id);}));return m;}
function alsoOnParcel(d){const m=state.parcelIndex||{};
  return (d.parcels||[]).some(p=>(m[p.gush+'/'+p.parcel]||new Set()).size>1);}

/* ---------- finding one property in a full vault -------------------------- */
function vaultRows(){const q=($('vault-q')?.value||'').trim();
  if(!q)return state.dossiers;
  const digits=q.replace(/\D/g,'');
  return state.dossiers.filter(d=>{
    if([value(d,'address'),d.building_id,parcelRef(d)].join(' ').includes(q))return true;
    return digits.length>1&&(d.parcels||[]).some(p=>
      String(p.gush)===digits||String(p.parcel)===digits||String(p.gush)+String(p.parcel)===digits);});}
/* 300 cards is 36,000 pixels of page. Render a window of them and let the
   reader ask for more; the search field is the way to reach a specific one. */
const VAULT_PAGE=48;
function paintVault(more){const rows=vaultRows(),all=state.dossiers.length;
  const searching=!!($('vault-q')?.value||'').trim();
  state.vaultShown=more?(state.vaultShown||VAULT_PAGE)+VAULT_PAGE:VAULT_PAGE;
  const shown=rows.slice(0,state.vaultShown);
  $('vault').innerHTML=rows.length?cards(shown)+(rows.length>shown.length
    ?`<button class="secondary vault-more" id="vault-more">הצגת ${Math.min(VAULT_PAGE,rows.length-shown.length)} תיקים נוספים · ${shown.length} מתוך ${rows.length}</button>`:'')
    :(searching?'<div class="empty">אין תיק שתואם את החיפוש. אפשר לחפש לפי כתובת, מספר גוש, מספר חלקה או מזהה מבנה.</div>'
               :'<div class="empty">אין עדיין תיקים במאגר.</div>');
  $('vault-count').textContent=searching?`${rows.length} מתוך ${all}`:`${all} תיקים`;
  $('vault').removeAttribute('aria-busy');}
/* ---------- what was scanned and not delivered ----------------------------
   Only candidates that pass every rule are presented. Everything else the
   scan touched used to vanish, which leaves the one honest question — why is
   my building not here? — with no answer on screen. A check that came back
   without data is not a rejection, and the two are reported apart. */
/* ---------- building-file archive coverage --------------------------------
   Every check that blocks eligibility reads from the municipal building file.
   The API already reports how much of that archive is indexed; not showing it
   leaves "no source for this field" as the answer, when the actionable answer
   is "this area has not been indexed yet". */
function archiveTotals(a){const st=(a&&a.streets)||{};
  const n=k=>(st[k]&&st[k].count)||0;
  const done=n('complete'),pending=n('pending'),failed=n('failed');
  return {done,pending,failed,total:done+pending+failed,
          files:((a&&a.files&&a.files.metadata_complete)||0)};}
function archiveNote(){const t=archiveTotals(state.archive);
  if(!t.total)return 'ארכיון תיקי הבניין טרם נסרק במכונה הזו — אין רחובות באינדקס, ולכן אף שדה שמקורו בתיק בניין אינו זמין לסריקה חיה.';
  if(!state.archive.coverage_complete)return `ארכיון תיקי הבניין נסרק חלקית — ${t.done} רחובות הושלמו מתוך ${t.total}, ${t.files} תיקים עם מטא־דאטה מלאה.`;
  return '';}
/* ---------- per-dossier source attribution --------------------------------
   Source quality was a screen of its own, describing systems in the abstract.
   The question a reader actually has is narrower and better: for THIS
   property, what did each source contribute, and how far can I lean on it. */
const SOURCE_KEYS=[
  [/archive\.gis-net|gis-net\.co\.il/,'archive','ארכיון תיקי הבניין — סריקות'],
  [/complot/,'complot','ארכיון תיקי בניין — קומפלוט'],
  [/handasa\.herzliya|urbanrenewal/,'policy','מדיניות שקד — עיריית הרצליה'],
  [/govmap|opendata/,'govmap','GovMap — חלקות וגבול עירוני'],
  [/overpass|openstreetmap/,'osm','OpenStreetMap — מבנים לגילוי'],
  [/iplan|xplan/,'xplan','מנהל התכנון — XPlan'],
  [/v5\.gis-net|minisite/,'gis','GIS עיריית הרצליה']];
function sourceKey(url){const m=SOURCE_KEYS.find(([re])=>re.test(String(url||'')));
  return m?{key:m[1],name:m[2]}:{key:'other',name:'מקור נוסף'};}
function catalogueFor(key){return (state.sources||[]).find(s=>sourceKey(s.url).key===key)||null;}

/* Fields grouped by the source that produced them, with the certainty mix each
   one carries — the difference between "official" and "derived" is the whole
   question of what may be leaned on. */
function dossierSources(d){const by={};
  for(const [k,f] of Object.entries(d.fields||{})){
    if(!f.source)continue;
    const id=sourceKey(f.source.feature_url||f.source.url);
    const e=by[id.key]||(by[id.key]={key:id.key,name:id.name,count:0,cert:{},url:f.source.url,at:f.source.retrieved_at});
    e.count++; e.cert[f.certainty]=(e.cert[f.certainty]||0)+1;
    if(f.source.retrieved_at>e.at)e.at=f.source.retrieved_at;}
  return Object.values(by).sort((a,b)=>b.count-a.count);}

/* XPlan classification sat on the standalone sources screen. That screen is
   gone, so the city-wide snapshot status now travels with source quality in
   the dossier. The markup and wording are the XPlan commit's own. */
function xplanStatusHTML(){const x=state.xplanStatus;if(!x)return '';const xc=x.categories||{};
  return `<section class="xplan-status">`+(x.snapshot
    ?`<span class="section-index">XPLAN / SNAPSHOT מקומי</span><h5>${esc(x.screened_parcels)} חלקות סווגו</h5><p>${Object.entries(xc).map(([k,v])=>`${esc(statusName[k]||k)}: ${esc(v)}`).join(' · ')||'טרם סווגו חלקות'}</p><small>צילום מצב: ${esc(x.snapshot.id)} · ${esc(new Date(x.snapshot.created_at).toLocaleString('he-IL'))}</small>`
    :`<span class="section-index">XPLAN</span><h5>XPlan טרם סונכרן</h5><p>בריצה הראשונה יורד snapshot עירוני; כשל מקור אינו מסנן חלקות.</p>`)+`</section>`;}
function sourcesPanel(d){
  const used=dossierSources(d),total=Object.keys(d.fields||{}).length;
  const sourced=used.reduce((n,s)=>n+s.count,0);
  const unused=(state.sources||[]).filter(s=>!used.some(u=>u.key===sourceKey(s.url).key));
  const certOrder=['official','manually_verified','derived','community','ocr_candidate','conflict'];
  return `<h4 class="panel-h">מקורות שתרמו לתיק<small>${sourced} / ${total} שדות</small></h4>`+
    (used.length?`<div class="src-attrib">${used.map(s=>{const cat=catalogueFor(s.key);
      return `<article class="src-item"><div class="src-head"><h5>${esc(s.name)}</h5>`+
        (cat?`<span class="badge ${sourceTone(cat.status_label)}">${esc(cat.status_label)}</span>`:'')+
        `</div><div class="src-bar">${certOrder.filter(c=>s.cert[c]).map(c=>
          `<span class="cert cert-${certaintyTone[c]||'mid'}">${esc(certainty[c]||c)} ${s.cert[c]}</span>`).join('')}</div>`+
        `<div class="src-foot"><span class="mono">${esc(String(s.at).slice(0,10))}</span>`+
        `<a href="${esc(s.url)}" target="_blank" rel="noopener">פתיחת המקור<span class="ext">↗</span></a></div>`+
        `<b class="src-count">${s.count}</b></article>`;}).join('')}</div>`
      :'<p class="muted">אף שדה בתיק אינו נשען עדיין על מקור שנשלף.</p>')+
    (archiveNote()?`<p class="archive-note">${esc(archiveNote())}</p>`:'')+
    xplanStatusHTML()+
    (unused.length?`<h4 class="panel-h">מקורות שנבדקו ולא תרמו לתיק זה<small>${unused.length}</small></h4>`+
      `<ul class="src-unused">${unused.map(s=>`<li><span>${esc(s.name)}</span><span class="badge ${sourceTone(s.status_label)}">${esc(s.status_label)}</span></li>`).join('')}</ul>`:'')+
    `<p class="muted src-caveat">גישה למקור אינה הוכחה לשלמות המידע, ותאריך שליפה אינו תאריך עדכון המקור.</p>`;}
/* ---------- loading -------------------------------------------------------
   The app rendered empty and then snapped into place, and a dossier took about
   a second of nothing at all. A skeleton says "this shape is coming" and keeps
   the layout from jumping when it arrives. */
function skeletonCards(n){return Array.from({length:n},()=>
  `<article class="result is-skeleton" aria-hidden="true">
     <span class="sk sk-badge"></span><span class="sk sk-title"></span><span class="sk sk-sub"></span>
     <div class="result-meta"><div><span class="sk sk-num"></span></div><div><span class="sk sk-num"></span></div><div><span class="sk sk-num"></span></div></div>
     <span class="sk sk-bar"></span><span class="sk sk-line"></span><span class="sk sk-line sk-line2"></span>
     <span class="sk sk-btn"></span><span class="sk sk-id"></span>
   </article>`).join('');}
function skeletonDossier(){return `<div class="sk-panel" aria-hidden="true">
    <span class="sk sk-row"></span><span class="sk sk-row"></span><span class="sk sk-row"></span>
    <span class="sk sk-row"></span><span class="sk sk-row"></span></div>`;}
/* ---------- motion --------------------------------------------------------
   One switch governs every animation in the app, so "reduced motion" is a
   real setting and not a promise made in four places. */
const REDUCED=window.matchMedia('(prefers-reduced-motion:reduce)');
const animates=()=>!REDUCED.matches;

/* ---------- feedback ------------------------------------------------------
   notice() is the error channel and shouts (role=alert). Success is quieter
   by design: it states what happened, waits, and leaves. */
function toast(message,kind){
  const host=$('toasts');if(!host)return;
  const el=document.createElement('div');
  el.className='toast'+(kind?' toast-'+kind:'');
  el.setAttribute('role','status');
  el.textContent=message;
  host.appendChild(el);
  const life=kind==='work'?2600:4200;
  setTimeout(()=>{el.classList.add('out');
    setTimeout(()=>el.remove(),animates()?260:0);},life);}

/* Counting a figure up reads as a measurement settling; jumping reads as a
   repaint. Only whole numbers animate, and only when they actually change. */
function setStat(id,text){
  const el=$(id);if(!el)return;
  const to=Number(String(text).replace(/[^\d-]/g,''));
  const from=Number(String(el.textContent).replace(/[^\d-]/g,''));
  if(!animates()||!Number.isFinite(to)||!Number.isFinite(from)||from===to||/[\/]/.test(String(text))){
    el.textContent=text;return;}
  const t0=performance.now(),span=Math.min(620,220+Math.abs(to-from)*4);
  (function step(now){const k=Math.min(1,(now-t0)/span);
    const eased=1-Math.pow(1-k,3);
    el.textContent=String(Math.round(from+(to-from)*eased));
    if(k<1)requestAnimationFrame(step);else el.textContent=text;})(t0);}

/* The map moves rather than teleports, so the reader keeps their bearings. */
function moveTo(bounds,opts){if(!map)return;
  if(animates()&&map.flyToBounds)map.flyToBounds(bounds,Object.assign({duration:.7},opts));
  else map.fitBounds(bounds,opts);}
function checkTally(d){let unknown=0,failed=0;
  (d.checks||[]).forEach(c=>{if(c.status==='failed')failed++;else if(c.status!=='passed')unknown++;});
  return {unknown,failed};}
function blockingReason(d){const t=checkTally(d);
  if(t.failed)return `${t.failed} בדיקות נכשלו`;
  if(t.unknown)return `${t.unknown} בדיקות ללא נתון`;
  return 'לא נמסר';}
function commonGaps(rows,limit){const c={};
  rows.forEach(d=>(d.checks||[]).forEach(k=>{if(k.status!=='passed'&&k.label)c[k.label]=(c[k.label]||0)+1;}));
  return Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,limit);}

function paintUndelivered(result){
  const all=result.candidates||[],shown=new Set((result.presented||[]));
  const rest=all.filter(d=>!shown.has(d.id));
  const box=$('not-delivered');
  if(!rest.length){box.hidden=true;box.innerHTML='';return;}
  // Most complete first: an arbitrary cut hides the one building someone came
  // looking for. Ranking by how few checks are still open puts the candidates
  // nearest to a decision at the top, and every one of them is listed.
  rest.sort((a,b)=>{const x=checkTally(a),y=checkTally(b);
    return (x.failed-y.failed)||(x.unknown-y.unknown);});
  const top=commonGaps(rest,5),n=rest.length;
  const failedAny=rest.some(d=>checkTally(d).failed>0);
  box.hidden=false;
  box.innerHTML=`<h3>מועמדים שנסרקו ולא נמסרו<small>${n}</small></h3>`+
    `<p class="undelivered-why">${failedAny
      ?'חלק מהמועמדים נפסלו על כלל מפורש, וחלקם נעצרו על שדות שאין להם עדיין מקור.'
      :'אף מועמד לא נפסל על כלל. כולם נעצרו על שדות שהסריקה החיה לא הצליחה למלא — הנתונים האלה יושבים בתיק הבניין העירוני.'}</p>`+
    (archiveNote()?`<p class="archive-note">${esc(archiveNote())}</p>`:'')+
    `<ul class="gap-rank">${top.map(([label,count])=>
      `<li><span class="gr-label">${esc(label)}</span>`+
      `<span class="gr-track"><span class="gr-fill" style="width:${Math.round(count/n*100)}%"></span></span>`+
      `<b>${count} / ${n}</b></li>`).join('')}</ul>`+
    `<div class="undelivered-list">${rest.map(d=>{const h=heading(d);
      return `<button class="undelivered-row" data-dossier="${esc(d.id)}"><span class="u-name">${esc(h.title)}</span><span class="u-reason">${esc(blockingReason(d))}</span></button>`;}).join('')}</div>`+
    `<p class="muted">כל המועמדים נשמרו במאגר התיקים וניתן לחפש אותם שם לפי כתובת, גוש או חלקה.</p>`;}
let map,circleLayer,centerMarker,buildingLayer,historyLayer;
function radius(){return Number($('radius')?.value||150);}
function initMap(){if(!window.L){$('map-loading').textContent='קובצי המפה לא נטענו. בדקו את התקנת האפליקציה.';return;}map=L.map('map',{zoomControl:false}).setView([32.164,34.842],16);L.control.zoom({position:'bottomleft'}).addTo(map);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);buildingLayer=L.layerGroup().addTo(map);historyLayer=L.layerGroup().addTo(map);$('map-loading')?.remove();map.on('click',e=>{if(!state.selectingCenter)return;setCenter({lat:e.latlng.lat,lon:e.latlng.lng},true);});}
function setCenter(center,fit=false){state.center=center;state.selectingCenter=false;if(circleLayer)map?.removeLayer(circleLayer);if(centerMarker)map?.removeLayer(centerMarker);if(center&&map){const p=[center.lat,center.lon];circleLayer=L.circle(p,{radius:radius(),color:'#b95724',weight:2,fillOpacity:.12}).addTo(map);centerMarker=L.circleMarker(p,{radius:5,color:'#b95724',fillOpacity:1}).addTo(map);if(fit)moveTo(circleLayer.getBounds(),{padding:[35,35]});}$('polygon-status').textContent=center?`מרכז נבחר · רדיוס ${radius()} מטר · מוכן לסריקה`:'טרם נבחר מרכז';}
function cards(rows){if(!rows.length)return '<div class="empty">טרם נמצאו תיקים שעברו את כל הבדיקות. תיק חסר או סותר אינו מוצג כמתאים.</div>';return rows.map(d=>{const h=heading(d),st=statusOf(d),note=passedNote(d);return `<article class="result" data-card="${esc(d.id)}"><span class="badge ${esc(st)}">${esc(statusName[st]||st)}</span>${note?`<span class="passed-note">${esc(note)}</span>`:''}${alsoOnParcel(d)?'<span class="dup-note">תיק נוסף קיים על אותה חלקה</span>':''}<h3>${esc(h.title)}</h3><span class="muted">${esc(h.sub)}</span><div class="result-meta"><div><b>${esc(value(d,'parcel_area'))}</b><small>מ״ר חלקה</small></div><div><b>${esc(value(d,'units'))}</b><small>דירות בהיתר</small></div><div><b>${d.archive_records.length}</b><small>תיקי בניין</small></div></div>${completenessBar(d)}<p>${esc(d.gaps.slice(0,2).join(' · '))}</p><button class="secondary" data-dossier="${esc(d.id)}">עיון בתיק ובמקורות<span class="ext">↗</span></button><small class="src-id">${esc(d.building_id)}</small></article>`;}).join('');}
function demoCard(d){const rights=d.rights_analysis||{};return `<article class="result"><span class="badge demo-badge">6 מתוך 6 תנאי סף עברו</span><h3>${esc(value(d,'address'))}</h3><span class="muted">תיק בניין ${esc(value(d,'building_file_number'))} · גוש ${esc(value(d,'gush'))} · חלקה ${esc(value(d,'parcel'))}</span><div class="result-meta"><div><b>${esc(value(d,'parcel_area'))}</b><small>מ״ר חלקה</small></div><div><b>${esc(value(d,'units'))}</b><small>דירות קיימות</small></div><div><b>${esc(rights.indicative_whole_unit_range?.join('–')||'—')}</b><small>יחידות אינדיקטיביות</small></div></div><p>תקרת שטח ראשונית: ${esc(rights.maximum_total_above_ground_m2?.toLocaleString('he-IL')||'—')} מ״ר. נדרשת השלמת בדיקה תכנונית לפני מסירה.</p><button class="primary" data-dossier="${esc(d.id)}">פתיחת תיק הראיות המלא ←</button></article>`;}
function showBuildings(rows){if(!buildingLayer)return;buildingLayer.clearLayers();Object.keys(featureLayers).forEach(k=>delete featureLayers[k]);rows.forEach(d=>{if(state.investorDemo)d.parcels.filter(p=>p.geometry).forEach(p=>L.geoJSON(p.geometry,{style:{color:'#70412c',weight:3,dashArray:'7 5',fillColor:'#d99a68',fillOpacity:.17}}).addTo(buildingLayer));const layer=L.geoJSON(d.geometry,{style:BUILDING_STYLE}).bindTooltip(esc(heading(d).title),{permanent:state.investorDemo,direction:'top'}).addTo(buildingLayer);layer.on('click',()=>openDossier(d.id));layer.on('mouseover',()=>highlightCard(d.id,true));layer.on('mouseout',()=>highlightCard(d.id,false));featureLayers[d.id]=layer;});}
function dossierHighlights(d){if(!d.eligibility&&!d.rights_analysis)return '';const e=d.eligibility||{},r=d.rights_analysis||{};return `<section class="dossier-highlight"><strong>${esc(e.passed_count??'—')} מתוך ${esc(e.total_core_checks??'—')} תנאי סף של המבנה עברו</strong><p>${esc(e.conclusion||'')}</p><div class="rights-grid"><div><b>${esc(r.base_area_m2?.toLocaleString('he-IL')||'—')}</b><small>מ״ר בסיס חוקי</small></div><div><b>${esc(r.maximum_total_above_ground_m2?.toLocaleString('he-IL')||'—')}</b><small>מ״ר תקרה ראשונית</small></div><div><b>${esc(r.indicative_whole_unit_range?.join('–')||'—')}</b><small>יחידות אינדיקטיביות</small></div><div><b>${esc(r.indicative_additional_units?.join('–')||'—')}</b><small>תוספת יחידות</small></div></div></section>`;}
function xplanEvidence(d){const x=d.xplan_screening;if(!x)return '';const rows=(x.parcels||[]).flatMap(p=>p.matches||[]);return `<details class="evidence-details" open><summary>XPlan — ${esc(statusName[x.category]||x.category)}</summary><p class="muted">תגיות: ${esc((x.tags||[]).map(t=>statusName[t]||t).join(' · ')||'—')} · סף כיסוי: ${Math.round(((x.parcels||[])[0]?.threshold||.9)*100)}%</p>${rows.length?`<table class="evidence-table"><thead><tr><th>תכנית</th><th>ייעוד</th><th>כיסוי חלקה</th><th>סטטוס</th><th>מקור</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.pl_number||r.pl_id||'—')}</td><td>${esc(`${r.mavat_code??'—'} · ${r.mavat_name||'—'}`)}</td><td>${esc((r.overlap*100).toLocaleString('he-IL',{maximumFractionDigits:1}))}%</td><td>${r.approved?'מאושרת':'אינה מאושרת — אזהרה בלבד'}</td><td><a href="${esc(r.source_url)}" target="_blank" rel="noopener">שכבה 4, רשומה ${esc(r.objectid)}<span class="ext">↗</span></a></td></tr>`).join('')}</tbody></table>`:'<p>לא נמצאה התאמת ייעוד מספקת; החלקה נשארת לאימות.</p>'}${(x.warnings||[]).map(w=>`<p class="pilot-note">${esc(w)}</p>`).join('')}</details>`;}
/* A first-time reader lands on an empty map with no idea what to do. Say it
   once, on the define stage, and remove it the moment there is anything. */
function paintFirstRun(dossiers,jobs){const el=$('first-run');if(!el)return;
  el.hidden=!(dossiers.length===0&&jobs.length===0);}
async function refresh(){const [pack,dossiers,jobs]=await Promise.all([api('/package'),api('/dossiers'),api('/searches')]);
  paintFirstRun(dossiers,jobs);state.dossiers=dossiers;state.parcelIndex=parcelIndex(dossiers);$('balance').textContent=pack.remaining+' / 3';setStat('dossier-count',String(dossiers.length));setStat('ready-count',String(dossiers.filter(d=>d.status==='ready').length));paintVault();/* Past searches are a way back in, not a log to read. Five is enough. */
$('history-list').innerHTML=jobs.length?jobs.slice(0,5).map(j=>`<div class="history-row"><span>${esc(new Date(j.created_at).toLocaleString('he-IL'))}</span><span>${esc(statusName[j.state])}</span><button class="text-button" data-job="${j.id}">פתיחת חיפוש ←</button></div>`).join(''):'אין חיפושים עדיין';
  if(jobs.length>5)$('history-list').insertAdjacentHTML('beforeend',`<p class="muted history-rest">${jobs.length-5} חיפושים נוספים קודמים</p>`);}
async function poll(jid){clearTimeout(state.timer);state.job=jid;const job=await api('/searches/'+jid);$('job-panel').hidden=false;$('progress').value=job.progress;$('job-state').textContent=statusName[job.state];$('job-title').textContent=job.state==='completed'?'הבדיקה הסתיימה. מוצגים רק מועמדים שעברו את כל הכללים.':'בודקים מועמד אחד בכל פעם עד שלוש הצלחות';$('retry').hidden=!['failed','completed'].includes(job.state);paintPipeline(job.progress,job.state==='failed');const all=job.result.candidates||[];const rows=job.result.presented_candidates||[];$('results').innerHTML=cards(rows);showBuildings(rows);if(job.error){const h=humanError(job.error);$('job-summary').innerHTML=`${esc(h.headline)}<br><small class="err-raw">${esc(h.detail)}</small>`;}else $('job-summary').textContent=`${all.length} מועמדים עברו pipeline · ${rows.length} מתוך 3 נמצאו מתאימים · ${job.result.stop_reason==='radius_exhausted'?'כל המועמדים ברדיוס מוצו':'החיפוש ממשיך לפי הסדר האקראי'} · seed ${job.result.selection_seed??'—'}`;$('scan').disabled=['queued','running'].includes(job.state);
  const scanned=job.result||{};paintUndelivered(scanned);
  $('scanned').innerHTML=[['מבנים בתחום',scanned.building_count],['חלקות שנשלפו',scanned.parcel_count],['עברו את כל הכללים',rows.length+' / 3'],['מועמדים שנבדקו',all.length]].map(([k,v])=>`<div><small>${k}</small><b>${v??'—'}</b></div>`).join('');
  if(['queued','running'].includes(job.state)){state.timer=setTimeout(()=>poll(jid).catch(e=>notice(e.message)),1800);}
  else{await refresh();
    if(job.state==='completed'&&state.step==='scan'){
      toast(rows.length?`הסריקה הסתיימה · ${rows.length} מתוך 3 נמסרו`
                       :`הסריקה הסתיימה · ${all.length} מועמדים נבדקו, אף אחד לא עבר את כל הכללים`);
      setStep('deliver');}}}
async function openDossier(id){try{
    $('dossier-title').textContent='טוען תיק…';$('dossier-body').innerHTML=skeletonDossier();
    $('dossier-body').setAttribute('aria-busy','true');
    if(!$('dossier').open)$('dossier').showModal();
    const d=await api('/dossiers/'+id);$('dossier-title').textContent=heading(d).title;$('dossier-body').innerHTML=`<div class="dossier-actions"><span class="badge ${esc(statusOf(d))}">${esc(statusName[statusOf(d)]||statusOf(d))}</span><a class="secondary" href="/api/dossiers/${id}/export/pdf">הורדת PDF</a><a class="secondary" href="/api/dossiers/${id}/export/xlsx">הורדת Excel</a></div><p class="muted">${esc(d.selection_note)}<br>נוצר: ${esc(new Date(d.created_at).toLocaleString('he-IL'))} · כללים: ${esc(d.rule_version)}</p>${(()=>{const used=new Set();
  const panels={id:groupsHTML(d,['זהות הנכס'],used),
    exist:groupsHTML(d,['המבנה היום','שטחים בהיתר'],used),
    plan:groupsHTML(d,['הכרעת תנאי הסף'],used)+xplanEvidence(d),
    pot:dossierHighlights(d)+groupsHTML(d,['פוטנציאל ראשוני'],used),
    src:sourcesPanel(d)+`<h4 class="panel-h">בדיקות שנותרו<small>${d.gaps.length}</small></h4><ul class="gap-list">${d.gaps.map(g=>`<li>${esc(g)}</li>`).join('')}</ul>`
      +`<h4 class="panel-h">תכנון ומקורות</h4><p class="muted">רשימת תכניות בארכיון אינה חישוב זכויות או הוכחה שאין תכנית גוברת.</p><a href="${esc(d.policy_source)}" target="_blank" rel="noopener">מדיניות שקד העירונית — מקור הכללים<span class="ext">↗</span></a>`
      +d.archive_records.map(r=>`<details class="evidence-details"><summary>תיק בניין ${esc(r.id)} — נתונים מהארכיון</summary><a href="${esc(r.source.url)}" target="_blank" rel="noopener">מקור ארכיון<span class="ext">↗</span></a>${r.tables.map(t=>`<div style="overflow:auto"><table class="evidence-table"><tr>${t.headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr>${t.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table></div>`).join('')}</details>`).join('')
      +`<p class="pilot-note">אין עדיין בסיס תכנוני והנחות שלמות לחישוב רווח. בקובץ Excel ניתן לעיין במבנה החישוב; התאים החסרים נשארים ריקים.</p>`
      +(d.source_issues.length?`<details class="evidence-details"><summary>מגבלות איסוף (${d.source_issues.length})</summary>${d.source_issues.map(i=>`<p class="muted">${esc(i.source)}: ${esc(i.message)}</p>`).join('')}</details>`:'')};
  panels.src=leftoverHTML(d,used)+panels.src;
  return `<div class="dtabs" role="tablist" aria-label="חלקי התיק">${DOSSIER_TABS.map((t,i)=>
      `<button role="tab" id="dtab-${t.k}" data-dtab="${t.k}" aria-controls="dpanel-${t.k}"
        aria-selected="${i===0}" tabindex="${i?-1:0}">${t.n}</button>`).join('')}</div>`
    +DOSSIER_TABS.map((t,i)=>`<div class="dpanel" role="tabpanel" id="dpanel-${t.k}"
        aria-labelledby="dtab-${t.k}" tabindex="0" data-dpanel="${t.k}"${i?' hidden':''}>${panels[t.k]}</div>`).join('');})()}`;
  $('dossier-body').removeAttribute('aria-busy');
  if(!$('dossier').open)$('dossier').showModal();
  $('dossier-body').scrollTop=0;}catch(e){$('dossier').close();notice(e.message);}}
document.addEventListener('mouseover',e=>{const c=e.target.closest('[data-card]');if(c&&!c.contains(e.relatedTarget))highlightFeature(c.dataset.card,true);});
document.addEventListener('mouseout',e=>{const c=e.target.closest('[data-card]');if(c&&!c.contains(e.relatedTarget))highlightFeature(c.dataset.card,false);});
document.addEventListener('click',e=>{const d=e.target.closest('[data-dossier]');if(d)openDossier(d.dataset.dossier);const j=e.target.closest('[data-job]');if(j)poll(j.dataset.job).catch(x=>notice(x.message));});
document.querySelectorAll('[data-screen]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-screen]').forEach(n=>n.classList.toggle('active',n===b));['search','vault'].forEach(s=>$('screen-'+s).hidden=s!==b.dataset.screen);if(b.dataset.screen==='search')map?.invalidateSize();});
$('draw').onclick=()=>{notice('');if(!map)return;state.selectingCenter=true;$('polygon-status').textContent='לחצו פעם אחת במפה לבחירת המרכז';};
$('clear').onclick=()=>setCenter(null);
function radiusNote(){const r=radius(),max=state.config?.max_radius_m||r;
  const dunam=(Math.PI*r*r/1000).toLocaleString('he-IL',{maximumFractionDigits:1});
  $('radius-note').textContent=`שטח סריקה כ-${dunam} דונם · ${r} מתוך ${max} מטר מותרים`;
  $('radius-note').classList.toggle('over',r>max);}
$('radius').oninput=()=>{radiusNote();if(state.center)setCenter(state.center);};
$('sample-area').onclick=()=>setCenter(state.config.sample_center,true);
async function runInvestorScan(){const d=state.dossiers[0];if(!d)throw Error('תיק ההדגמה לא נטען');$('scan').disabled=true;$('job-panel').hidden=false;$('retry').hidden=true;const stages=[{progress:18,title:'מאתרים מבנים בתוך הרדיוס',state:'מיפוי מבנים'},{progress:46,title:'מושכים תיק בניין ומסמכי היתר',state:'איסוף מקורות'},{progress:73,title:'מחלצים נתונים ובודקים תנאי סף',state:'ניתוח ראיות'},{progress:100,title:'נמצא תיק שעבר את תנאי הסף',state:'התיק מוכן לעיון'}];for(const stage of stages){$('progress').value=stage.progress;paintPipeline(stage.progress,false);$('job-title').textContent=stage.title;$('job-state').textContent=stage.state;$('job-summary').textContent=stage.progress<100?'ה־pipeline עובד על נתונים ומסמכים שנשמרו מראש לצורך ההדגמה.':'השושנים 4 עבר 6 מתוך 6 תנאי סף ברמת המבנה. בדיקה תכנונית משלימה נשארת גלויה.';await new Promise(resolve=>setTimeout(resolve,520));}$('results').innerHTML=demoCard(d);showBuildings([d]);if(map){const shapes=[d.geometry,...d.parcels.filter(p=>p.geometry).map(p=>p.geometry)];const g=L.geoJSON({type:'FeatureCollection',features:shapes.map(geometry=>({type:'Feature',properties:{},geometry}))});moveTo(g.getBounds(),{padding:[85,85],maxZoom:19});}$('scan').disabled=false;$('results').scrollIntoView({behavior:'smooth',block:'center'});}
$('scan').onclick=guarded(async()=>{if(!state.center)throw Error('יש לבחור נקודת מרכז במפה לפני הסריקה');if(radius()>state.config.max_radius_m)throw Error(`רדיוס הפיילוט המרבי הוא ${state.config.max_radius_m} מטר`);await paintBuy();setStep('buy');});

/* Purchase, then the scan the purchase paid for. */
/* Backend failures arrive as "HTTP 504: <url>". A bare status code and a
   200-character query string tell the reader nothing, so name the source that
   did not answer and keep the raw line underneath for whoever needs it. */
const SOURCE_NAMES=[[/overpass/,'מאגר המבנים של OpenStreetMap'],[/govmap|opendata/,'GovMap — חלקות וגבול עירוני'],
  [/complot/,'ארכיון תיקי הבניין העירוני'],[/iplan|xplan/,'מנהל התכנון — XPlan'],[/herzliya|muni\.il/,'GIS עיריית הרצליה']];
function humanError(message){const m=/HTTP (\d{3}):\s*(\S+)/.exec(message||'');
  if(!m)return {headline:message||'הסריקה לא הושלמה',detail:''};
  const url=m[2],name=(SOURCE_NAMES.find(([re])=>re.test(url))||[null,'אחד המקורות'])[1];
  const transient=['429','502','503','504'].includes(m[1]);
  return {headline:transient?`${name} לא הגיב בזמן. זו תקלה חולפת — אפשר לנסות שוב.`
                            :`${name} החזיר שגיאה ${m[1]}.`, detail:message};}
function scanFailed(message){paintPipeline(0,true);$('job-title').textContent='הסריקה נעצרה';
  $('job-state').textContent='שגיאה';const h=humanError(message);
  $('job-summary').innerHTML=`${esc(h.headline)}${h.detail?`<br><small class="err-raw">${esc(h.detail)}</small>`:''}`;
  $('scan-back').hidden=false;}
async function startScan(){setStep('scan');paintPipeline(0,false);$('job-panel').hidden=false;
  $('scan-back').hidden=true;$('deliver-title').textContent='מה נמסר';
  try{return await runScan();}catch(e){scanFailed(e.message);throw e;}}
async function runScan(){
  if(state.investorDemo){await runInvestorScan();setStep('deliver');return;}const filters={};for(const [id,key] of [['min-area','min_parcel_area'],['max-units','max_units'],['max-floors','max_floors']])if($(id).value!=='')filters[key]=Number($(id).value);const preferences=[];$('scan').disabled=true;try{const j=await api('/searches',{method:'POST',body:JSON.stringify({center:state.center,radius_m:radius(),filters,preferences})});await poll(j.id);}catch(e){$('scan').disabled=false;throw e;}}
$('buy-back').onclick=()=>setStep('define');
$('scan-back').onclick=()=>setStep('define');
$('buy-existing').onclick=guarded(startScan);
$('buy-confirm').onclick=guarded(async()=>{await api('/package',{method:'POST'});
  toast('החבילה נפתחה. הסריקה מתחילה על האזור שהגדרתם.');await startScan();});
$('deliver-again').onclick=()=>setStep('define');
$('first-run-go').onclick=()=>{setCenter(state.config.sample_center,true);toast('נבחר מרכז לדוגמה. אפשר לשנות רדיוס ולהמשיך.');};
$('retry').onclick=guarded(async()=>{const j=await api('/searches/'+state.job+'/retry',{method:'POST'});await poll(j.id);});
$('audit').onclick=guarded(async()=>{const rows=await api('/pilot-sample',{method:'POST'});setStep('deliver');$('deliver-title').textContent='בדיקת 10 המבנים השמורה';$('scanned').innerHTML='';$('not-delivered').hidden=true;$('results').innerHTML=cards(rows);showBuildings(rows);if(rows.length&&map){const g=L.geoJSON({type:'FeatureCollection',features:rows.map(d=>({type:'Feature',properties:{},geometry:d.geometry}))});moveTo(g.getBounds(),{padding:[25,25]});}await refresh();$('results').scrollIntoView({behavior:'smooth',block:'start'});});
$('hashoshanim').onclick=guarded(async()=>{const d=state.investorDemo&&state.dossiers[0]?state.dossiers[0]:await api('/hashoshanim-sample',{method:'POST'});setStep('deliver');$('deliver-title').textContent='תיק הראיות של השושנים 4';$('scanned').innerHTML='';$('not-delivered').hidden=true;$('results').innerHTML=state.investorDemo?demoCard(d):cards([d]);showBuildings([d]);if(map){const g=L.geoJSON(d.geometry);moveTo(g.getBounds(),{padding:[80,80],maxZoom:19});}if(!state.investorDemo)await refresh();await openDossier(d.id);});
$('close').onclick=()=>$('dossier').close();
$('vault-q').oninput=()=>paintVault(false);
document.addEventListener('click',e=>{const a=e.target.closest('.dossier-actions a[href*="/export/"]');
  if(a)toast(a.href.endsWith('pdf')?'מכינים את קובץ ה־PDF…':'מכינים את קובץ ה־Excel…','work');});
document.addEventListener('click',e=>{if(e.target.closest('#vault-more'))paintVault(true);});
/* Tabs live inside innerHTML that is rebuilt per dossier, so delegate. */
function selectTab(b,focus){
  document.querySelectorAll('[data-dtab]').forEach(x=>{const on=x===b;
    x.setAttribute('aria-selected',String(on));x.tabIndex=on?0:-1;});
  document.querySelectorAll('[data-dpanel]').forEach(p=>{
    const on=p.dataset.dpanel===b.dataset.dtab;p.hidden=!on;
    if(on&&animates()){p.classList.remove('enter');void p.offsetWidth;p.classList.add('enter');}});
  $('dossier-body').scrollTop=0;
  /* scrollIntoView's inline axis is unreliable under RTL, so centre the tab
     with a relative scroll, which needs no assumption about scrollLeft's sign. */
  const strip=b.parentElement,sb=strip.getBoundingClientRect(),tb=b.getBoundingClientRect();
  if(tb.left<sb.left||tb.right>sb.right)
    /* Instant, not smooth: under RTL the smooth path here settles back at 0
       instead of the clamped target. The motion budget is spent on the panel
       transition, which does work. */
    strip.scrollBy({left:(tb.left+tb.width/2)-(sb.left+sb.width/2),behavior:'auto'});
  if(focus)b.focus();}
$('dossier-body').addEventListener('click',e=>{const b=e.target.closest('[data-dtab]');if(b)selectTab(b);});
/* Arrow keys move between tabs, Home and End jump to the ends — the behaviour
   a screen-reader user is entitled to expect from role="tablist". */
$('dossier-body').addEventListener('keydown',e=>{const b=e.target.closest('[data-dtab]');if(!b)return;
  const tabs=[...document.querySelectorAll('[data-dtab]')],i=tabs.indexOf(b);
  const step={ArrowRight:-1,ArrowLeft:1,Home:'first',End:'last'}[e.key];   /* RTL: right is previous */
  if(step===undefined)return;e.preventDefault();
  const next=step==='first'?tabs[0]:step==='last'?tabs[tabs.length-1]:tabs[(i+step+tabs.length)%tabs.length];
  selectTab(next,true);});

/* Theme. The pre-paint script in the document head has already applied the
   stored choice; this only keeps the control in sync and writes changes. */
function paintTheme(){const t=document.documentElement.getAttribute('data-theme')||'dark';
  document.querySelectorAll('[data-theme-set]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeSet===t)));}
document.querySelectorAll('[data-theme-set]').forEach(b=>b.onclick=()=>{
  const t=b.dataset.themeSet;document.documentElement.setAttribute('data-theme',t);
  try{localStorage.setItem('shakdan-theme',t);}catch(e){}
  paintTheme();map?.invalidateSize();});
paintTheme();
async function setupInvestorDemo(){document.body.classList.add('investor-demo');document.title='Shakdan | מפת הזדמנויות';$('page-title').textContent='בוחרים אזור. המערכת מוצאת הזדמנות ומציגה את הראיות.';document.querySelector('header .subtitle').textContent='סריקה על מפת הרצליה המבוססת על תיק ומסמכים שנשמרו מראש.';const d=await api('/hashoshanim-sample',{method:'POST'});state.dossiers=[d];const demoCenter=L.geoJSON(d.geometry).getBounds().getCenter();state.config.sample_center={lat:demoCenter.lat,lon:demoCenter.lng};setCenter(state.config.sample_center,true);$('hashoshanim').textContent='פתיחת תיק הראיות המלא ←';$('balance-label').textContent='תנאי סף שנבדקו';$('balance').textContent=`${d.eligibility.passed_count} / ${d.eligibility.total_core_checks}`;$('balance-note').textContent='כל תנאי הסף ברמת המבנה עברו';$('dossier-count-label').textContent='שדות שמולאו';$('dossier-count').textContent=`${Object.values(d.fields).filter(f=>f.value!==null&&f.value!==undefined).length} / ${Object.keys(d.fields).length}`;$('dossier-count-note').textContent='כל ערך כולל מקור ורמת ודאות';$('ready-count-label').textContent='מסמכי מקור';$('ready-count').textContent=d.documents.length;$('ready-count-note').textContent='היתרים ותכניות נשמרו עם חותמת מקור';$('results').innerHTML='';$('vault').innerHTML=demoCard(d);showBuildings([]);const boundary=await api('/investor-boundary');L.geoJSON(boundary,{style:{color:'#6f3b27',weight:2,fillOpacity:0,interactive:false}}).addTo(map);}
(async()=>{try{$('vault').innerHTML=skeletonCards(6);$('vault').setAttribute('aria-busy','true');
  state.config=await api('/config');state.archive=await api('/archive-sync').catch(()=>null);$('radius').max=state.config.max_radius_m;
  document.querySelector('header .eyebrow').textContent='גרסת כללים '+state.config.rule_version;$('limits').textContent=`מגבלות פיילוט: רדיוס עד ${state.config.max_radius_m} מטר; חריגה מ־${state.config.max_buildings} מבנים או ${state.config.max_parcels} חלקות עוצרת את הסריקה בלי חיתוך.`;radiusNote();paintSteps();paintPipeline(0,false);initMap();if(state.investorDemo)await setupInvestorDemo();else await refresh();[state.sources,state.xplanStatus]=await Promise.all([api('/sources'),api('/xplan/status').catch(()=>null)]);if(!state.investorDemo)try{const boundary=await api('/boundary');if(map)L.geoJSON(boundary,{style:{color:'#6f3b27',weight:2,fillOpacity:0,interactive:false}}).addTo(map);}catch(e){notice('גבול העיר אינו זמין כרגע: '+e.message);}}catch(e){notice(e.message);}})();

