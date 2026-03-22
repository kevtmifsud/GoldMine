"""S3 storage utility for Supabase S3-compatible storage.

Thin wrapper around boto3 that always uses the Supabase endpoint.
Every file that needs S3 imports from here — never instantiates
boto3 directly.
"""
from __future__ import annotations

import structlog

from app.config.settings import settings

logger = structlog.get_logger(__name__)


def get_s3_client():
    """Create a boto3 S3 client configured for Supabase storage.

    Always uses endpoint_url pointing to the Supabase S3-compatible API.
    Never use boto3.client('s3') without endpoint_url elsewhere in the codebase.
    """
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.SUPABASE_STORAGE_URL,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.AWS_REGION,
    )


def upload_model(
    ticker: str,
    version: str,
    date_str: str,
    file_bytes: bytes,
) -> str:
    """Upload Excel model to Supabase storage.

    Returns the S3 path (key) on success.
    Raises on failure — never silently swallows errors.
    """
    key = (
        f"{settings.S3_MODELS_PREFIX}/{ticker}/"
        f"{ticker}_model_v{version}_{date_str}.xlsx"
    )
    client = get_s3_client()
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )
    logger.info("model_uploaded", ticker=ticker, version=version, key=key)
    return key


def get_presigned_download_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned download URL.

    Valid for expires_in seconds (default 1 hour).
    URL points to the Supabase S3-compatible endpoint.
    """
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
        },
        ExpiresIn=expires_in,
    )


def download_model(key: str) -> bytes:
    """Download a model file from Supabase storage.

    Used by model_processing_job when reading from S3.
    """
    client = get_s3_client()
    response = client.get_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
    )
    return response["Body"].read()


def list_model_versions(ticker: str) -> list[str]:
    """List all model versions for a ticker in S3.

    Returns list of keys sorted by version descending.
    """
    client = get_s3_client()
    prefix = f"{settings.S3_MODELS_PREFIX}/{ticker}/"
    response = client.list_objects_v2(
        Bucket=settings.S3_BUCKET,
        Prefix=prefix,
    )
    keys = [
        obj["Key"]
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".xlsx")
    ]
    return sorted(keys, reverse=True)
