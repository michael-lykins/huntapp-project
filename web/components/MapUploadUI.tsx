// File: web/components/MapUploadUI.tsx
// Drop‑in overlay toolbar + flyout (sheet) for the Maps page
// v2: Adds auto‑attach to nearest waypoint on backend, and optional waypoint override in UI.
// - Floating "tool bar" on the map with an Upload tile
// - Flyout shows Saved Trail Cameras (inherits Make/Model/Name/Lat/Lon)
// - Optional Waypoint override (if set, backend uses it instead of nearest)
// - Optional threshold (meters) and toggle for auto‑attach
// - POST FormData to backend /api/images or /api/images:batch
// - GET cameras from backend /api/trailcams, waypoints from /api/waypoints

'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Upload, Camera, MapPin, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger } from '@/components/ui/sheet'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

// ---- Types ----
export type TrailCam = {
  id: string
  name: string
  make?: string | null
  model?: string | null
  lat: number
  lon: number
}

export type Waypoint = {
  id: string
  name: string
  lat: number
  lon: number
}

// ---- Helpers ----
const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, '') || 'http://localhost:8000'

async function fetchTrailCams(): Promise<TrailCam[]> {
  const res = await fetch(`${API_BASE}/api/trailcams`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to load trail cameras')
  return res.json()
}

async function fetchWaypoints(): Promise<Waypoint[]> {
  const res = await fetch(`${API_BASE}/api/waypoints`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Failed to load waypoints')
  return res.json()
}

async function uploadImages(payload: {
  files: File[]
  camera?: TrailCam | null
  waypointOverrideId?: string | null
  autoAttach?: boolean
  thresholdM?: number
  notes?: string
}): Promise<{ ok: boolean; count?: number; error?: string; attached?: Array<{ waypoint?: Waypoint | null; distance_m?: number | null; exif?: { lat?: number; lon?: number } | null }> }> {
  const fd = new FormData()
  payload.files.forEach((f) => fd.append('files', f))
  if (payload.camera) {
    fd.append('camera_id', payload.camera.id)
    fd.append('camera_name', payload.camera.name)
    if (payload.camera.make) fd.append('camera_make', payload.camera.make)
    if (payload.camera.model) fd.append('camera_model', payload.camera.model)
    fd.append('lat', String(payload.camera.lat))
    fd.append('lon', String(payload.camera.lon))
  }
  if (payload.waypointOverrideId) fd.append('override_waypoint_id', payload.waypointOverrideId)
  if (payload.autoAttach != null) fd.append('auto_attach', String(payload.autoAttach))
  if (payload.thresholdM != null) fd.append('attach_threshold_meters', String(payload.thresholdM))
  if (payload.notes) fd.append('notes', payload.notes)
  fd.append('image_type', payload.camera ? 'trailcam' : 'cellphone')

  const res = await fetch(`${API_BASE}/api/images:batch`, { method: 'POST', body: fd })
  if (!res.ok) {
    const txt = await res.text()
    return { ok: false, error: txt || 'Upload failed' }
  }
  const data = await res.json().catch(() => ({}))
  return { ok: true, count: data?.count, attached: data?.attached }
}

// ---- Drag & Drop zone ----
function DropZone({ files, setFiles }: { files: File[]; setFiles: (f: File[]) => void }) {
  const [active, setActive] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const onFiles = (list: FileList | null) => {
    if (!list) return
    const arr = Array.from(list).filter((f) => f.type.startsWith('image/'))
    setFiles([...files, ...arr])
  }

  return (
    <div
      onDrop={(e) => { e.preventDefault(); setActive(false); onFiles(e.dataTransfer?.files ?? null) }}
      onDragOver={(e) => { e.preventDefault(); setActive(true) }}
      onDragLeave={() => setActive(false)}
      className={cn('rounded-2xl border border-dashed p-6 transition-shadow text-center cursor-pointer', active ? 'shadow-lg' : 'shadow-sm')}
      onClick={() => inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => onFiles(e.target.files)} />
      <div className="flex flex-col items-center gap-2">
        <Upload className="h-8 w-8" />
        <div className="font-medium">Drag & drop images here</div>
        <div className="text-sm text-muted-foreground">or click to browse</div>
      </div>
      {files.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2 max-h-44 overflow-auto">
          {files.map((f, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border p-2 text-sm">
              <span className="truncate" title={f.name}>{f.name}</span>
              <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); setFiles(files.filter((_, ix) => ix !== i)) }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---- The Flyout content ----
function UploadFlyoutContent({ onDone }: { onDone?: () => void }) {
  const [cams, setCams] = useState<TrailCam[]>([])
  const [wps, setWps] = useState<Waypoint[]>([])

  const [selectedCamId, setSelectedCamId] = useState<string | undefined>(undefined)
  const [waypointOverrideId, setWaypointOverrideId] = useState<string | undefined>(undefined)

  const [autoAttach, setAutoAttach] = useState(true)
  const [thresholdM, setThresholdM] = useState<number>(150)

  const [files, setFiles] = useState<File[]>([])
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ type: 'ok' | 'err'; msg: string; detail?: any } | null>(null)

  useEffect(() => {
    fetchTrailCams().then(setCams).catch((e) => { console.error(e); setResult({ type: 'err', msg: 'Could not load saved trail cameras.' }) })
    fetchWaypoints().then(setWps).catch((e) => { console.error(e); setResult({ type: 'err', msg: 'Could not load waypoints.' }) })
  }, [])

  const selectedCam = useMemo(() => cams.find((c) => c.id === selectedCamId) ?? null, [cams, selectedCamId])

  const handleSubmit = async () => {
    if (files.length === 0) return setResult({ type: 'err', msg: 'Please add at least one image.' })
    setBusy(true)
    setResult(null)
    const out = await uploadImages({ files, camera: selectedCam ?? undefined, waypointOverrideId, autoAttach, thresholdM, notes })
    setBusy(false)
    if (out.ok) {
      setResult({ type: 'ok', msg: `Uploaded ${out.count ?? files.length} image(s).`, detail: out.attached })
      setFiles([]); setNotes(''); setSelectedCamId(undefined); setWaypointOverrideId(undefined)
      onDone?.()
    } else setResult({ type: 'err', msg: out.error || 'Upload failed' })
  }

  return (
    <div className="space-y-6">
      {/* Camera picker */}
      <Card className="shadow-none border-0">
        <CardHeader className="p-0">
          <CardTitle className="text-base">Select Trail Camera</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-3">
          <div className="grid gap-3">
            <Label htmlFor="camera">Saved Cameras</Label>
            <Select value={selectedCamId} onValueChange={setSelectedCamId}>
              <SelectTrigger id="camera"><SelectValue placeholder="Choose a camera (optional)" /></SelectTrigger>
              <SelectContent className="max-h-64">
                {cams.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    <div className="flex items-center gap-2">
                      <Camera className="h-4 w-4" />
                      <span className="font-medium">{c.name}</span>
                      <span className="text-xs text-muted-foreground">({c.make ?? '—'}/{c.model ?? '—'})</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {selectedCam && (
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div><Label>Make</Label><Input value={selectedCam.make ?? ''} readOnly /></div>
                <div><Label>Model</Label><Input value={selectedCam.model ?? ''} readOnly /></div>
                <div className="col-span-2"><Label>Name</Label><Input value={selectedCam.name} readOnly /></div>
                <div><Label>Latitude</Label><Input value={selectedCam.lat} readOnly /></div>
                <div><Label>Longitude</Label><Input value={selectedCam.lon} readOnly /></div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Waypoint override & auto-attach controls */}
      <div className="grid gap-4">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label>Auto-attach to nearest waypoint</Label>
            <div className="text-sm text-muted-foreground">If no override selected, backend finds nearest ≤ threshold.</div>
          </div>
          <Switch checked={autoAttach} onCheckedChange={setAutoAttach} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="threshold">Threshold (meters)</Label>
            <Input id="threshold" type="number" min={0} step={1} value={thresholdM} onChange={(e) => setThresholdM(Number(e.target.value))} />
          </div>
          <div>
            <Label htmlFor="wp">Waypoint override (optional)</Label>
            <Select value={waypointOverrideId} onValueChange={setWaypointOverrideId}>
              <SelectTrigger id="wp"><SelectValue placeholder="Pick a waypoint (optional)" /></SelectTrigger>
              <SelectContent className="max-h-64">
                {wps.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4" />
                      <span className="font-medium">{w.name}</span>
                      <span className="text-xs text-muted-foreground">({w.lat.toFixed(5)}, {w.lon.toFixed(5)})</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Files */}
      <div>
        <Label>Images</Label>
        <DropZone files={files} setFiles={setFiles} />
        <div className="mt-2 flex flex-wrap gap-2">
          {files.length > 0 && <Badge variant="secondary">{files.length} selected</Badge>}
        </div>
      </div>

      {/* Notes */}
      <div className="grid gap-2">
        <Label htmlFor="notes">Notes (optional)</Label>
        <Textarea id="notes" placeholder="Any notes to attach to these images…" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {/* Result */}
      {result && (
        <div className={cn('rounded-lg p-3 text-sm', result.type === 'ok' ? 'bg-emerald-50' : 'bg-rose-50')}>
          {result.type === 'ok' ? '✅ ' : '⚠️ '} {result.msg}
          {result.detail && Array.isArray(result.detail) && result.detail.length > 0 && (
            <div className="mt-2 space-y-1">
              {result.detail.map((d: any, i: number) => (
                <div key={i} className="text-xs text-muted-foreground">
                  {d?.waypoint ? (
                    <>Attached to <span className="font-medium">{d.waypoint.name}</span>{typeof d.distance_m === 'number' ? ` (${Math.round(d.distance_m)} m)` : ''}{d?.exif?.lat ? ` • EXIF: ${d.exif.lat.toFixed(5)}, ${d.exif.lon?.toFixed(5)}` : ''}</n>
                  ) : (
                    <>No waypoint attached{d?.exif?.lat ? ` • EXIF: ${d.exif.lat.toFixed(5)}, ${d.exif.lon?.toFixed(5)}` : ''}</>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={() => { setFiles([]); setNotes(''); setSelectedCamId(undefined); setWaypointOverrideId(undefined) }}>Reset</Button>
        <Button disabled={busy} onClick={handleSubmit}>{busy ? 'Uploading…' : 'Upload'}</Button>
      </div>
    </div>
  )
}

// ---- Floating toolbar + sheet ----
export default function MapUploadUI() {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[500] flex flex-col items-end gap-3">
      {/* Toolbar */}
      <div className="pointer-events-auto grid grid-cols-1 gap-3">
        <Sheet>
          <SheetTrigger asChild>
            <button className="group w-[72px] h-[72px] rounded-2xl border bg-background/80 backdrop-blur shadow-lg hover:shadow-xl transition flex flex-col items-center justify-center gap-1" aria-label="Upload trail cam images">
              <Upload className="h-6 w-6" />
              <span className="text-[11px] font-medium">Upload</span>
            </button>
          </SheetTrigger>
          <SheetContent side="right" className="w-[420px] sm:w-[460px]">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2"><Upload className="h-5 w-5" /> Upload Trail Cam Images</SheetTitle>
              <SheetDescription>Select a saved camera to inherit metadata, optionally override waypoint, then add images.</SheetDescription>
            </SheetHeader>
            <div className="mt-6">
              <UploadFlyoutContent />
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Hint chip */}
      <div className="pointer-events-auto rounded-full bg-background/80 backdrop-blur border shadow px-3 py-1 text-xs text-muted-foreground flex items-center gap-1">
        <MapPin className="h-3.5 w-3.5" /> Tools
      </div>
    </div>
  )
}

// ---- Integration notes ----
// 1) Save this file to: web/components/MapUploadUI.tsx
// 2) Render <MapUploadUI /> once on your Maps page.
// 3) Ensure API routes:
//    - GET /api/trailcams → TrailCam[]
//    - GET /api/waypoints → Waypoint[]
//    - POST /api/uploads/images → handles EXIF + nearest waypoint + override
// 4) The backend returns per-file attachment details to show in the result banner.
