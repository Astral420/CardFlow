"""Thin wrapper around Cloudflare R2 (S3-compatible) for object storage.

Storage layout (see spec Section 9):
    raw/{batch_id}/{scan_id}-{front|back}.jpg
    cropped/{batch_id}/{crop_id}-{front|back}.jpg
"""

from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config as BotoConfig

from app.config import settings


@lru_cache
def _client() -> Any:
    endpoint_url = (
        settings.r2_endpoint_url
        or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> None:
    _client().put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    response = _client().get_object(Bucket=settings.r2_bucket_name, Key=key)
    return response["Body"].read()


def delete_object(key: str) -> None:
    _client().delete_object(Bucket=settings.r2_bucket_name, Key=key)


def presigned_url(key: str, expires_in: int = 3600) -> str:
    if settings.r2_public_base_url:
        return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )


def raw_key(batch_id: int, scan_id: int, side: str, ext: str = "jpg") -> str:
    return f"raw/{batch_id}/{scan_id}-{side}.{ext}"


def cropped_key(batch_id: int, crop_id: int, side: str, ext: str = "jpg") -> str:
    return f"cropped/{batch_id}/{crop_id}-{side}.{ext}"


def temp_upload_key(batch_id: int) -> str:
    return f"tmp/uploads/{batch_id}.zip"
