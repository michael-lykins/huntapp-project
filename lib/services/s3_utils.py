import boto3
import os
from botocore.client import Config


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION"),
        config=Config(signature_version="s3v4")
    )


def upload_file(bucket, key, file_path):
    s3 = get_s3_client()
    s3.upload_file(file_path, bucket, key)


def download_file(bucket, key, local_path):
    s3 = get_s3_client()
    s3.download_file(bucket, key, local_path)
