// web/components/MapShell.client.tsx
'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';

// React-Leaflet pieces (client only)
const MapContainer = dynamic(() => import('react-leaflet').then(m => m.MapContainer), { ssr: false });
const TileLayer     = dynamic(() => import('react-leaflet').then(m => m.TileLayer),     { ssr: false });
const Marker        = dynamic(() => import('react-leaflet').then(m => m.Marker),        { ssr: false });
const Popup         = dynamic(() => import('react-leaflet').then(m => m.Popup),         { ssr: false });

// --- Helpers (all client-safe) ----------------------------------------------

function getColoredIcon(color: string) {
  // require Leaflet at runtime on the client
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const L = require('leaflet') as typeof import('leaflet');

  const html = `
    <svg xmlns="http://www.w3.org/2000/svg" width="26" height="41" viewBox="0 0 26 41" aria-hidden="true">
      <defs>
        <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="1.2" stdDeviation="1.2" flood-color="rgba(0,0,0,0.35)" />
        </filter>
      </defs>
      <g filter="url(#shadow)">
        <path d="M13 0.8
                 C6.1 0.8 0.5 6.4 0.5 13.3
                 C0.5 21.8 13 40 13 40
                 C13 40 25.5 21.8 25.5 13.3
                 C25.5 6.4 19.9 0.8 13 0.8Z"
              fill="${color}" stroke="#1f2937" stroke-width="1" />
        <circle cx="13" cy="13.5" r="4.2" fill="#ffffff" opacity="0.9" />
      </g>
    </svg>
  `.trim();

  return L.divIcon({
    className: 'huntapp-pin',
    html,
    iconSize: [26, 41],
    iconAnchor: [13, 40],
    popupAnchor: [0, -36],
  });
}

const DEFAULT_COLOR = '#3b82f6'; // blue
const draftIcon     = () => getColoredIcon('#1e3a8a');
const eventIcon     = (c?: string) => getColoredIcon(c || DEFAULT_COLOR);

type EventItem = {
  id: string;
  timestamp?: string;
  event_type?: string;
  note?: string | null;
  species?: string | null;
  color?: string | null;
  geo?: { lat?: number | string; lon?: number | string };
  lat?: number | string | null;
  lon?: number | string | null;
};

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000').replace(/\/+$/, '');

function toNum(v: number | string | null | undefined): number | undefined {
  if (v == null) return undefined;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : undefined;
}

const PALETTE: { name: string; hex: string }[] = [
  { name: 'blue',     hex: '#3b82f6' }, { name: 'orange',  hex: '#fb923c' },
  { name: 'green',    hex: '#22c55e' }, { name: 'purple',  hex: '#a855f7' },
  { name: 'red',      hex: '#ef4444' }, { name: 'yellow',  hex: '#eab308' },
  { name: 'pink',     hex: '#ec4899' }, { name: 'teal',    hex: '#14b8a6' },
  { name: 'indigo',   hex: '#6366f1' }, { name: 'lime',    hex: '#84cc16' },
  { name: 'amber',    hex: '#f59e0b' }, { name: 'cyan',    hex: '#06b6d4' },
  { name: 'rose',     hex: '#f43f5e' }, { name: 'violet',  hex: '#8b5cf6' },
  { name: 'emerald',  hex: '#10b981' }, { name: 'slate',   hex: '#64748b' },
];

