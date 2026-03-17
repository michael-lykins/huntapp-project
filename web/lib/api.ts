// web/lib/api.ts
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") || "http://localhost:8000";

export type HuntEvent = {
  id: string;
  timestamp: string;
  event_type: string;
  note?: string | null;
  species?: string | null;
  spot_id?: string | null;
  color?: string | null;
  glyph?: string | null;
  category?: string | null;
  geo?: { lat: number | string; lon: number | string };
  lat?: number | string | null;
  lon?: number | string | null;
};

export type NearResponse = {
  count: number;
  items: HuntEvent[];
};

function toNumber(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) return Number(v);
  return null;
}

export function normalizeLatLon(ev: HuntEvent): { lat: number; lon: number } | null {
  const lat = toNumber(ev.lat) ?? toNumber(ev.geo?.lat);
  const lon = toNumber(ev.lon) ?? toNumber(ev.geo?.lon);
  if (lat == null || lon == null) return null;
  return { lat, lon };
}

/** List events (pins). Backend has no "near" filter yet; use limit to cap results. */
export async function getNearbyEvents(args: {
  lat: number;
  lon: number;
  radius_m: number;
  limit?: number;
}): Promise<NearResponse> {
  const limit = args.limit ?? 50;
  const res = await fetch(`${API_BASE}/api/events?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`events failed: ${res.status} ${res.statusText} ${txt}`);
  }
  const items = (await res.json()) as HuntEvent[];
  return { count: items.length, items };
}

export async function postPin(args: {
  lat: number;
  lon: number;
  note?: string;
  species?: string;
  color?: string;
  glyph?: string;
  category?: string;
}) {
  const res = await fetch(`${API_BASE}/api/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`pin failed: ${res.status} ${res.statusText} ${txt}`);
  }
  return res.json();
}
