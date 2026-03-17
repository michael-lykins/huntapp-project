# lib/images/exif.py
from __future__ import annotations
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ExifTags
import piexif
import io, datetime as dt

def _get_exif_dict(image_bytes: bytes) -> Dict[str, Any]:
    try:
        return piexif.load(image_bytes)
    except Exception:
        return {}

def _gps_to_deg(gps_ifd) -> Optional[Tuple[float,float]]:
    try:
        lat_ref = gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b'N').decode()
        lon_ref = gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef, b'E').decode()
        lat = gps_ifd[piexif.GPSIFD.GPSLatitude]
        lon = gps_ifd[piexif.GPSIFD.GPSLongitude]
        def to_deg(x): return float(x[0][0])/float(x[0][1]) + (float(x[1][0])/float(x[1][1]))/60 + (float(x[2][0])/float(x[2][1]))/3600
        latd, lond = to_deg(lat), to_deg(lon)
        if lat_ref == 'S': latd = -latd
        if lon_ref == 'W': lond = -lond
        return (latd, lond)
    except Exception:
        return None

def _dt_from_exif(ifd) -> Optional[str]:
    # returns ISO8601 if available
    for tag in (piexif.ExifIFD.DateTimeOriginal, piexif.ImageIFD.DateTime):
        v = ifd.get(tag)
        if v:
            s = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
            try:
                return dt.datetime.strptime(s, "%Y:%m:%d %H:%M:%S").isoformat() + "Z"
            except Exception:
                pass
    return None

def extract(image_bytes: bytes) -> Dict[str, Any]:
    exif = _get_exif_dict(image_bytes)
    gps = exif.get("GPS", {}) or {}
    exif_ifd = exif.get("Exif", {}) or {}
    latlon = _gps_to_deg(gps)
    ts = _dt_from_exif(exif_ifd)
    out: Dict[str, Any] = {}
    if latlon:
        out["geo"] = {"lat": latlon[0], "lon": latlon[1]}
    if ts:
        out["captured_at"] = ts
    # Basic size
    try:
        im = Image.open(io.BytesIO(image_bytes))
        out["width"], out["height"] = im.size
        out["mode"] = im.mode
        out["format"] = im.format
    except Exception:
        pass
    return out
