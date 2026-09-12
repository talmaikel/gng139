"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { MapContainer, Polygon, Popup, TileLayer, useMap } from "react-leaflet";
import type { Candidate, MultiPolygonGeometry } from "@/lib/api";

const HERZLIYA_CENTER: [number, number] = [32.1624, 34.8447];

type LatLngTuple = [number, number];

// react-leaflet's <Polygon> accepts the same nested ring structure GeoJSON
// uses, just with each position as [lat, lng] instead of GeoJSON's [lng, lat].
function toLeafletRings(geometry: MultiPolygonGeometry): LatLngTuple[][][] {
  return geometry.coordinates.map((polygon) =>
    polygon.map((ring) => ring.map(([lng, lat]) => [lat, lng] as LatLngTuple))
  );
}

function FitToCandidates({ candidates }: { candidates: Candidate[] }) {
  const map = useMap();

  useEffect(() => {
    const points: LatLngTuple[] = candidates
      .filter((c) => c.geometry)
      .flatMap((c) => toLeafletRings(c.geometry as MultiPolygonGeometry).flat(2));

    if (points.length > 0) {
      map.fitBounds(points, { padding: [30, 30] });
    }
  }, [candidates, map]);

  return null;
}

export default function OpportunityMap({ candidates = [] as Candidate[] }: { candidates?: Candidate[] }) {
  return (
    <MapContainer center={HERZLIYA_CENTER} zoom={13} style={{ height: 420, width: "100%", borderRadius: 10 }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {candidates
        .filter((candidate) => candidate.geometry)
        .map((candidate) => (
          <Polygon
            key={candidate.id}
            positions={toLeafletRings(candidate.geometry as MultiPolygonGeometry)}
            pathOptions={{ color: "#1f6f4f", weight: 2, fillOpacity: 0.25 }}
          >
            <Popup>
              <strong>{candidate.address}</strong>
              <br />
              Block {candidate.block ?? "—"} / Parcel {candidate.parcel ?? "—"}
              <br />
              {candidate.area_sqm ?? "—"} sqm
            </Popup>
          </Polygon>
        ))}
      <FitToCandidates candidates={candidates} />
    </MapContainer>
  );
}
