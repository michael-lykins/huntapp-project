// FILE: web/components/PinFormModal.tsx
'use client';

import { useState } from 'react';

export default function PinFormModal({
  visible,
  lat,
  lon,
  onClose,
  onSave,
}: {
  visible: boolean;
  lat?: number;
  lon?: number;
  onClose: () => void;
  onSave: () => void;
}) {
  const [note, setNote] = useState('');
  const [species, setSpecies] = useState('');
  const [glyph, setGlyph] = useState('');
  const [color, setColor] = useState('#22c55e');
  const [photo, setPhoto] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!visible || lat === undefined || lon === undefined) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    const formData = new FormData();
    formData.append('lat', lat.toString());
    formData.append('lon', lon.toString());
    formData.append('note', note);
    formData.append('species', species);
    formData.append('glyph', glyph);
    formData.append('color', color);
    if (photo) formData.append('photo', photo);

    try {
      const res = await fetch('/api/pin', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Failed to save pin');
      onSave();
    } catch (err) {
      console.error(err);
      alert('Failed to save waypoint');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-lg shadow-lg p-6 w-full max-w-md space-y-4"
      >
        <h2 className="text-lg font-bold">New Waypoint</h2>
        <p className="text-sm text-gray-500">{lat.toFixed(5)}, {lon.toFixed(5)}</p>

        <div className="space-y-2">
          <input
            className="w-full border px-3 py-1 rounded"
            placeholder="Glyph (e.g. stand, cam)"
            value={glyph}
            onChange={(e) => setGlyph(e.target.value)}
          />
          <input
            className="w-full border px-3 py-1 rounded"
            placeholder="Species (optional)"
            value={species}
            onChange={(e) => setSpecies(e.target.value)}
          />
          <textarea
            className="w-full border px-3 py-1 rounded"
            placeholder="Notes"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <input
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
          />
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setPhoto(e.target.files?.[0] || null)}
          />
        </div>

        <div className="flex justify-end space-x-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="text-gray-600 hover:text-black"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="bg-green-600 text-white px-4 py-1 rounded hover:bg-green-700"
            disabled={submitting}
          >
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
}
