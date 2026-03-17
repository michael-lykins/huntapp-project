// web/components/makeIcon.client.ts
'use client';

export function makeIcon(color: string, glyph?: string) {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const L = require('leaflet') as typeof import('leaflet');

  // Keep glyph to a single char/emoji (fallback to empty)
  const g = (glyph || '').toString().slice(0, 2);

  const svg = encodeURIComponent(
    `
<svg width="25" height="41" viewBox="0 0 25 41" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="gloss" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.45"/>
      <stop offset="0.35" stop-color="#ffffff" stop-opacity="0.12"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="rgba(0,0,0,0.35)"/>
    </filter>
  </defs>
  <path filter="url(#shadow)" d="M12.5 0C5.6 0 0 5.6 0 12.5 0 21.9 12.5 41 12.5 41S25 21.9 25 12.5C25 5.6 19.4 0 12.5 0z" fill="${color}"/>
  <path d="M2 5 C8 -2 17 -2 23 5 L23 12 L2 12 Z" fill="url(#gloss)"/>
  <circle cx="12.5" cy="12.5" r="7.5" fill="white"/>
  <text x="12.5" y="13" text-anchor="middle" dominant-baseline="middle" font-family="system-ui, Apple Color Emoji, Segoe UI Emoji" font-size="11">${g}</text>
</svg>`
  );
  const url = `data:image/svg+xml;charset=UTF-8,${svg}`;

  return (L as any).icon({
    iconUrl: url,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [0, -36],
    className: 'hunt-pin',
  });
}
