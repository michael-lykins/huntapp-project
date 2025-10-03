from dataclasses import dataclass
import os

@dataclass(frozen=True)
class SearchConfig:
    # Provider switch
    provider: str = os.getenv("SEARCH_PROVIDER", "elastic")
    # Elastic credentials (only used when provider == "elastic")
    host: str = os.getenv("ELASTIC_SEARCH_HOST", "http://localhost:9200")
    api_key: str = os.getenv("ELASTIC_SEARCH_API_KEY", "")

    # Logical destinations (data stream or index names)
    images_index: str = os.getenv("IMAGES_DATA_STREAM", "hunt-trailcam")
    events_index: str = os.getenv("EVENTS_DATA_STREAM", "hunt-events")
    tracks_index: str = os.getenv("TRACKS_DATA_STREAM", "hunt-geo-tracks")

@dataclass(frozen=True)
class BlobConfig:
    provider: str = os.getenv("BLOB_PROVIDER", "s3")
    endpoint: str = os.getenv("S3_ENDPOINT", "http://minio:9000")
    bucket: str = os.getenv("S3_BUCKET", "trailcam-images")
    public_base: str = os.getenv("S3_PUBLIC_URL", os.getenv("S3_ENDPOINT", "http://localhost:9000"))
    region: str = os.getenv("S3_REGION", "us-east-1")
    access_key: str = os.getenv("S3_ACCESS_KEY", "")
    secret_key: str = os.getenv("S3_SECRET_KEY", "")
