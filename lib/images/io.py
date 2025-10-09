import hashlib, io, time
from typing import Optional, Tuple, Dict, Any
import exifread
from PIL import Image
import boto3

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def parse_exif(raw: bytes) -> Dict[str, Any]:
    tags = exifread.process_file(io.BytesIO(raw), details=False)
    out: Dict[str, Any] = {}
    # timestamp
    dt = (tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime"))
    if dt: out["timestamp_raw"] = str(dt)
    # GPS (very basic; extend if you like)
    def ratio_to_float(r):
        return float(r.num) / float(r.den) if hasattr(r, "num") else float(r)
    lat_ref = tags.get("GPS GPSLatitudeRef")
    lat = tags.get("GPS GPSLatitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")
    lon = tags.get("GPS GPSLongitude")
    if lat and lon and lat_ref and lon_ref:
        lat_vals = [ratio_to_float(x) for x in lat.values]
        lon_vals = [ratio_to_float(x) for x in lon.values]
        lat_deg = lat_vals[0] + lat_vals[1]/60 + lat_vals[2]/3600
        lon_deg = lon_vals[0] + lon_vals[1]/60 + lon_vals[2]/3600
        if str(lat_ref).upper() == "S": lat_deg *= -1
        if str(lon_ref).upper() == "W": lon_deg *= -1
        out["gps"] = {"lat": lat_deg, "lon": lon_deg}
    # camera
    if tags.get("Image Make"):  out["camera_make"]  = str(tags["Image Make"])
    if tags.get("Image Model"): out["camera_model"] = str(tags["Image Model"])
    return out

def put_s3_bytes(*, session: boto3.session.Session, bucket: str, key: str, data: bytes, content_type: str):
    s3 = session.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

def get_boto_session(endpoint: str, region: str, access_key: str, secret_key: str):
    return boto3.session.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    ), {"endpoint_url": endpoint}
