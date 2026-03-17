'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import mapboxgl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

type Mode = 'default' | 'add' | 'delete';
type FC = { type: 'FeatureCollection'; features: any[] };

interface Camera {
  id: string;
  camera_id: string;
  name: string;
  model?: string;
  property_id?: string;
  property_name?: string;
  lat?: number;
  lon?: number;
  last_transmission_ts?: string;
  battery_level?: string;
  signal_strength?: string;
}

interface Weather {
  temperature?: number;
  wind_speed?: number;
  wind_cardinal?: string;
  pressure_hpa?: number;
  pressure_tendency?: string;
  moon_phase?: string;
  sun_phase?: string;
  label?: string;
}

interface CameraImage {
  id: string;
  filename?: string;
  timestamp?: string;
  url?: string;
  ai_has_animal?: boolean;
  ai_species?: string;
  ai_sex?: string;
  ai_age_class?: string;
  ai_antlers?: string;
  ai_confidence?: number;
  ai_labels?: string[];
  ai_notes?: string;
  has_headshot?: boolean;
  weather?: Weather;
}

interface ActivityHour { hour: number; count: number; }

// ── Activity chart (inline SVG) ───────────────────────────────────────────────

function ActivityChart({ hours }: { hours: ActivityHour[] }) {
  const W = 328, H = 56, pad = 2;
  const barW = (W - pad * 25) / 24;
  const maxCount = Math.max(...hours.map(h => h.count), 1);

  // Dawn/dusk highlight bands
  const dawnStart = 5, dawnEnd = 8, duskStart = 17, duskEnd = 20;
  const xOf = (h: number) => pad + h * (barW + pad);

  return (
    <svg width={W} height={H} style={{ display: 'block', overflow: 'visible' }}>
      {/* Dawn band */}
      <rect
        x={xOf(dawnStart)} y={0}
        width={xOf(dawnEnd) - xOf(dawnStart)} height={H}
        fill="rgba(251,191,36,.08)" rx={3}
      />
      {/* Dusk band */}
      <rect
        x={xOf(duskStart)} y={0}
        width={xOf(duskEnd) - xOf(duskStart)} height={H}
        fill="rgba(251,191,36,.08)" rx={3}
      />
      {hours.map(({ hour, count }) => {
        const barH = count === 0 ? 2 : Math.max(4, (count / maxCount) * (H - 8));
        const x = xOf(hour);
        const isDawnDusk = (hour >= dawnStart && hour < dawnEnd) || (hour >= duskStart && hour < duskEnd);
        const fill = count === 0 ? '#1f2937' : isDawnDusk ? '#fbbf24' : '#10b981';
        return (
          <g key={hour}>
            <rect x={x} y={H - barH} width={barW} height={barH} rx={1.5} fill={fill} opacity={count === 0 ? 0.4 : 0.9} />
            {/* Hour labels: midnight, 6am, noon, 6pm */}
            {[0, 6, 12, 18].includes(hour) && (
              <text x={x + barW / 2} y={H + 10} textAnchor="middle" fontSize={8} fill="#4b5563">
                {hour === 0 ? '12a' : hour === 6 ? '6a' : hour === 12 ? '12p' : '6p'}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000').replace(/\/$/, '');

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

function relativeTime(ts?: string): string {
  if (!ts) return 'unknown';
  const diff = Date.now() - new Date(ts).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

function batteryColor(level?: string): string {
  if (!level) return '#6b7280';
  const n = parseFloat(level);
  if (n > 60) return '#10b981';
  if (n > 30) return '#f59e0b';
  return '#ef4444';
}

// ── Side Panel ────────────────────────────────────────────────────────────────

interface PanelProps {
  camera: Camera | null;
  onClose: () => void;
}

function CameraPanel({ camera, onClose }: PanelProps) {
  const [images, setImages] = useState<CameraImage[]>([]);
  const [stats, setStats] = useState<{ species: { species: string; count: number }[]; animal_photos: number } | null>(null);
  const [activity, setActivity] = useState<{ hours: ActivityHour[]; peak_hour: number | null; total: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [animalsOnly, setAnimalsOnly] = useState(false);
  const [selected, setSelected] = useState<CameraImage | null>(null);

  useEffect(() => {
    if (!camera) return;
    setImages([]);
    setStats(null);
    setActivity(null);
    setSelected(null);
    setLoading(true);

    const cid = encodeURIComponent(camera.camera_id);
    Promise.all([
      fetch(`${API_BASE}/api/trailcams/${cid}/images?limit=12&animals_only=${animalsOnly}`).then(r => r.json()),
      fetch(`${API_BASE}/api/trailcams/${cid}/stats`).then(r => r.json()),
      fetch(`${API_BASE}/api/trailcams/${cid}/activity`).then(r => r.json()),
    ])
      .then(([imgs, st, act]) => {
        setImages(imgs.images ?? []);
        setStats(st);
        setActivity(act);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [camera, animalsOnly]);

  if (!camera) return null;

  const confPct = selected?.ai_confidence != null ? Math.round(selected.ai_confidence * 100) : null;

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0,
      width: 360, background: '#111827', color: '#f9fafb',
      display: 'flex', flexDirection: 'column',
      boxShadow: '-4px 0 24px rgba(0,0,0,.4)', zIndex: 20000,
      fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid #1f2937' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.2 }}>{camera.name}</div>
            <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
              {camera.property_name || camera.property_id || 'Unknown property'} &middot; {camera.model || 'Tactacam'}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 20, padding: 4, lineHeight: 1 }}
          >&#x2715;</button>
        </div>

        {/* Status badges */}
        <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
          <span style={{ background: '#1f2937', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#d1d5db' }}>
            Last: {relativeTime(camera.last_transmission_ts)}
          </span>
          {camera.battery_level && (
            <span style={{ background: '#1f2937', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: batteryColor(camera.battery_level) }}>
              Batt: {camera.battery_level}
            </span>
          )}
          {camera.signal_strength && (
            <span style={{ background: '#1f2937', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#d1d5db' }}>
              Signal: {camera.signal_strength}
            </span>
          )}
        </div>

        {/* Species stats */}
        {stats && stats.species.length > 0 && (
          <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {stats.species.slice(0, 6).map(s => (
              <span key={s.species} style={{
                background: '#065f46', color: '#6ee7b7', borderRadius: 12,
                padding: '2px 8px', fontSize: 11,
              }}>
                {s.species} x{s.count}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Activity chart */}
      {activity && activity.total > 0 && (
        <div style={{ padding: '10px 16px 14px', borderBottom: '1px solid #1f2937' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Activity</span>
            {activity.peak_hour != null && (
              <span style={{ fontSize: 11, color: '#fbbf24' }}>
                Peak {activity.peak_hour < 12 ? `${activity.peak_hour}am` : activity.peak_hour === 12 ? '12pm' : `${activity.peak_hour - 12}pm`}
              </span>
            )}
            <span style={{ fontSize: 11, color: '#4b5563', marginLeft: 'auto' }}>{activity.total} sightings</span>
          </div>
          <ActivityChart hours={activity.hours} />
          <div style={{ display: 'flex', gap: 12, marginTop: 10, fontSize: 10, color: '#4b5563' }}>
            <span><span style={{ color: '#fbbf24' }}>▪</span> dawn/dusk</span>
            <span><span style={{ color: '#10b981' }}>▪</span> other hours</span>
          </div>
        </div>
      )}

      {/* Controls */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #1f2937', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12, color: '#9ca3af' }}>Recent photos</span>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#9ca3af', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={animalsOnly}
            onChange={e => setAnimalsOnly(e.target.checked)}
            style={{ accentColor: '#10b981' }}
          />
          Animals only
        </label>
      </div>

      {/* Image grid / detail view */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {selected ? (
          /* ── Detail view ── */
          <div>
            <div style={{ position: 'relative' }}>
              <img
                src={selected.url!}
                alt={selected.filename}
                style={{ width: '100%', maxHeight: 240, objectFit: 'cover', display: 'block' }}
              />
              <button
                onClick={() => setSelected(null)}
                style={{
                  position: 'absolute', top: 8, left: 8,
                  background: 'rgba(0,0,0,.65)', border: 'none', color: '#fff',
                  borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12,
                }}
              >← back</button>
            </div>
            <div style={{ padding: '12px 14px 16px', fontSize: 13 }}>
              {selected.ai_species ? (
                <div style={{ fontSize: 16, fontWeight: 700, color: '#34d399', marginBottom: 6 }}>
                  {selected.ai_species}
                  {selected.ai_sex && selected.ai_sex !== 'unknown' && ` · ${selected.ai_sex}`}
                  {selected.ai_age_class && selected.ai_age_class !== 'unknown' && ` · ${selected.ai_age_class}`}
                </div>
              ) : (
                <div style={{ color: '#6b7280', marginBottom: 6 }}>No animal detected</div>
              )}
              {confPct != null && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 12 }}>
                    <span style={{ color: '#9ca3af' }}>Confidence</span>
                    <span style={{ color: '#f9fafb' }}>{confPct}%</span>
                  </div>
                  <div style={{ height: 5, background: '#1f2937', borderRadius: 3 }}>
                    <div style={{
                      height: 5, borderRadius: 3, width: `${confPct}%`,
                      background: confPct > 70 ? '#10b981' : confPct > 40 ? '#f59e0b' : '#ef4444',
                    }} />
                  </div>
                </div>
              )}
              {selected.ai_antlers && (
                <div style={{ color: '#d1d5db', marginBottom: 4, fontSize: 12 }}>Rack: {selected.ai_antlers}</div>
              )}
              {selected.ai_notes && (
                <div style={{ color: '#9ca3af', fontStyle: 'italic', fontSize: 12, lineHeight: 1.4 }}>"{selected.ai_notes}"</div>
              )}
              <div style={{ color: '#4b5563', marginTop: 8, fontSize: 11 }}>
                {selected.timestamp ? new Date(selected.timestamp).toLocaleString() : ''}
                {selected.has_headshot && <span style={{ marginLeft: 8, color: '#fbbf24' }}>headshot</span>}
              </div>
              {/* Weather conditions at time of capture */}
              {selected.weather && (
                <div style={{
                  marginTop: 10, padding: '8px 10px', background: '#0f172a',
                  borderRadius: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px',
                  fontSize: 11, color: '#6b7280',
                }}>
                  {selected.weather.temperature != null && (
                    <span>🌡 {Math.round(selected.weather.temperature)}°F</span>
                  )}
                  {selected.weather.wind_speed != null && (
                    <span>💨 {Math.round(selected.weather.wind_speed)}mph {selected.weather.wind_cardinal || ''}</span>
                  )}
                  {selected.weather.pressure_tendency && (
                    <span>
                      {selected.weather.pressure_tendency === 'falling' ? '📉' : selected.weather.pressure_tendency === 'rising' ? '📈' : '➡'} {selected.weather.pressure_tendency}
                    </span>
                  )}
                  {selected.weather.moon_phase && (
                    <span>🌕 {selected.weather.moon_phase}</span>
                  )}
                  {selected.weather.sun_phase && (
                    <span style={{ color: '#fbbf24' }}>{selected.weather.sun_phase}</span>
                  )}
                  {selected.weather.label && (
                    <span style={{ gridColumn: '1 / -1', color: '#9ca3af' }}>{selected.weather.label}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ── Thumbnail grid ── */
          <div style={{ padding: 12 }}>
            {loading && (
              <div style={{ color: '#6b7280', textAlign: 'center', padding: 32 }}>Loading...</div>
            )}
            {!loading && images.length === 0 && (
              <div style={{ color: '#6b7280', textAlign: 'center', padding: 32 }}>No images found</div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
              {images.map(img => (
                <div
                  key={img.id}
                  onClick={() => setSelected(img)}
                  style={{
                    position: 'relative', cursor: 'pointer',
                    borderRadius: 8, overflow: 'hidden', aspectRatio: '1',
                    background: '#1f2937',
                  }}
                >
                  {img.url ? (
                    <img src={img.url} alt={img.filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4b5563', fontSize: 11 }}>
                      no img
                    </div>
                  )}
                  {img.ai_has_animal && img.ai_species && (
                    <div style={{
                      position: 'absolute', bottom: 0, left: 0, right: 0,
                      background: 'linear-gradient(transparent, rgba(0,0,0,.8))',
                      padding: '12px 4px 4px', fontSize: 9, color: '#d1d5db',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    }}>
                      {img.ai_species}
                    </div>
                  )}
                  {img.has_headshot && (
                    <div style={{ position: 'absolute', top: 3, right: 3, fontSize: 10, color: '#fbbf24', background: 'rgba(0,0,0,.5)', borderRadius: 4, padding: '0 3px' }}>HS</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}



// ── Intel Chat ─────────────────────────────────────────────────────────────────

interface IntelImage {
  doc_id: string;
  url?: string;
  camera_name?: string;
  ai_species?: string;
  ai_sex?: string;
  ai_age_class?: string;
  ai_antlers?: string;
  ai_confidence?: number;
  ai_notes?: string;
  timestamp?: string;
  score?: number;
}

interface IntelMessage {
  role: 'user' | 'assistant';
  text: string;
  esql?: string;
  rows?: number;
  error?: string;
  cost_usd?: number;
  tokens_in?: number;
  tokens_out?: number;
  images?: IntelImage[];
}

const STARTER_QUESTIONS = [
  'Which camera has the most mature buck activity?',
  'When do deer move most at my cameras?',
  'Which stand should I sit on a falling barometer?',
  'Show me raccoon activity by camera',
];

function IntelChat({ cameraPanelOpen }: { cameraPanelOpen: boolean }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<IntelMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const ask = async (question: string) => {
    if (!question.trim() || loading) return;
    const userMsg: IntelMessage = { role: 'user', text: question };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/intel/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        esql: data.esql_query,
        rows: data.row_count,
        error: data.error,
        cost_usd: data.cost_usd,
        tokens_in: data.tokens_in,
        tokens_out: data.tokens_out,
        images: data.images ?? [],
      }]);
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', text: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          position: 'fixed', bottom: 24, right: open ? 384 : 24,
          width: 52, height: 52, borderRadius: '50%',
          background: open ? '#1f2937' : '#166534',
          border: '2px solid ' + (open ? '#374151' : '#15803d'),
          color: '#fff', cursor: 'pointer',
          boxShadow: '0 4px 16px rgba(0,0,0,.35)',
          fontSize: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 30000, transition: 'right .2s ease, background .15s',
        }}
        title="Hunting Intel Chat"
      >
        {open ? '✕' : '🤖'}
      </button>

      {/* Chat panel */}
      {open && (
        <div style={{
          position: 'fixed', bottom: 0, right: cameraPanelOpen ? 360 : 0,
          width: 380, height: '60vh', maxHeight: 560, minHeight: 300,
          background: '#0f172a', color: '#f9fafb', borderRadius: '12px 12px 0 0',
          boxShadow: '-4px 0 32px rgba(0,0,0,.5)', zIndex: 25000,
          display: 'flex', flexDirection: 'column',
          fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        }}>
          {/* Header */}
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid #1f2937',
            display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
          }}>
            <span style={{ fontSize: 18 }}>🎯</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14 }}>Hunting Intel</div>
              <div style={{ fontSize: 11, color: '#4b5563' }}>Claude + Elasticsearch · {messages.filter(m => m.role === 'user').length} queries</div>
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.length === 0 && (
              <div>
                <div style={{ color: '#4b5563', fontSize: 12, marginBottom: 12 }}>
                  Ask anything about your cameras, species patterns, or stand timing.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {STARTER_QUESTIONS.map(q => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      style={{
                        background: '#1f2937', border: '1px solid #374151',
                        color: '#d1d5db', borderRadius: 8, padding: '8px 12px',
                        textAlign: 'left', cursor: 'pointer', fontSize: 12, lineHeight: 1.4,
                      }}
                    >{q}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '88%', padding: '8px 12px', borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                  background: msg.role === 'user' ? '#166534' : '#1e293b',
                  fontSize: 13, lineHeight: 1.5, color: msg.role === 'user' ? '#d1fae5' : '#e2e8f0',
                }}>
                  {msg.text}
                </div>
                {msg.role === 'assistant' && (msg.esql || msg.rows != null || msg.cost_usd != null) && (
                  <div style={{ fontSize: 10, color: '#374151', marginTop: 3, paddingLeft: 4, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    {msg.rows != null && <span>{msg.rows} rows</span>}
                    {msg.cost_usd != null && (
                      <span style={{ color: '#166534' }} title={`${msg.tokens_in} in / ${msg.tokens_out} out tokens`}>
                        ${msg.cost_usd < 0.001 ? '<$0.001' : `$${msg.cost_usd.toFixed(4)}`}
                      </span>
                    )}
                    {msg.esql && (
                      <details>
                        <summary style={{ cursor: 'pointer', color: '#4b5563' }}>ES|QL</summary>
                        <pre style={{
                          marginTop: 4, padding: '6px 8px', background: '#1e293b',
                          borderRadius: 6, fontSize: 10, color: '#64748b',
                          overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                        }}>{msg.esql}</pre>
                      </details>
                    )}
                  </div>
                )}
                {msg.role === 'assistant' && msg.images && msg.images.length > 0 && (
                  <div style={{ marginTop: 8, width: '100%' }}>
                    <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 4 }}>
                      📷 {msg.images.length} relevant images · Elastic ELSER
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4 }}>
                      {msg.images.map(img => (
                        <div key={img.doc_id} style={{
                          position: 'relative', borderRadius: 6, overflow: 'hidden',
                          aspectRatio: '1', background: '#1e293b', border: '1px solid #374151',
                        }}>
                          {img.url ? (
                            <img src={img.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: '#4b5563' }}>no img</div>
                          )}
                          {img.ai_species && (
                            <div style={{
                              position: 'absolute', bottom: 0, left: 0, right: 0,
                              background: 'linear-gradient(transparent, rgba(0,0,0,.85))',
                              padding: '8px 3px 3px', fontSize: 8, color: '#d1d5db',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                            }}>{img.ai_species}</div>
                          )}
                          {img.camera_name && (
                            <div style={{
                              position: 'absolute', top: 2, left: 2,
                              background: 'rgba(0,0,0,.6)', borderRadius: 3,
                              padding: '1px 3px', fontSize: 7, color: '#9ca3af',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                              maxWidth: '90%',
                            }}>{img.camera_name}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ color: '#4b5563', fontSize: 13, fontStyle: 'italic' }}>Thinking…</div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ padding: '10px 12px', borderTop: '1px solid #1f2937', display: 'flex', gap: 8, flexShrink: 0 }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && ask(input)}
              placeholder="Ask about your cameras…"
              style={{
                flex: 1, background: '#1e293b', border: '1px solid #374151',
                borderRadius: 8, padding: '8px 12px', color: '#f9fafb', fontSize: 13,
                outline: 'none',
              }}
            />
            <button
              onClick={() => ask(input)}
              disabled={loading || !input.trim()}
              style={{
                background: '#166534', border: 'none', borderRadius: 8,
                padding: '8px 14px', color: '#fff', cursor: 'pointer',
                fontSize: 13, opacity: (loading || !input.trim()) ? 0.5 : 1,
              }}
            >Send</button>
          </div>
        </div>
      )}
    </>
  );
}

// ── Dock control ───────────────────────────────────────────────────────────────

class Dock implements mapboxgl.IControl {
  private el!: HTMLElement;
  private modeRef: React.MutableRefObject<Mode>;
  constructor(modeRef: React.MutableRefObject<Mode>) { this.modeRef = modeRef; }
  getDefaultPosition(): mapboxgl.ControlPosition { return 'top-right'; }
  onAdd() {
    const box = document.createElement('div');
    box.style.cssText = 'display:flex;gap:8px;background:rgba(255,255,255,.95);border-radius:12px;padding:8px;box-shadow:0 6px 16px rgba(0,0,0,.12);z-index:999999;';
    const mk = (label: string, title: string, on: () => void, color?: string) => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = label; b.title = title;
      b.style.cssText = 'padding:8px 10px;border-radius:10px;background:#fff;border:1px solid rgba(0,0,0,.08);cursor:pointer;font-size:12px;';
      if (color) b.style.color = color;
      const h = (e: Event) => { e.preventDefault(); e.stopPropagation(); on(); };
      ['click','mousedown','mouseup','touchstart','touchend','contextmenu'].forEach(ev =>
        b.addEventListener(ev, h, { passive: false } as any));
      return b;
    };
    const addBtn = mk('Add', 'Add waypoint', () => {
      this.modeRef.current = this.modeRef.current === 'add' ? 'default' : 'add';
      addBtn.style.boxShadow = this.modeRef.current === 'add' ? '0 0 0 2px #3b82f6' : 'none';
      delBtn.style.boxShadow = 'none';
    });
    const delBtn = mk('Delete', 'Delete waypoint', () => {
      this.modeRef.current = this.modeRef.current === 'delete' ? 'default' : 'delete';
      delBtn.style.boxShadow = this.modeRef.current === 'delete' ? '0 0 0 2px #ef4444' : 'none';
      addBtn.style.boxShadow = 'none';
    }, '#b91c1c');
    ['click','mousedown','mouseup','touchstart','touchend','wheel','contextmenu'].forEach(ev =>
      box.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }, { passive: false }));
    box.append(addBtn, delBtn);
    this.el = box;
    return box;
  }
  onRemove() { this.el?.parentNode?.removeChild(this.el); }
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function MapClient() {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const divRef = useRef<HTMLDivElement | null>(null);
  const modeRef = useRef<Mode>('default');
  const [counts, setCounts] = useState({ features: 0 });
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [activeCamera, setActiveCamera] = useState<Camera | null>(null);
  const camerasRef = useRef<Camera[]>([]);

  useEffect(() => { camerasRef.current = cameras; }, [cameras]);

  // Load cameras from API
  useEffect(() => {
    fetch(`${API_BASE}/api/trailcams`)
      .then(r => r.json())
      .then(data => setCameras(data.cameras ?? []))
      .catch(err => console.warn('Failed to load cameras', err));
  }, []);

  const bboxParam = () => {
    const b = mapRef.current!.getBounds()!;
    return `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
  };

  const ensureWaypointLayers = (map: mapboxgl.Map) => {
    if (!map.getSource('geo')) {
      map.addSource('geo', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        promoteId: 'id',
        generateId: true,
      });
    }
    if (!map.getLayer('wpt-circles')) {
      map.addLayer({
        id: 'wpt-circles', type: 'circle', source: 'geo',
        filter: ['==', ['get', 'kind'], 'wpt'],
        paint: { 'circle-color': '#0ea5e9', 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5, 'circle-radius': 6 },
      });
    }
    if (!map.getLayer('wpt-labels')) {
      map.addLayer({
        id: 'wpt-labels', type: 'symbol', source: 'geo',
        filter: ['==', ['get', 'kind'], 'wpt'],
        layout: { 'text-field': ['coalesce', ['get', 'name'], '.'], 'text-size': 11, 'text-anchor': 'top', 'text-offset': [0, 1.2] },
        paint: { 'text-color': '#111827', 'text-halo-color': '#fff', 'text-halo-width': 1 },
      });
    }
    if (!map.getLayer('trk-lines')) {
      map.addLayer({
        id: 'trk-lines', type: 'line', source: 'geo',
        filter: ['==', ['get', 'kind'], 'trk'],
        paint: { 'line-color': '#10b981', 'line-width': 3 },
      });
    }
  };

  const refresh = async (map: mapboxgl.Map) => {
    try {
      const data = await j<FC>(`${API_BASE}/api/geo/features?bbox=${encodeURIComponent(bboxParam())}`);
      (map.getSource('geo') as mapboxgl.GeoJSONSource).setData(data as any);
      const f = data.features;
      const w = f.filter((x: any) => x.properties?.kind === 'wpt').length;
      const t = f.filter((x: any) => x.properties?.kind === 'trk').length;
      setCounts({ features: w + t });
    } catch (e) { console.warn('refresh failed', e); }
  };

  const loadCameraLayer = useCallback((map: mapboxgl.Map, cams: Camera[]) => {
    const features = cams
      .filter(c => c.lat != null && c.lon != null)
      .map(c => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [c.lon!, c.lat!] },
        properties: { id: c.camera_id, name: c.name, property: c.property_name || c.property_id || '' },
      }));

    const src = map.getSource('trailcams') as mapboxgl.GeoJSONSource | undefined;
    if (src) { src.setData({ type: 'FeatureCollection', features }); return; }

    map.addSource('trailcams', { type: 'geojson', data: { type: 'FeatureCollection', features } });
    map.addLayer({ id: 'cam-glow', type: 'circle', source: 'trailcams', paint: { 'circle-radius': 16, 'circle-color': '#f97316', 'circle-opacity': 0.18, 'circle-stroke-width': 0 } });
    map.addLayer({ id: 'cam-circles', type: 'circle', source: 'trailcams', paint: { 'circle-radius': 8, 'circle-color': '#f97316', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2.5 } });
    map.addLayer({ id: 'cam-labels', type: 'symbol', source: 'trailcams', layout: { 'text-field': ['get', 'name'], 'text-size': 11, 'text-anchor': 'top', 'text-offset': [0, 1.4], 'text-max-width': 10 }, paint: { 'text-color': '#111827', 'text-halo-color': '#fff', 'text-halo-width': 1.5 } });
  }, []);

  useEffect(() => {
    if (!divRef.current || mapRef.current) return;

    const map = new mapboxgl.Map({
      container: divRef.current,
      style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
      center: [-96.5, 41.45],
      zoom: 9.5,
      attributionControl: false,
    });


    map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');
    map.addControl(new Dock(modeRef), 'top-right');

    map.on('load', () => {
      ensureWaypointLayers(map);
      refresh(map);
      if (camerasRef.current.length > 0) loadCameraLayer(map, camerasRef.current);
    });
    map.on('moveend', () => refresh(map));

    map.on('click', async e => {
      if (modeRef.current !== 'add') return;
      try {
        await j(`${API_BASE}/api/geo/waypoints`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: null, lat: e.lngLat.lat, lon: e.lngLat.lng, type: null, trailcam: null }),
        });
        modeRef.current = 'default';
        await refresh(map);
      } catch (err) { console.error('[Map] add failed', err); }
    });

    const onWptClick = async (ev: mapboxgl.MapLayerMouseEvent) => {
      ev.preventDefault(); ev.originalEvent?.stopPropagation();
      const fid = ev.features?.[0]?.id ? String(ev.features![0].id) : null;
      if (!fid) return;
      if (modeRef.current === 'delete') {
        try {
          await j(`${API_BASE}/api/delete/waypoint/${encodeURIComponent(fid)}`, { method: 'DELETE' });
          await refresh(map);
        } catch (err) { console.error('[Map] delete failed', err); }
        return;
      }
      const current = (ev.features?.[0]?.properties as any)?.name || '';
      const newName = window.prompt('Rename waypoint:', current);
      if (newName === null) return;
      try {
        await j(`${API_BASE}/api/geo/waypoints/${encodeURIComponent(fid)}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName }),
        });
        await refresh(map);
      } catch (err) { console.error('[Map] rename failed', err); }
    };

    ['wpt-circles','wpt-labels'].forEach(l => {
      map.on('click', l, onWptClick);
      map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
    });

    const onCamClick = (ev: mapboxgl.MapLayerMouseEvent) => {
      ev.preventDefault(); ev.originalEvent?.stopPropagation();
      const camId = (ev.features?.[0]?.properties as any)?.id;
      if (!camId) return;
      const cam = camerasRef.current.find(c => c.camera_id === camId);
      if (cam) setActiveCamera(cam);
    };

    ['cam-circles','cam-labels','cam-glow'].forEach(l => {
      map.on('click', l, onCamClick);
      map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When cameras load, add/update layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || cameras.length === 0) return;
    if (map.loaded()) loadCameraLayer(map, cameras);
    else map.once('load', () => loadCameraLayer(map, cameras));
  }, [cameras, loadCameraLayer]);

  // Fit map to all cameras on first load
  const fittedRef = useRef(false);
  useEffect(() => {
    if (fittedRef.current || cameras.length === 0) return;
    const map = mapRef.current;
    if (!map) return;
    fittedRef.current = true;
    const valid = cameras.filter(c => c.lat != null && c.lon != null);
    if (valid.length < 2) return;
    const lngs = valid.map(c => c.lon!);
    const lats = valid.map(c => c.lat!);
    const bounds = new mapboxgl.LngLatBounds([Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]);
    const doFit = () => map.fitBounds(bounds, { padding: 80, maxZoom: 13, animate: false });
    if (map.loaded()) doFit();
    else map.once('load', doFit);
  }, [cameras]);

  const properties = Array.from(new Set(cameras.map(c => c.property_name || c.property_id || 'Unknown')));

  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <div
        ref={divRef}
        style={{
          position: 'absolute', top: 0, bottom: 0, left: 0,
          right: activeCamera ? 360 : 0,
          transition: 'right .2s ease',
        }}
      />

      {/* Stats HUD */}
      <div style={{
        position: 'fixed', top: 12, left: 12, zIndex: 10000,
        background: 'rgba(255,255,255,.9)', padding: '4px 10px', borderRadius: 8, fontSize: 12,
        boxShadow: '0 2px 6px rgba(0,0,0,.1)', pointerEvents: 'none',
      }}>
        {cameras.length} cameras &nbsp;|&nbsp; {counts.features} waypoints
      </div>

      {/* Property legend */}
      {properties.length > 1 && (
        <div style={{
          position: 'fixed', bottom: 60, left: 12, zIndex: 10000,
          background: 'rgba(255,255,255,.92)', borderRadius: 10, padding: '8px 12px',
          boxShadow: '0 2px 8px rgba(0,0,0,.1)', fontSize: 12,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4, color: '#111827' }}>Properties</div>
          {properties.map(p => (
            <div key={p} style={{ color: '#374151', marginBottom: 2 }}>
              <span style={{ color: '#f97316' }}>&#9679;</span> {p} ({cameras.filter(c => (c.property_name || c.property_id || 'Unknown') === p).length})
            </div>
          ))}
        </div>
      )}

      <CameraPanel camera={activeCamera} onClose={() => setActiveCamera(null)} />
      <IntelChat cameraPanelOpen={activeCamera !== null} />
    </div>
  );
}
