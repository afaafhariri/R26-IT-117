import { useEffect, useRef } from 'react';

/** Leaflet is loaded globally via CDN script tags in index.html - no npm
 *  dependency added. This keeps the map's imperative DOM/event handling
 *  isolated from the rest of the React tree. */
declare const L: {
  map: (el: HTMLElement) => LeafletMap;
  tileLayer: (url: string, opts: Record<string, unknown>) => { addTo: (m: LeafletMap) => void };
  marker: (pos: [number, number], opts: Record<string, unknown>) => LeafletMarker;
};

interface LeafletLatLng {
  lat: number;
  lng: number;
}
interface LeafletMap {
  setView: (pos: [number, number], zoom: number) => LeafletMap;
  remove: () => void;
  on: (event: string, handler: (e: { latlng: LeafletLatLng }) => void) => void;
}
interface LeafletMarker {
  addTo: (m: LeafletMap) => LeafletMarker;
  on: (event: string, handler: () => void) => void;
  getLatLng: () => LeafletLatLng;
  setLatLng: (pos: [number, number]) => void;
}

const DEFAULT_CENTER: [number, number] = [7.8731, 80.7718]; // Sri Lanka, roughly centred

type Props = {
  latitude: number | null;
  longitude: number | null;
  /** Fired once per placement (click, or drag release) - never mid-drag. */
  onChange: (lat: number, lon: number) => void;
};

export function LocationMap({ latitude, longitude, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerRef = useRef<LeafletMarker | null>(null);
  // Keep the latest callback without re-creating the map on every render.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (typeof L === 'undefined') return; // CDN blocked/offline - map area stays blank

    const start = latitude != null && longitude != null ? ([latitude, longitude] as [number, number]) : DEFAULT_CENTER;
    const map = L.map(containerRef.current).setView(start, latitude != null ? 13 : 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    const marker = L.marker(start, { draggable: true }).addTo(map);

    // dragend (not drag) - fires once per placement, so moving the pin
    // never floods the backend with a PATCH per pixel of movement.
    marker.on('dragend', () => {
      const pos = marker.getLatLng();
      onChangeRef.current(pos.lat, pos.lng);
    });
    map.on('click', (e) => {
      marker.setLatLng([e.latlng.lat, e.latlng.lng]);
      onChangeRef.current(e.latlng.lat, e.latlng.lng);
    });

    mapRef.current = map;
    markerRef.current = marker;

    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // Intentionally mount once; external location changes are synced below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reflect an externally-changed saved location (e.g. dashboard refetch
  // after switching projects) onto the marker, without re-creating the map.
  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    if (latitude == null || longitude == null) return;
    const current = markerRef.current.getLatLng();
    if (Math.abs(current.lat - latitude) > 1e-6 || Math.abs(current.lng - longitude) > 1e-6) {
      markerRef.current.setLatLng([latitude, longitude]);
      mapRef.current.setView([latitude, longitude], 13);
    }
  }, [latitude, longitude]);

  return <div ref={containerRef} className="location-map" />;
}

/** OpenStreetMap's free geocoding service - no API key required, and
 *  entirely separate from the backend's OpenWeatherMap key, which stays
 *  server-side. */
export async function geocodeSearch(query: string): Promise<{ lat: number; lon: number } | null> {
  const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`Location search failed (HTTP ${res.status}).`);
  const results = (await res.json()) as { lat: string; lon: string }[];
  if (!results.length) return null;
  return { lat: parseFloat(results[0].lat), lon: parseFloat(results[0].lon) };
}
