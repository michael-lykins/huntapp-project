import boto3
from .config import BlobConfig

class S3Blob:
    def __init__(self, cfg: BlobConfig):
        self.cfg = cfg
        self.s3 = boto3.client(
            "s3",
            endpoint_url=cfg.endpoint,
            region_name=cfg.region,
            aws_access_key_id=cfg.access_key or None,
            aws_secret_access_key=cfg.secret_key or None,
        )

    def put(self, key: str, data: bytes, content_type: str):
        self.s3.put_object(
            Bucket=self.cfg.bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return {"bucket": self.cfg.bucket, "key": key}

    def public_url(self, key: str) -> str:
        base = self.cfg.public_base.rstrip("/")
        return f"{base}/{self.cfg.bucket}/{key}"
