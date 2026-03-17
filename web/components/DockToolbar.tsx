'use client';

type Props = {
  onAddWaypoint: () => void;
  onUpload: () => void;
  onToggleDeleteMode: () => void;
  onLayerToggle: () => void;
  mode: 'default' | 'add' | 'delete';
};

// tiny inline SVGs so we have zero dependencies
const Icon = {
  MapPin: () => (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 22s8-4.5 8-10a8 8 0 1 0-16 0c0 5.5 8 10 8 10z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  Upload: () => (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M7 10l5-5 5 5" />
      <path d="M12 15V5" />
    </svg>
  ),
  Layers3: () => (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2l9 4.5-9 4.5L3 6.5 12 2z" />
      <path d="M3 12.5l9 4.5 9-4.5" />
      <path d="M3 17.5l9 4.5 9-4.5" />
    </svg>
  ),
  Trash2: () => (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  ),
};

export default function DockToolbar({
  onAddWaypoint,
  onUpload,
  onToggleDeleteMode,
  onLayerToggle,
  mode,
}: Props) {
  const btn = "p-2 rounded-xl hover:bg-gray-100";
  const wrap = "fixed top-4 right-4 z-[1000] flex flex-col gap-2 p-2 rounded-2xl shadow-lg bg-white/90 backdrop-blur";

  return (
    <div className={wrap}>
      <button
        className={`${btn} ${mode === 'add' ? 'ring-2 ring-blue-500' : ''}`}
        onClick={onAddWaypoint}
        title="Add waypoint"
      >
        <Icon.MapPin />
      </button>

      <button className={btn} onClick={onUpload} title="Upload">
        <Icon.Upload />
      </button>

      <button className={btn} onClick={onLayerToggle} title="Layers">
        <Icon.Layers3 />
      </button>

      <button
        className={`${btn} ${mode === 'delete' ? 'ring-2 ring-red-500' : ''}`}
        onClick={onToggleDeleteMode}
        title="Delete mode"
      >
        <span className="text-red-600"><Icon.Trash2 /></span>
      </button>
    </div>
  );
}
