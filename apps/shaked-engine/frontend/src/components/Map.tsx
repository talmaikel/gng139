"use client";

import "leaflet/dist/leaflet.css";
import Link from "next/link";
import { useEffect } from "react";
import { MapContainer, Polygon, Popup, TileLayer, useMap } from "react-leaflet";
import type { Candidate, MultiPolygonGeometry } from "@/lib/api";
import DrawPolygon from "@/components/DrawPolygon";
import PickCircle from "@/components/PickCircle";
import type { LatLngTuple } from "@/lib/searchArea";
import { MAP_COLOUR } from "@/lib/labels";

const HERZLIYA_CENTER: [number, number] = [32.1624, 34.8447];

// react-leaflet's <Polygon> accepts the same nested ring structure GeoJSON
// uses, just with each position as [lat, lng] instead of GeoJSON's [lng, lat].
function toLeafletRings(geometry: MultiPolygonGeometry): LatLngTuple[][][] {
  return geometry.coordinates.map((polygon) =>
    polygon.map((ring) => ring.map(([lng, lat]) => [lat, lng] as LatLngTuple))
  );
}

function ringsOf(polygon: object | null): LatLngTuple[][] | null {
  const p = polygon as { coordinates?: number[][][] } | null;
  if (!p?.coordinates) return null;
  return p.coordinates.map((ring) => ring.map(([lng, lat]) => [lat, lng] as LatLngTuple));
}

/** ממקד את המפה על התוצאות — אבל לא בזמן ציור, שם זה היה חוטף את המפה
 *  מתחת ליד של המשתמש. */
function FitToCandidates({ candidates, paused }: { candidates: Candidate[]; paused: boolean }) {
  const map = useMap();

  useEffect(() => {
    if (paused) return;
    const points: LatLngTuple[] = candidates
      .filter((c) => c.geometry)
      .flatMap((c) => toLeafletRings(c.geometry as MultiPolygonGeometry).flat(2));

    if (points.length > 0) {
      map.fitBounds(points, { padding: [30, 30] });
    }
  }, [candidates, map, paused]);

  return null;
}

interface Props {
  candidates?: Candidate[];
  /** על מה להתמקד. ברירת המחדל: כל ה-candidates. מערך ריק משאיר את המפה
   *  על הרצליה כולה. */
  fitTo?: Candidate[];
  /** מצב ציור/בחירה פעיל */
  drawing?: boolean;
  /** ‏polygon: הצוות מצייר; ‏circle: הלקוח לוחץ נקודה והרדיוס נבחר במחוון */
  mode?: "polygon" | "circle";
  /** הפוליגון שנבחר, שנשאר על המפה כדי שרואים מה נסרק (במצב polygon) */
  searchArea?: object | null;
  /** מרכז ורדיוס (במצב circle) */
  circle?: { center: LatLngTuple; radiusM: number; tooLarge?: boolean } | null;
  onPolygon?: (polygon: object, areaSqm: number) => void;
  onPick?: (center: LatLngTuple) => void;
  onCancelDraw?: () => void;
  onDrawProgress?: (points: number, areaSqm: number) => void;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** קישור לתיק מתוך החלון הקופץ של חלקה שנמסרה */
  dossierHref?: (id: string) => string;
}

export default function OpportunityMap({
  candidates = [],
  fitTo,
  drawing = false,
  mode = "polygon",
  searchArea = null,
  circle = null,
  onPolygon,
  onPick,
  onCancelDraw,
  onDrawProgress,
  selectedId = null,
  onSelect,
  dossierHref,
}: Props) {
  const areaRings = mode === "polygon" ? ringsOf(searchArea) : null;

  return (
    <MapContainer center={HERZLIYA_CENTER} zoom={13} style={{ height: 460, width: "100%", borderRadius: 5 }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {areaRings && !drawing && (
        <Polygon
          positions={areaRings}
          pathOptions={{ color: MAP_COLOUR.area, weight: 2, dashArray: "6 4", fill: false }}
        />
      )}

      {candidates
        .filter((candidate) => candidate.geometry)
        .map((candidate) => {
          const selected = candidate.id === selectedId;
          return (
            <Polygon
              key={candidate.id}
              positions={toLeafletRings(candidate.geometry as MultiPolygonGeometry)}
              eventHandlers={!drawing && onSelect ? { click: () => onSelect(candidate.id) } : undefined}
              pathOptions={{
                color: selected ? MAP_COLOUR.selected : MAP_COLOUR.candidate,
                weight: selected ? 3 : 2,
                fillOpacity: selected ? 0.35 : 0.22,
                // בזמן ציור החלקות אינן ניתנות ללחיצה, אחרת קודקוד שנופל
                // על מועמד נבלע בו ולא מגיע למפה — והמשתמש רואה לחיצה
                // שלא עשתה כלום, בדיוק מעל האזור שהוא הכי רוצה לסמן.
                interactive: !drawing,
              }}
            >
              <Popup>
                <strong>{candidate.address}</strong>
                <br />
                גוש {candidate.block ?? "—"} · חלקה {candidate.parcel ?? "—"}
                {candidate.area_sqm ? <><br />{candidate.area_sqm} מ״ר</> : null}
                {dossierHref && (
                  <>
                    <br />
                    <Link href={dossierHref(candidate.id)} className="text-link">פתח תיק ←</Link>
                  </>
                )}
              </Popup>
            </Polygon>
          );
        })}

      {mode === "circle" ? (
        <PickCircle
          active={drawing}
          center={circle?.center ?? null}
          radiusM={circle?.radiusM ?? 0}
          tooLarge={circle?.tooLarge}
          onPick={(c) => onPick?.(c)}
          onCancel={() => onCancelDraw?.()}
        />
      ) : (
        <DrawPolygon
          active={drawing}
          onFinish={(polygon, area) => onPolygon?.(polygon, area)}
          onCancel={() => onCancelDraw?.()}
          onProgress={onDrawProgress}
        />
      )}
      <FitToCandidates candidates={fitTo ?? candidates} paused={drawing} />
    </MapContainer>
  );
}
