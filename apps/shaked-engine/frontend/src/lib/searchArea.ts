/**
 * גאומטריה של אזור חיפוש — פייתון טהור של הדפדפן, **בלי leaflet**.
 *
 * הקבועים והפונקציות האלה ישבו קודם ב-`components/DrawPolygon.tsx`, ו-
 * `dashboard/page.tsx` ייבא משם את `MAX_AREA_SQM`. ייבוא אחד כזה גורר את
 * כל המודול — כולל `react-leaflet` ודרכו `leaflet` — לתוך חבילת ה-SSR,
 * ושם אין `window`. התוצאה הייתה **500 על טעינה נקייה של /dashboard**,
 * שלא נראתה בדפדפן כי ניווט פנימי באפליקציה שכבר נטענה עוקף את השרת.
 *
 * הכלל שנובע: ‏`Map` ו-`DrawPolygon` נטענים דינמית עם `ssr: false`, ולכן
 * **אסור לייבא מהם דבר בקוד שרץ בשרת** — גם לא קבוע.
 */

export type LatLngTuple = [number, number];

/** מגבלת MAP-01, כפי שהשרת אוכף אותה. כאן היא רק רמז מוקדם. */
export const MAX_AREA_SQM = 250_000;

/**
 * שטח גאודזי של טבעת ב-WGS84, במטרים רבועים.
 *
 * הנוסחה של עודף כדורי — אותה אחת ש-leaflet-draw משתמש בה. היא נחוצה כאן
 * כי **המשתמש צריך לדעת שהוא חרג לפני שהוא מסיים את הציור**, ולא לקבל
 * 422 אחרי. השרת נשאר הסמכות: הוא מודד ב-ITM ובודק גם את הגבול העירוני,
 * ושתי הבדיקות האלה אינן ניתנות לשכפול אמין בדפדפן.
 */
export function geodesicArea(ring: LatLngTuple[]): number {
  if (ring.length < 3) return 0;
  const R = 6378137;
  const d2r = Math.PI / 180;
  let total = 0;
  for (let i = 0; i < ring.length; i++) {
    const [lat1, lng1] = ring[i];
    const [lat2, lng2] = ring[(i + 1) % ring.length];
    total += (lng2 - lng1) * d2r * (2 + Math.sin(lat1 * d2r) + Math.sin(lat2 * d2r));
  }
  return Math.abs((total * R * R) / 2);
}

/** טבעת לייפלט → GeoJSON Polygon. סדר הצירים מתהפך, והטבעת נסגרת. */
export function toGeoJson(ring: LatLngTuple[]): object {
  const coords = ring.map(([lat, lng]) => [lng, lat]);
  const first = coords[0];
  const last = coords[coords.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) coords.push(first);
  return { type: "Polygon", coordinates: [coords] };
}
