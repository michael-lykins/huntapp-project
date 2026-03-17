"use client";

import React, { useEffect, useMemo, useState } from "react";

type WaypointTypeKey =
  | "location"
  | "bedding_area"
  | "ladder_stand"
  | "saddle"
  | "blind"
  | "food_plot"
  | "trail"
  | "tree_stand"
  | "tracks"
  | "other";

export type WaypointDraft = {
  id?: string;
  name: string;
  type?: WaypointTypeKey | null;
  color?: string | null;
  notes?: string | null;
  lat: number;
  lon: number;
};

type Props = {
  open: boolean;
  draft: WaypointDraft | null;
  onClose: () => void;
  onSave: (draft: WaypointDraft) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
};

const TYPE_DEFS: { key: WaypointTypeKey; label: string; icon: React.JSX.Element }[] = [
  { key: "location",     label: "Location",     icon: <span style={{fontSize:22}}>📍</span> },
  { key: "bedding_area", label: "Bedding Area", icon: <span style={{fontSize:22}}>🛏️</span> },
  { key: "ladder_stand", label: "Ladder Stand", icon: <span style={{fontSize:22}}>🪜</span> },
  { key: "saddle",       label: "Saddle",       icon: <span style={{fontSize:22}}>🪢</span> },
  { key: "blind",        label: "Blind",        icon: <span style={{fontSize:22}}>🫣</span> },
  { key: "food_plot",    label: "Food Plot",    icon: <span style={{fontSize:22}}>🌾</span> },
  { key: "trail",        label: "Trail",        icon: <span style={{fontSize:22}}>〰️</span> },
  { key: "tree_stand",   label: "Tree Stand",   icon: <span style={{fontSize:22}}>🌳</span> },
  { key: "tracks",       label: "Tracks",       icon: <span style={{fontSize:22}}>🐾</span> },
  { key: "other",        label: "More",         icon: <span style={{fontSize:22}}>➕</span> },
];

const COLORS = [
  "#E4472D", // red-orange
  "#3162F3", // blue
  "#69F2F2", // cyan
  "#8BCB2C", // green
  "#000000", // black
  "#FFFFFF", // white (outline)
  "#5E127D", // purple
  "#FFEF42", // yellow
  "#E22A21", // red
  "#6C3A1C", // brown
];

export default function WaypointModal({ open, draft, onClose, onSave, onDelete }: Props) {
  const [name, setName]     = useState("");
  const [type, setType]     = useState<WaypointTypeKey | null>("location");
  const [color, setColor]   = useState<string | null>("#E4472D");
  const [notes, setNotes]   = useState<string | null>("");
  const [lat, setLat]       = useState<number>(0);
  const [lon, setLon]       = useState<number>(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !draft) return;
    setName(draft.name ?? "");
    setType(draft.type ?? "location");
    setColor(draft.color ?? "#E4472D");
    setNotes(draft.notes ?? "");
    setLat(draft.lat);
    setLon(draft.lon);
  }, [open, draft]);

  const valid = useMemo(() => name.trim().length > 0 && Number.isFinite(lat) && Number.isFinite(lon), [name, lat, lon]);

  if (!open || !draft) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        background: "rgba(0,0,0,.35)", display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(720px, 92vw)", maxHeight: "90vh", overflow: "auto",
          background: "#fff", borderRadius: 18, boxShadow: "0 20px 60px rgba(0,0,0,.25)", padding: 20,
        }}
      >
        {/* Title + Close */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontWeight: 800, fontSize: 24 }}>Waypoint</h2>
          <button
            onClick={onClose}
            style={{ border: "none", background: "transparent", fontSize: 24, cursor: "pointer", lineHeight: 1 }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Name */}
        <label style={{ display: "block", fontSize: 14, fontWeight: 700, marginBottom: 6 }}>Waypoint Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Waypoint name"
          style={{
            width: "100%", border: "1px solid #e5e7eb", borderRadius: 10, padding: "12px 14px",
            fontSize: 16, marginBottom: 18, outline: "none",
          }}
        />

        {/* Types */}
        <div style={{ borderTop: "1px solid #eee", paddingTop: 10, marginTop: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 10 }}>Type</div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
              gap: 12,
              marginBottom: 16,
            }}
          >
            {TYPE_DEFS.map((t) => {
              const active = type === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setType(t.key)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    border: active ? "2px solid #111" : "1px solid #e5e7eb",
                    borderRadius: 12, padding: "10px 12px", background: "#fff", cursor: "pointer",
                  }}
                >
                  <span aria-hidden>{t.icon}</span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Color */}
        <div style={{ borderTop: "1px solid #eee", paddingTop: 10, marginTop: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 10 }}>Color</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 10 }}>
            {COLORS.map((c) => {
              const active = color === c;
              return (
                <button
                  key={c}
                  onClick={() => setColor(c)}
                  title={c}
                  style={{
                    width: 38, height: 38, borderRadius: "50%",
                    border: active ? "3px solid #111" : "2px solid #ddd",
                    background: c,
                    cursor: "pointer",
                  }}
                />
              );
            })}
          </div>
        </div>

        {/* Notes */}
        <div style={{ borderTop: "1px solid #eee", paddingTop: 10, marginTop: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 8 }}>Notes</div>
          <textarea
            value={notes ?? ""}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={512}
            rows={5}
            placeholder="Add any details here…"
            style={{
              width: "100%", border: "1px solid #e5e7eb", borderRadius: 10,
              padding: 12, fontSize: 15, resize: "vertical",
            }}
          />
          <div style={{ textAlign: "right", fontSize: 12, color: "#666" }}>
            {512 - (notes?.length ?? 0)} characters remaining
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 12, marginTop: 18 }}>
          {draft.id && onDelete ? (
            <button
              onClick={async () => { if (!draft.id) return; await onDelete(draft.id); }}
              style={{
                flex: "0 0 auto", minWidth: 140,
                background: "#efefef", color: "#222", border: "none", borderRadius: 12,
                fontWeight: 800, padding: "12px 16px", cursor: "pointer",
              }}
            >
              Delete
            </button>
          ) : (
            <div />
          )}

          <div style={{ flex: 1 }} />

          <button
            disabled={!valid || saving}
            onClick={async () => {
              if (!valid || !draft) return;
              setSaving(true);
              await onSave({
                ...draft,
                name: name.trim(),
                type: (type ?? undefined) as WaypointTypeKey | undefined,
                color: color ?? undefined,
                notes: notes ?? undefined,
                lat, lon
              });
              setSaving(false);
            }}
            style={{
              minWidth: 160,
              background: "#E4472D", color: "white",
              border: "none", borderRadius: 12, fontWeight: 900,
              padding: "12px 18px", cursor: valid && !saving ? "pointer" : "not-allowed",
              opacity: valid ? 1 : .6,
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
