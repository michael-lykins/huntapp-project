from typing import Optional, Tuple
from PIL import Image, ExifTags
import exifread
import io

def _to_deg(value):
    # Convert EXIF rational tuples to float degrees
    d = float(value[0].num) / float(value[0].den)
    m = float(value[1].num) / float(value[1].den)
    s = float(value[2].num) / float(value[2].den)
    return d + (m / 60.0) + (s / 3600.0)

def _apply_ref(deg: float, ref: str) -> float:
    if ref in ["S", "W"]:
        return -deg
    return deg

def read_exif_gps(file_bytes: bytes) -> Tuple[Optional[float], Optional[float]]:
    """
    Try Pillow first; if it fails or lacks GPS, try exifread.
    Returns (lat, lon) or (None, None).
    """
    # Attempt Pillow
    try:
        im = Image.open(io.BytesIO(file_bytes))
        exif = im.getexif()
        if exif:
            exif_dict = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            gps = exif_dict.get("GPSInfo")
            if gps:
                gps_tags = {}
                for tkey in gps.keys():
                    tag_name = ExifTags.GPSTAGS.get(tkey, tkey)
                    gps_tags[tag_name] = gps[tkey]

                lat = _to_deg(gps_tags["GPSLatitude"]) if "GPSLatitude" in gps_tags else None
                lon = _to_deg(gps_tags["GPSLongitude"]) if "GPSLongitude" in gps_tags else None
                if lat is not None and lon is not None:
                    lat = _apply_ref(lat, gps_tags.get("GPSLatitudeRef", "N"))
                    lon = _apply_ref(lon, gps_tags.get("GPSLongitudeRef", "E"))
                    return lat, lon
    except Exception:
        pass

    # Fallback: exifread (handles some JPEG/HEIC better)
    try:
        tags = exifread.process_file(io.BytesIO(file_bytes), details=False)
        lat_vals = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_vals = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        def _vals_to_deg(vals):
            # exifread gives e.g. [35, 12, 25.12]
            d, m, s = [float(x.num) / float(x.den) if hasattr(x, 'num') else float(x) for x in vals.values]
            return d + (m / 60.0) + (s / 3600.0)

        if lat_vals and lon_vals:
            lat = _vals_to_deg(lat_vals)
            lon = _vals_to_deg(lon_vals)
            if lat_ref: lat = _apply_ref(lat, str(lat_ref))
            if lon_ref: lon = _apply_ref(lon, str(lon_ref))
            return lat, lon
    except Exception:
        pass

    return None, None
