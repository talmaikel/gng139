"use client";

import type { LeafletMouseEvent } from "leaflet";
import { useEffect } from "react";
import { Circle, CircleMarker, useMap } from "react-leaflet";
import type { LatLngTuple } from "@/lib/searchArea";
import { MAP_COLOUR } from "@/lib/labels";

interface Props {
  /** מצב בחירה: לחיצה על המפה קובעת את המרכז */
  active: boolean;
  center: LatLngTuple | null;
  radiusM: number;
  tooLarge?: boolean;
  onPick: (center: LatLngTuple) => void;
  onCancel: () => void;
}

/**
 * נקודה ורדיוס במקום פוליגון.
 *
 * הלקוח לוחץ פעם אחת; העיגול סביב הנקודה הוא אזור החיפוש, והרדיוס נבחר
 * במחוון ליד המפה. הפוליגון שנשלח לשרת נבנה מהעיגול (`circlePolygon`),
 * כך שהשרת ומגבלת 250 הדונם לא השתנו.
 */
export default function PickCircle({ active, center, radiusM, tooLarge = false, onPick, onCancel }: Props) {
  const map = useMap();

  useEffect(() => {
    if (!active) return;
    const pick = (e: LeafletMouseEvent) => onPick([e.latlng.lat, e.latlng.lng]);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    map.on("click", pick);
    const container = map.getContainer();
    const previous = container.style.cursor;
    container.style.cursor = "crosshair";
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("click", pick);
      container.style.cursor = previous;
      window.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, map]);

  if (!center) return null;
  const colour = tooLarge ? MAP_COLOUR.tooLarge : MAP_COLOUR.area;
  return (
    <>
      <Circle center={center} radius={radiusM} pathOptions={{ color: colour, weight: 2, dashArray: "6 4", fillOpacity: 0.08, interactive: false }} />
      <CircleMarker center={center} radius={5} pathOptions={{ color: colour, fillColor: "#fff", fillOpacity: 1, interactive: false }} />
    </>
  );
}