// Separate component to attach map click events (proper hook usage)
function ClickCatcher({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { useMapEvents } = require('react-leaflet') as typeof import('react-leaflet');
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

// --- Component ---------------------------------------------------------------

export default function MapShell() {
  // explicit 100vh root ensures non-zero height everywhere
  const rootStyle: React.CSSProperties = { position: 'absolute', inset: 0 };

  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(false);

  const [draft, setDraft] = useState<{ lat: number; lon: number } | null>(null);
  const [eventType, setEventType] = useState('stand');
  const [note, setNote]           = useState('');
  const [species, setSpecies]     = useState('whitetail');
  const [color, setColor]         = useState<string>(DEFAULT_COLOR);

  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState<string | null>(null);
  const [okMsg, setOkMsg]   = useState<string | null>(null);

  const center = useMemo<[number, number]>(() => [41.2565, -95.9345], []);

  const fetchRecent = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/events/recent?limit=500`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`recent failed: ${res.status}`);
      const json = await res.json();
      setEvents(Array.isArray(json?.items) ? json.items : []);
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load events');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecent();
  }, [fetchRecent]);

  const onMapClick = useCallback((lat: number, lon: number) => {
    setDraft({ lat, lon });
    setOkMsg(null);
    setErr(null);
  }, []);

  const onSave = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    setErr(null);
    setOkMsg(null);
    try {
      const res = await fetch(`${API_BASE}/events/pin`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          lat: draft.lat,
          lon: draft.lon,
          event_type: eventType,
          note: note || undefined,
          species: species || undefined,
          color,
        }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`save failed: ${res.status} ${txt}`);
      }
      setOkMsg('Pin saved!');
      setDraft(null);
      setNote('');
      setColor(DEFAULT_COLOR);
      await fetchRecent();
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to save');
    } finally {
      setSaving(false);
    }
  }, [draft, eventType, note, species, color, fetchRecent]);

  const onCancel = useCallback(() => {
    setDraft(null);
    setNote('');
    setOkMsg(null);
    setErr(null);
    setColor(DEFAULT_COLOR);
    setEventType('stand');
    setSpecies('whitetail');
  }, []);

  return (
    <div style={rootStyle}>
      {/* debug chip so you know it's mounted even if tiles not visible */}
      <div style={{
        position: 'absolute', zIndex: 1000, top: 8, left: 8,
        background: 'rgba(0,0,0,.8)', color: '#a7f3d0',
        borderRadius: 8, padding: '3px 8px', fontSize: 12
      }}>
        map: client ✓ {events.length ? `| events: ${events.length}` : ''}
      </div>

      <MapContainer
        center={center}
        zoom={12}
        style={{ height: '100%', width: '100%' }} // <- forces height
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />

        {/* existing events */}
        {events.map((ev) => {
          const lat = toNum(ev.lat ?? ev.geo?.lat);
          const lon = toNum(ev.lon ?? ev.geo?.lon);
          if (lat === undefined || lon === undefined) return null;
          const c = (typeof ev.color === 'string' && ev.color.trim()) ? ev.color : DEFAULT_COLOR;
          return (
            <Marker key={ev.id} position={[lat, lon]} icon={eventIcon(c)}>
              <Popup>
                <div style={{ lineHeight: 1.35, fontSize: 13 }}>
                  <b>{ev.event_type || 'event'}</b><br />
                  {ev.species ? <>species: {ev.species}<br /></> : null}
                  {ev.note ? <>note: {ev.note}<br /></> : null}
                  [{lat.toFixed(5)}, {lon.toFixed(5)}]
                  {ev.timestamp ? <><br />{new Date(ev.timestamp).toLocaleString()}</> : null}
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* click handler */}
        <ClickCatcher onClick={onMapClick} />

        {/* draft marker + form */}
        {draft && (
          <Marker position={[draft.lat, draft.lon]} icon={draftIcon()}>
            <Popup minWidth={260}>
              <form
                style={{ display: 'grid', gap: 8, fontSize: 13 }}
                onSubmit={(e) => { e.preventDefault(); onSave(); }}
              >
                <div style={{ fontWeight: 600 }}>New pin</div>
                <div style={{ fontSize: 11, opacity: .7 }}>
                  [{draft.lat.toFixed(5)}, {draft.lon.toFixed(5)}]
                </div>

                <label style={{ fontSize: 12 }}>
                  Type
                  <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                    style={{ width: '100%', marginTop: 4 }}
                  >
                    <option value="stand">stand</option>
                    <option value="scrape">scrape</option>
                    <option value="rub">rub</option>
                    <option value="bedding">bedding</option>
                    <option value="access">access</option>
                    <option value="camp">camp</option>
                    <option value="other">other</option>
                  </select>
                </label>

                <label style={{ fontSize: 12 }}>
                  Species
                  <input
                    value={species}
                    onChange={(e) => setSpecies(e.target.value)}
                    placeholder="whitetail"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </label>

                <label style={{ fontSize: 12 }}>
                  Note
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="optional"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </label>

                <div style={{ fontSize: 12 }}>Color</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 4 }}>
                  {PALETTE.map((p) => (
                    <button
                      key={p.hex}
                      type="button"
                      title={p.name}
                      onClick={() => setColor(p.hex)}
                      style={{
                        height: 22, borderRadius: 6,
                        boxShadow: color === p.hex ? '0 0 0 2px #000' : '0 0 0 1px #CBD5E1',
                        background: p.hex,
                      }}
                    />
                  ))}
                </div>

                <div style={{ display: 'flex', gap: 8, paddingTop: 4 }}>
                  <button type="submit" disabled={saving} style={{ padding: '4px 10px' }}>
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button type="button" onClick={onCancel} style={{ padding: '4px 10px' }}>
                    Cancel
                  </button>
                </div>

                {err && <div style={{ fontSize: 12, color: '#dc2626' }}>{err}</div>}
                {okMsg && <div style={{ fontSize: 12, color: '#065f46' }}>{okMsg}</div>}
              </form>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      {loading && (
        <div style={{
          position: 'absolute', left: 8, bottom: 8,
          background: 'rgba(255,255,255,.9)', padding: '2px 6px',
          borderRadius: 6, fontSize: 12
        }}>
          loading…
        </div>
      )}
    </div>
  );
}
