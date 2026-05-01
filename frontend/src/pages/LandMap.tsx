// @ts-nocheck
import React from "react";
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { LatLngExpression } from "leaflet";

// Fix default icon paths for Leaflet in bundlers
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export type DisputeRiskLevel = "low" | "medium" | "high" | "unknown";

export interface LandMarker {
  id: string;
  owner?: string | null;
  khasra_number?: string | null;
  area?: string | null;
  latitude: number;
  longitude: number;
  dispute_status?: DisputeRiskLevel;
}

interface LandMapProps {
  center?: LatLngExpression;
  markers: LandMarker[];
}

function MapAutoFocus({ markers }: { markers: LandMarker[] }) {
  const map = useMap();

  // When markers change, fly to the first marker with a smooth animation
  React.useEffect(() => {
    if (!markers.length) return;
    const first = markers[0];
    if (first.latitude == null || first.longitude == null) return;

    const target: LatLngExpression = [first.latitude, first.longitude];
    map.flyTo(target, 13, { duration: 1.2 });
  }, [markers, map]);

  return null;
}

export function LandMap({ center, markers }: LandMapProps) {
  const defaultCenter: LatLngExpression = center || [26.8467, 80.9462]; // Lucknow, UP

  // Tighter bounding box for Uttar Pradesh (SW, NE)
  const upBounds: [[number, number], [number, number]] = [
    [24.0, 77.0], // south-west
    [29.8, 84.0], // north-east
  ];

  const getColorForRisk = (risk?: DisputeRiskLevel) => {
    switch (risk) {
      case "high":
        return "#ef4444";
      case "medium":
        return "#facc15";
      case "low":
        return "#22c55e";
      default:
        return "#3b82f6";
    }
  };

  return (
    <div className="land-map-container">
      <MapContainer
        center={defaultCenter}
        zoom={8}
        minZoom={7}
        maxZoom={14}
        maxBounds={upBounds}
        maxBoundsViscosity={1.0}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%", borderRadius: "0.75rem", overflow: "hidden" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {markers.map((marker) => (
          <Marker
            key={marker.id}
            position={[marker.latitude, marker.longitude]}
          >
            <Popup>
              <div className="space-y-1 text-sm">
                {marker.owner && (
                  <div>
                    <span className="font-semibold">Owner:</span> {marker.owner}
                  </div>
                )}
                {marker.khasra_number && (
                  <div>
                    <span className="font-semibold">Khasra No.:</span> {marker.khasra_number}
                  </div>
                )}
                {marker.area && (
                  <div>
                    <span className="font-semibold">Area:</span> {marker.area}
                  </div>
                )}
                {marker.dispute_status && (
                  <div>
                    <span className="font-semibold">Dispute Risk:</span>{" "}
                    {marker.dispute_status.toUpperCase()}
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}

        {markers.map((marker) => (
          <CircleMarker
            key={marker.id + "-risk"}
            center={[marker.latitude, marker.longitude]}
            radius={10}
            pathOptions={{
              color: getColorForRisk(marker.dispute_status),
              fillColor: getColorForRisk(marker.dispute_status),
              weight: 3,
              fillOpacity: 0.45,
            }}
          />
        ))}

        <MapAutoFocus markers={markers} />
      </MapContainer>
    </div>
  );
}

export default LandMap;

