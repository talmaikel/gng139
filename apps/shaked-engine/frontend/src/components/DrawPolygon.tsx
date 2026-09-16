"use client";

import type { LeafletMouseEvent } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { CircleMarker, Polygon, Polyline, useMap } from "react-leaflet";
import { MAX_AREA_SQM, geodesicArea, toGeoJson, type LatLngTuple } from "@/lib/searchArea";
import { MAP_COLOUR } from "@/lib/labels";

interface Props {
  active: boolean;
  onFinish: (polygon: object, areaSqm: number) => void;
  onCancel: () => void;
  /** נקרא בכל נקודה, כדי שהמסך יוכל להציג שטח חי */
  onProgress?: (points: number, areaSqm: number) => void;
}

/**
 * ציור פוליגון בלייפלט גולמי, בלי leaflet-draw.
 *
 * ‏`leaflet-draw` אינו נתמך ב-react-leaflet 4 בלי עטיפה שאינה מתוחזקת,
 * וסרגל הכלים שלו אנגלי ו-LTR. הציור עצמו הוא כשמונים שורות, והוא נותן
 * לנו את הרמזים בעברית ואת מד השטח החי — שהם בדיוק מה שהופך את מגבלת
 * ה-250 דונם למובנת ולא להפתעה.
 *
 * לחיצה מוסיפה קודקוד · לחיצה כפולה או ״סיום״ סוגרת · Escape מבטל.
 */
export default function DrawPolygon({ active, onFinish, onCancel, onProgress }: Props) {
  const map = useMap();
  const [points, setPoints] = useState<LatLngTuple[]>([]);

  // ‏`finish` נקרא ממאזינים שנרשמים פעם אחת לכל הפעלה, ולכן הוא אינו יכול
  // לקרוא את `points` מה-closure — הוא היה תמיד רואה מערך ריק. ‏ref
  // שמתעדכן בכל שינוי הוא הדרך לקרוא את הערך העדכני משם.
  const pointsRef = useRef<LatLngTuple[]>([]);
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);

  // **קריאה להורה חייבת לצאת מכאן ולא מתוך `setPoints`.** הגרסה הראשונה
  // קראה ל-`onProgress` בתוך פונקציית העדכון, ש-React מריץ בזמן render,
  // וזה עדכון של קומפוננטה אחת מתוך render של אחרת.
  useEffect(() => {
    if (active) onProgress?.(points.length, geodesicArea(points));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, active]);

  useEffect(() => {
    if (!active) {
      setPoints([]);
      return;
    }

    function addPoint(e: LeafletMouseEvent) {
      setPoints((prev) => [...prev, [e.latlng.lat, e.latlng.lng]]);
    }

    function finish() {
      const current = pointsRef.current;
      setPoints([]);
      // פחות משלוש נקודות אינו פוליגון. שתיקה כאן הייתה נראית כמו תקלה,
      // ולכן הביטול מפורש ומדווח למעלה.
      if (current.length < 3) {
        onCancel();
        return;
      }
      onFinish(toGeoJson(current), geodesicArea(current));
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPoints([]);
        onCancel();
      } else if (event.key === "Enter") {
        finish();
      }
    }

    // ‏`map.on` ישירות ולא `useMapEvents`: שם המאזינים נרשמים מחדש בכל
    // render לפי זהות אובייקט ה-handlers, והתלות הזו עדינה מכדי להישען
    // עליה לרישום שקיים רק בזמן ציור. כאן ההרשמה קשורה ל-`active` בלבד.
    map.on("click", addPoint);
    map.on("dblclick", finish);
    map.doubleClickZoom.disable();

    const container = map.getContainer();
    const previousCursor = container.style.cursor;
    container.style.cursor = "crosshair";
    window.addEventListener("keydown", onKey);

    return () => {
      map.off("click", addPoint);
      map.off("dblclick", finish);
      map.doubleClickZoom.enable();
      container.style.cursor = previousCursor;
      window.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, map]);

  if (!active || points.length === 0) return null;

  const area = geodesicArea(points);
  const tooLarge = points.length >= 3 && area > MAX_AREA_SQM;
  const colour = tooLarge ? MAP_COLOUR.tooLarge : MAP_COLOUR.area;

  return (
    <>
      {points.length >= 3 ? (
        <Polygon positions={points} pathOptions={{ color: colour, weight: 2, dashArray: "5 5", fillOpacity: 0.1 }} />
      ) : (
        <Polyline positions={points} pathOptions={{ color: colour, weight: 2, dashArray: "5 5" }} />
      )}
      {points.map((p, i) => (
        <CircleMarker key={i} center={p} radius={4} pathOptions={{ color: colour, fillColor: "#fff", fillOpacity: 1 }} />
      ))}
    </>
  );
}
