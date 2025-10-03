// web/pages/gallery.tsx
import { useEffect, useState } from "react";

type LatLon = { lat: number; lon: number };
type ImageHit = {
  id: string;
  bucket?: string | null;
  key?: string | null;
  thumb_key?: string | null;
  capture_time?: string | null;
  location?: LatLon | null;
  camera_model?: string | null;
  labels?: string[];
  url?: string | null;
  thumb_url?: string | null;
};

type SearchResponse = { count: number; items: ImageHit[] };

const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE as string | undefined) ??
  "http://localhost:8000";

export default function GalleryPage() {
  const [items, setItems] = useState<ImageHit[]>([]);
  const [q, setQ] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [err, setErr] = useState<string | null>(null);

  async function runSearch() {
    setLoading(true);
    setErr(null);
    try {
      const url = new URL("/images/search", API_BASE);
      if (q.trim()) url.searchParams.set("q", q.trim());
      const r = await fetch(url.toString());
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data: SearchResponse = await r.json();
      setItems(data.items);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main style={{ padding: 16 }}>
      <h1>Gallery</h1>

      <form
        onSubmit={(ev) => {
          ev.preventDefault();
          void runSearch();
        }}
        style={{ display: "flex", gap: 8, marginTop: 12 }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search labels or key"
          style={{ flex: 1, padding: 8 }}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {err && <p style={{ color: "red", marginTop: 12 }}>{err}</p>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 12,
          marginTop: 16,
        }}
      >
        {items.map((it) => {
          const src = it.thumb_url ?? it.url ?? "";
          const title = it.capture_time ?? it.key ?? it.id;
          return (
            <figure
              key={it.id}
              style={{
                border: "1px solid #eee",
                borderRadius: 8,
                padding: 8,
                background: "#fff",
              }}
            >
              {src ? (
                <img
                  src={src}
                  alt={title ?? "image"}
                  style={{
                    width: "100%",
                    height: 180,
                    objectFit: "cover",
                    borderRadius: 6,
                  }}
                />
              ) : (
                <div
                  style={{ height: 180, background: "#f5f5f5", borderRadius: 6 }}
                />
              )}
              <figcaption style={{ fontSize: 12, marginTop: 8 }}>
                <div>{title}</div>
                {!!(it.labels && it.labels.length) && (
                  <div>labels: {it.labels.join(", ")}</div>
                )}
              </figcaption>
            </figure>
          );
        })}
      </div>
    </main>
  );
}
