"use client";

import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

export interface MapMarker {
  id: string;
  label: string;
  lat: number;
  lng: number;
}

const HERZLIYA_CENTER: [number, number] = [32.1624, 34.8447];

export default function OpportunityMap({ markers = [] as MapMarker[] }: { markers?: MapMarker[] }) {
  return (
    <MapContainer center={HERZLIYA_CENTER} zoom={13} style={{ height: 420, width: "100%", borderRadius: 10 }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {markers.map((marker) => (
        <Marker key={marker.id} position={[marker.lat, marker.lng]}>
          <Popup>{marker.label}</Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
