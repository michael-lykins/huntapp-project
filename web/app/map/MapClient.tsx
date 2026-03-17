'use client';

import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

type Mode = 'default' | 'add' | 'delete';
type FC = { type: 'FeatureCollection'; features: any[] };

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000').replace(/\/$/, '');
mapboxgl.accessToken =
  process.env.NEXT_PUBLIC_MAPBOX_TOKEN || process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN || '';

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

class Dock implements mapboxgl.IControl {
  private el!: HTMLElement;
  private modeRef: React.MutableRefObject<Mode>;
  constructor(modeRef: React.MutableRefObject<Mode>) {
    this.modeRef = modeRef;
  }
  getDefaultPosition(): mapboxgl.ControlPosition {
    return 'top-right';
  }
  onAdd() {
    const box = document.createElement('div');
    box.style.cssText =
      'display:flex;gap:8px;background:rgba(255,255,255,.95);border-radius:12px;padding:8px;box-shadow:0 6px 16px rgba(0,0,0,.12);z-index:999999;';
    const mk = (label: string, title: string, on: () => void, color?: string) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.title = title;
      b.style.cssText =
        'padding:8px 10px;border-radius:10px;background:#fff;border:1px solid rgba(0,0,0,.08);cursor:pointer;font-size:12px;';
      if (color) b.style.color = color;
      const h = (e: Event) => {
        e.preventDefault(); e.stopPropagation();
        on();
      };
      ['click','mousedown','mouseup','touchstart','touchend','contextmenu'].forEach((ev) =>
        b.addEventListener(ev, h, { passive: false } as any));
      return b;
    };
    const addBtn = mk('Add', 'Add waypoint', () => {
      this.modeRef.current = this.modeRef.current === 'add' ? 'default' : 'add';
      console.log('[Dock] mode ->', this.modeRef.current);
      addBtn.style.boxShadow = this.modeRef.current === 'add' ? '0 0 0 2px #3b82f6' : 'none';
      delBtn.style.boxShadow = 'none';
    });
    const delBtn = mk('Delete', 'Delete waypoint', () => {
      this.modeRef.current = this.modeRef.current === 'delete' ? 'default' : 'delete';
      console.log('[Dock] mode ->', this.modeRef.current);
      delBtn.style.boxShadow = this.modeRef.current === 'delete' ? '0 0 0 2px #ef4444' : 'none';
      addBtn.style.boxShadow = 'none';
    }, '#b91c1c');

    ['click','mousedown','mouseup','touchstart','touchend','wheel','contextmenu'].forEach((ev) =>
      box.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); }, { passive: false }));

    box.append(addBtn, delBtn);
    this.el = box;
    return box;
  }
  onRemove() { this.el?.parentNode?.removeChild(this.el); }
}

