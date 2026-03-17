// web/app/upload/image/page.tsx
"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type UploadResp =
  | { ok: true; indexed_id: string; bucket: string; key: string; url: string | null }
  | { ok: true; count: number; items: Array<{ id?: string; bucket?: string; key?: string; url?: string | null; error?: string; filename?: string }> }
  | { ok: false; error: string };

export default function UploadImagePage() {
  const [imageType, setImageType] = useState<"trailcam" | "cellphone" | "digital">("trailcam");
  const [capturedAt, setCapturedAt] = useState<string>("");
  const [lat, setLat] = useState<string>("");
  const [lon, setLon] = useState<string>("");
  const [trailMake, setTrailMake] = useState<string>("");
  const [trailModel, setTrailModel] = useState<string>("");

  const [useBatch, setUseBatch] = useState<boolean>(false);
  const [resp, setResp] = useState<UploadResp | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [pickedFrom, setPickedFrom] = useState<"files" | "folder" | null>(null); // purely UX

  const filesRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  // enable directory chooser on supporting browsers
  useEffect(() => {
    if (folderRef.current) {
      folderRef.current.setAttribute("webkitdirectory", "true");
      // @ts-ignore - not in TS DOM typings
      folderRef.current.directory = true;
      folderRef.current.multiple = true;
    }
  }, []);

  // ---- FIX: choose the non-empty FileList, preferring "files" over "folder" ----
  const getSelectedFiles = useCallback((): FileList | null => {
    const files = filesRef.current?.files;
    const folder = folderRef.current?.files;
    if (files && files.length > 0) {
      setPickedFrom("files");
      return files;
    }
    if (folder && folder.length > 0) {
      setPickedFrom("folder");
      return folder;
    }
    setPickedFrom(null);
    return null;
  }, []);
  // ---------------------------------------------------------------------------

  const uploadSingle = useCallback(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("image_type", imageType);
    if (capturedAt) form.append("captured_at", new Date(capturedAt).toISOString());
    if (lat) form.append("lat", lat);
    if (lon) form.append("lon", lon);
    if (imageType === "trailcam") {
      if (trailMake) form.append("trailcam_camera_make", trailMake);
      if (trailModel) form.append("trailcam_camera_model", trailModel);
    }

    const r = await fetch(`${API_BASE}/api/images`, { method: "POST", body: form });
    if (!r.ok) throw new Error(`upload failed: ${r.status} ${await r.text()}`);
    return (await r.json()) as UploadResp;
  }, [imageType, capturedAt, lat, lon, trailMake, trailModel]);

  const uploadBatch = useCallback(async (files: FileList) => {
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    form.append("image_type", imageType);
    if (capturedAt) form.append("captured_at", new Date(capturedAt).toISOString());
    if (lat) form.append("lat", lat);
    if (lon) form.append("lon", lon);
    if (imageType === "trailcam") {
      if (trailMake) form.append("trailcam_camera_make", trailMake);
      if (trailModel) form.append("trailcam_camera_model", trailModel);
    }
    form.append("continue_on_error", "true");

    const r = await fetch(`${API_BASE}/api/images:batch`, { method: "POST", body: form });
    if (!r.ok) throw new Error(`batch failed: ${r.status} ${await r.text()}`);
    return (await r.json()) as UploadResp;
  }, [imageType, capturedAt, lat, lon, trailMake, trailModel]);

  const onSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setResp(null);
    setLoading(true);
    try {
      if (useBatch) {
        const selected = getSelectedFiles(); // <-- FIX used here
        if (!selected || selected.length === 0) throw new Error("No files selected");
        const out = await uploadBatch(selected);
        setResp(out);
      } else {
        const files = filesRef.current?.files;
        if (!files || files.length === 0) throw new Error("No file selected");
        const out = await uploadSingle(files[0]);
        setResp(out);
      }
    } catch (err: any) {
      setResp({ ok: false, error: String(err?.message || err) });
    } finally {
      setLoading(false);
    }
  }, [useBatch, uploadSingle, uploadBatch, getSelectedFiles]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-4">Upload Trail Camera Images</h1>

      <form onSubmit={onSubmit} className="space-y-6">
        {/* Controls */}
        <section className="grid md:grid-cols-2 gap-6 p-4 rounded-2xl shadow border">
          <div className="space-y-3">
            <label className="text-sm font-medium">Image type</label>
            <select
              className="border rounded px-2 py-1"
              value={imageType}
              onChange={(e) => setImageType(e.target.value as any)}
            >
              <option value="trailcam">Trail camera</option>
              <option value="cellphone">Cell phone</option>
              <option value="digital">Digital camera</option>
            </select>

            <label className="text-sm font-medium">Captured at (ISO)</label>
            <input
              className="border rounded px-2 py-1"
              type="datetime-local"
              value={capturedAt}
              onChange={(e) => setCapturedAt(e.target.value)}
            />

            <label className="text-sm font-medium">Latitude</label>
            <input
              className="border rounded px-2 py-1"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />

            <label className="text-sm font-medium">Longitude</label>
            <input
              className="border rounded px-2 py-1"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
            />

            {imageType === "trailcam" && (
              <>
                <label className="text-sm font-medium">Trailcam make</label>
                <input
                  className="border rounded px-2 py-1"
                  value={trailMake}
                  onChange={(e) => setTrailMake(e.target.value)}
                />

                <label className="text-sm font-medium">Trailcam model</label>
                <input
                  className="border rounded px-2 py-1"
                  value={trailModel}
                  onChange={(e) => setTrailModel(e.target.value)}
                />
              </>
            )}
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium">Mode</label>
            <div className="flex items-center gap-3">
              <label className="inline-flex items-center gap-2">
                <input
                  type="radio"
                  name="mode"
                  checked={!useBatch}
                  onChange={() => setUseBatch(false)}
                />
                <span>Single file</span>
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="radio"
                  name="mode"
                  checked={useBatch}
                  onChange={() => setUseBatch(true)}
                />
                <span>Batch / folder</span>
              </label>
            </div>

            {!useBatch && (
              <>
                <label className="text-sm font-medium">Choose file</label>
                <input ref={filesRef} type="file" accept="image/*" />
              </>
            )}

            {useBatch && (
              <>
                <label className="text-sm font-medium">Choose files</label>
                <input ref={filesRef} type="file" multiple accept="image/*" />
                <div className="text-xs text-gray-500">or select a folder:</div>
                <input ref={folderRef} type="file" />
                {pickedFrom && (
                  <div className="text-xs text-gray-500">
                    Using files from: <span className="font-medium">{pickedFrom}</span>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 rounded-2xl bg-blue-600 text-white disabled:opacity-50"
        >
          {loading ? "Uploading..." : "Upload"}
        </button>
      </form>

      {resp && (
        <pre className="mt-6 text-xs p-3 rounded bg-gray-900 text-green-300 overflow-auto">
          {JSON.stringify(resp, null, 2)}
        </pre>
      )}
    </div>
  );
}
