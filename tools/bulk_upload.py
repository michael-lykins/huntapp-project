#!/usr/bin/env python3
# tools/bulk_upload.py
from __future__ import annotations

import requests
import argparse
import concurrent.futures as cf
import itertools
import os
from pathlib import Path
from typing import Iterable, List, Tuple, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def iter_files(
    folder: Path,
    recursive: bool,
    include_exts: Iterable[str],
    globs: Iterable[str] | None = None,
) -> List[Path]:
    """Find files to upload."""
    include_exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in include_exts}
    globs = list(globs or [])
    paths: List[Path] = []

    if globs:
        for pattern in globs:
            if recursive:
                paths.extend(folder.rglob(pattern))
            else:
                paths.extend(folder.glob(pattern))
    else:
        it = folder.rglob("*") if recursive else folder.glob("*")
        for p in it:
            if p.is_file() and p.suffix.lower() in include_exts:
                paths.append(p)

    # de-dup & sort for stable progress bars
    paths = sorted(set(p.resolve() for p in paths))
    return paths


def make_session(total_retries: int = 3, backoff: float = 0.25) -> requests.Session:
    """Requests session with basic retry (idempotent enough for our uploads)."""
    s = requests.Session()
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=64, pool_maxsize=64)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def _guess_content_type(p: Path) -> str:
    ext = p.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
    }.get(ext, "application/octet-stream")


def upload_one(
    session: requests.Session,
    api_url: str,
    path: Path,
    shared_fields: Dict[str, Any],
    timeout: float,
    dry_run: bool = False,
) -> Tuple[Path, bool, Optional[str]]:
    """
    Returns (path, ok, message_or_id).
    On success, message_or_id is the indexed ID (if present).
    """
    if dry_run:
        return (path, True, "DRY-RUN")

    files = {
        "file": (path.name, path.open("rb"), _guess_content_type(path)),
    }
    data = {k: v for k, v in shared_fields.items() if v is not None}

    try:
        resp = session.post(api_url, files=files, data=data, timeout=timeout)
    except Exception as e:
        return (path, False, f"request failed: {e!r}")

    if resp.status_code >= 400:
        # surface API error body if available
        try:
            return (path, False, resp.json())
        except Exception:
            return (path, False, f"{resp.status_code} {resp.text[:200]}")

    try:
        js = resp.json()
    except Exception:
        return (path, False, f"non-JSON response: {resp.status_code}")

    # Your single-file endpoint returns {"indexed_id": "...", "ok": true, ...}
    idx = js.get("indexed_id") or js.get("id")
    return (path, True, str(idx) if idx else "OK")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bulk-upload images to Ridgeline API (/api/images)."
    )
    ap.add_argument("folder", type=str, help="Folder containing images")
    ap.add_argument(
        "--api",
        default=os.getenv("RIDGELINE_API", "http://localhost:8000/api/images"),
        help="Upload endpoint (default: %(default)s or $HUNTAPP_API)",
    )
    ap.add_argument(
        "--type",
        dest="image_type",
        default="trailcam",
        choices=["trailcam", "cellphone", "digital"],
        help="image_type value to send with each file",
    )
    ap.add_argument("--make", dest="trailcam_camera_make", default=None,
                    help="trailcam camera make (if image_type=trailcam)")
    ap.add_argument("--model", dest="trailcam_camera_model", default=None,
                    help="trailcam camera model (if image_type=trailcam)")
    ap.add_argument("--ts", dest="captured_at", default=None,
                    help="ISO8601 capture timestamp (optional; EXIF can override server-side)")
    ap.add_argument("--lat", type=float, default=None, help="Latitude override")
    ap.add_argument("--lon", type=float, default=None, help="Longitude override")

    ap.add_argument("-r", "--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument(
        "--ext",
        default=",".join(sorted(IMAGE_EXTS)),
        help=f"Comma-separated extensions to include (default: {','.join(sorted(IMAGE_EXTS))})",
    )
    ap.add_argument(
        "--glob",
        action="append",
        help="Optional glob pattern(s). Can be provided multiple times. Overrides --ext filtering if present.",
    )
    ap.add_argument("-j", "--concurrency", type=int, default=4, help="Parallel uploads (default: 4)")
    ap.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout seconds")
    ap.add_argument("--retries", type=int, default=3, help="HTTP retry attempts (default: 3)")
    ap.add_argument("--dry-run", action="store_true", help="List files and exit successfully")
    ap.add_argument("--fail-fast", action="store_true", help="Stop on first error")

    args = ap.parse_args()
    folder = Path(args.folder).expanduser().resolve()

    if not folder.exists() or not folder.is_dir():
        print(f"ERR: folder not found or not a directory: {folder}")
        return 2

    files = iter_files(
        folder=folder,
        recursive=bool(args.recursive),
        include_exts=[e.strip() for e in args.ext.split(",") if e.strip()],
        globs=args.glob,
    )
    if not files:
        print("No files matched.")
        return 0

    shared_fields: Dict[str, Any] = {
        "image_type": args.image_type,
        "captured_at": args.captured_at,
        "lat": args.lat,
        "lon": args.lon,
        "trailcam_camera_make": args.trailcam_camera_make,
        "trailcam_camera_model": args.trailcam_camera_model,
    }

    if args.dry_run:
        for p in files:
            print(p)
        print(f"DRY-RUN: {len(files)} file(s) would be uploaded to {args.api}")
        return 0

    session = make_session(total_retries=max(0, args.retries))

    ok_count = 0
    fail_count = 0
    first_error: Optional[str] = None

    with tqdm(total=len(files), unit="img", desc="Uploading") as bar:
        with cf.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futs = [
                ex.submit(
                    upload_one,
                    session,
                    args.api,
                    p,
                    shared_fields,
                    args.timeout,
                    False,
                )
                for p in files
            ]
            for fut in cf.as_completed(futs):
                path, ok, msg = fut.result()
                if ok:
                    ok_count += 1
                    bar.set_postfix_str(f"ok={ok_count} fail={fail_count} last={msg}")
                else:
                    fail_count += 1
                    bar.set_postfix_str(f"ok={ok_count} fail={fail_count} last_err")
                    if first_error is None:
                        first_error = f"{path.name}: {msg}"
                    if args.fail_fast:
                        # Cancel remaining
                        for f2 in futs:
                            f2.cancel()
                        break
                bar.update(1)

    print(f"\nDone. uploaded={ok_count} failed={fail_count} -> {args.api}")
    if first_error:
        print(f"First error: {first_error}")
    return 1 if fail_count and args.fail_fast else 0


if __name__ == "__main__":
    raise SystemExit(main())