export default function MapClient() {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const divRef = useRef<HTMLDivElement | null>(null);
  const modeRef = useRef<Mode>('default');
  const [counts, setCounts] = useState({ features: 0, cams: 0 });

  const bboxParam = () => {
    const b = mapRef.current!.getBounds();
    return `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
  };

  const ensure = () => {
    const m = mapRef.current!;
    if (!m.getSource('geo')) {
      m.addSource('geo', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        promoteId: 'id',
        generateId: true,
      } as mapboxgl.GeoJSONSourceRaw);
    }
    if (!m.getLayer('wpt-circles')) {
      m.addLayer({
        id: 'wpt-circles',
        type: 'circle',
        source: 'geo',
        filter: ['==', ['get', 'kind'], 'wpt'],
        paint: {
          'circle-color': '#0ea5e9',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.5,
          'circle-radius': 6,
        },
      });
    }
    if (!m.getLayer('wpt-labels')) {
      m.addLayer({
        id: 'wpt-labels',
        type: 'symbol',
        source: 'geo',
        filter: ['==', ['get', 'kind'], 'wpt'],
        layout: {
          'text-field': ['coalesce', ['get', 'name'], '•'],
          'text-size': 11,
          'text-anchor': 'top',
          'text-offset': [0, 1.2],
        },
        paint: { 'text-color': '#111827', 'text-halo-color': '#fff', 'text-halo-width': 1 },
      });
    }
    if (!m.getLayer('trk-lines')) {
      m.addLayer({
        id: 'trk-lines',
        type: 'line',
        source: 'geo',
        filter: ['==', ['get', 'kind'], 'trk'],
        paint: { 'line-color': '#10b981', 'line-width': 3 },
      });
    }
  };

  const refresh = async () => {
    try {
      const data = await j<FC>(`${API_BASE}/api/geo/features?bbox=${encodeURIComponent(bboxParam())}`);
      (mapRef.current!.getSource('geo') as mapboxgl.GeoJSONSource).setData(data as any);
      const f = data.features;
      const w = f.filter((x) => x.properties?.kind === 'wpt').length;
      const t = f.filter((x) => x.properties?.kind === 'trk').length;
      const cams = new Set(f.filter((x) => x.properties?.trailcam?.id).map((x) => x.properties.trailcam.id)).size;
      setCounts({ features: w + t, cams });
    } catch (e) { console.warn('refresh failed', e); }
  };

  useEffect(() => {
    if (!divRef.current || mapRef.current) return;

    const map = new mapboxgl.Map({
      container: divRef.current,
      style: 'mapbox://styles/mapbox/outdoors-v12',
      center: [-96.5, 41.45],
      zoom: 9.5,
      attributionControl: false,
    });

    // ✅ Capture-phase stopper to block app-level navigation
    const canvasEl = map.getCanvasContainer();
    const captureStop = (e: Event) => {
      e.preventDefault();
      e.stopPropagation();
      // console.log('[CaptureStop]', e.type);
    };
    ['click','dblclick','contextmenu','pointerdown','pointerup','mousedown','mouseup','touchstart','touchend']
      .forEach((evt) => canvasEl.addEventListener(evt, captureStop, { capture: true }));

    map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');
    map.addControl(new Dock(modeRef), 'top-right');

    map.on('load', () => { console.log('[Map] loaded'); ensure(); refresh(); });
    map.on('moveend', refresh);

    map.on('click', async (e) => {
      console.log('[Map] map click @', e.lngLat, 'mode=', modeRef.current);
      if (modeRef.current !== 'add') return;
      try {
        await j(`${API_BASE}/api/geo/waypoints`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: null, lat: e.lngLat.lat, lon: e.lngLat.lng, type: null, trailcam: null }),
        });
        modeRef.current = 'default';
        await refresh();
      } catch (err) { console.error('[Map] add failed', err); }
    });

    const onPointClick = async (ev: mapboxgl.MapLayerMouseEvent) => {
      ev.preventDefault();
      ev.originalEvent?.stopPropagation();
      console.log('[Map] waypoint click mode=', modeRef.current, 'features=', ev.features?.length);
      let fid: string | null = ev.features?.[0]?.id ? String(ev.features![0].id) : null;
      if (!fid) return;
      if (modeRef.current === 'delete') {
        try {
          await j(`${API_BASE}/api/delete/waypoint/${encodeURIComponent(fid)}`, { method: 'DELETE' });
          await refresh();
        } catch (err) { console.error('[Map] delete failed', err); }
        return;
      }
      try {
        const current = (ev.features?.[0]?.properties as any)?.name || '';
        const newName = window.prompt('Rename waypoint:', current);
        if (newName === null) return;
        await j(`${API_BASE}/api/geo/waypoints/${encodeURIComponent(fid)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName }),
        });
        await refresh();
      } catch (err) { console.error('[Map] rename failed', err); }
    };
    ['wpt-circles','wpt-labels'].forEach((l) => {
      map.on('click', l, onPointClick);
      map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
    });

    // ✅ Clean up
    return () => {
      ['click','dblclick','contextmenu','pointerdown','pointerup','mousedown','mouseup','touchstart','touchend']
        .forEach((evt) => canvasEl.removeEventListener(evt, captureStop, { capture: true } as any));
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <div ref={divRef} style={{ position: 'absolute', inset: 0 }} />
      <div
        style={{
          position: 'fixed',
          top: 60,
          right: 12,
          zIndex: 10000,
          background: 'rgba(255,255,255,.85)',
          padding: '2px 6px',
          borderRadius: 6,
          fontSize: 12,
          boxShadow: '0 2px 6px rgba(0,0,0,.08)',
          pointerEvents: 'none',
        }}
      >
        Features: {counts.features} &nbsp; Cams: {counts.cams}
      </div>
    </div>
  );
}
