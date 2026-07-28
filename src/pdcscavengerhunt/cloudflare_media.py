from __future__ import annotations

import asyncio
import hmac
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from .settings import Settings


class MediaProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    size_bytes: int
    content_type: str
    prefix: bytes


@dataclass(frozen=True)
class StreamVideo:
    size_bytes: int
    status: str
    ready: bool


class CloudflareMediaProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._s3 = None

    def _require_configuration(self) -> None:
        required = (
            self.settings.cloudflare_account_id,
            self.settings.cloudflare_api_token,
            self.settings.cloudflare_r2_access_key_id,
            self.settings.cloudflare_r2_secret_access_key,
            self.settings.cloudflare_r2_bucket,
            self.settings.cloudflare_stream_customer_subdomain,
        )
        if not all(required):
            raise MediaProviderError("Cloudflare media storage is not configured")

    @property
    def s3(self):
        self._require_configuration()
        if self._s3 is None:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=(
                    f"https://{self.settings.cloudflare_account_id}"
                    ".r2.cloudflarestorage.com"
                ),
                aws_access_key_id=self.settings.cloudflare_r2_access_key_id,
                aws_secret_access_key=self.settings.cloudflare_r2_secret_access_key,
                region_name="auto",
            )
        return self._s3

    def create_photo_upload_url(self, key: str, content_type: str) -> str:
        return self.s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.cloudflare_r2_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=self.settings.media_upload_url_ttl_seconds,
        )

    def create_photo_read_url(self, key: str) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.settings.cloudflare_r2_bucket,
                "Key": key,
            },
            ExpiresIn=self.settings.media_read_url_ttl_seconds,
        )

    async def inspect_photo(self, key: str) -> StoredObject:
        def inspect() -> StoredObject:
            try:
                head = self.s3.head_object(
                    Bucket=self.settings.cloudflare_r2_bucket,
                    Key=key,
                )
                response = self.s3.get_object(
                    Bucket=self.settings.cloudflare_r2_bucket,
                    Key=key,
                    Range="bytes=0-31",
                )
                prefix = response["Body"].read(32)
                response["Body"].close()
                return StoredObject(
                    size_bytes=int(head["ContentLength"]),
                    content_type=str(head.get("ContentType", "")).lower(),
                    prefix=prefix,
                )
            except (BotoCoreError, ClientError, KeyError, TypeError, ValueError) as error:
                raise MediaProviderError("Unable to verify the R2 photo") from error

        return await asyncio.to_thread(inspect)

    async def promote_photo(self, pending_key: str, final_key: str) -> None:
        def promote() -> None:
            try:
                self.s3.copy_object(
                    Bucket=self.settings.cloudflare_r2_bucket,
                    CopySource={
                        "Bucket": self.settings.cloudflare_r2_bucket,
                        "Key": pending_key,
                    },
                    Key=final_key,
                    MetadataDirective="COPY",
                )
                self.s3.delete_object(
                    Bucket=self.settings.cloudflare_r2_bucket,
                    Key=pending_key,
                )
            except (BotoCoreError, ClientError) as error:
                raise MediaProviderError("Unable to finalize the R2 photo") from error

        await asyncio.to_thread(promote)

    async def delete_photo(self, key: str) -> None:
        def delete() -> None:
            try:
                self.s3.delete_object(
                    Bucket=self.settings.cloudflare_r2_bucket,
                    Key=key,
                )
            except (BotoCoreError, ClientError) as error:
                raise MediaProviderError("Unable to delete the R2 photo") from error

        await asyncio.to_thread(delete)

    @property
    def stream_api_base(self) -> str:
        self._require_configuration()
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.cloudflare_account_id}/stream"
        )

    @property
    def stream_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.cloudflare_api_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _result(payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("success") or not isinstance(payload.get("result"), dict):
            errors = payload.get("errors") or []
            message = errors[0].get("message") if errors else "Cloudflare request failed"
            raise MediaProviderError(str(message))
        return payload["result"]

    async def create_video_upload(
        self,
        *,
        clue_id: str,
        original_filename: str,
    ) -> tuple[str, str]:
        payload = {
            "maxDurationSeconds": self.settings.video_max_duration_seconds,
            "requireSignedURLs": True,
            "scheduledDeletion": (
                datetime.now(UTC) + timedelta(days=31)
            ).isoformat().replace("+00:00", "Z"),
            "meta": {
                "clue_id": clue_id,
                "original_filename": original_filename,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.stream_api_base}/direct_upload",
                    headers=self.stream_headers,
                    json=payload,
                )
                response.raise_for_status()
            result = self._result(response.json())
            return str(result["uid"]), str(result["uploadURL"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise MediaProviderError("Unable to create the Stream upload") from error

    async def video_details(self, uid: str) -> StreamVideo:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.stream_api_base}/{uid}",
                    headers=self.stream_headers,
                )
                response.raise_for_status()
            result = self._result(response.json())
            provider_status = str((result.get("status") or {}).get("state", "processing"))
            ready = bool(result.get("readyToStream"))
            status = (
                "ready"
                if ready
                else "error"
                if provider_status == "error"
                else "processing"
            )
            return StreamVideo(
                size_bytes=int(result.get("size") or 0),
                status=status,
                ready=ready,
            )
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise MediaProviderError("Unable to check the Stream video") from error

    async def secure_video(self, uid: str) -> None:
        payload = {
            "uid": uid,
            "requireSignedURLs": True,
            "allowedOrigins": [self.settings.public_hostname],
            "scheduledDeletion": None,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.stream_api_base}/{uid}",
                    headers=self.stream_headers,
                    json=payload,
                )
                response.raise_for_status()
                self._result(response.json())
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise MediaProviderError("Unable to secure the Stream video") from error

    async def create_video_player_url(self, uid: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.stream_api_base}/{uid}/token",
                    headers=self.stream_headers,
                )
                response.raise_for_status()
            token = str(self._result(response.json())["token"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise MediaProviderError("Unable to authorize Stream playback") from error
        return (
            f"https://{self.settings.cloudflare_stream_customer_subdomain}/"
            f"{token}/iframe"
        )

    async def delete_video(self, uid: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{self.stream_api_base}/{uid}",
                    headers=self.stream_headers,
                )
                if response.status_code != 404:
                    response.raise_for_status()
        except httpx.HTTPError as error:
            raise MediaProviderError("Unable to delete the Stream video") from error

    def verify_stream_webhook(self, body: bytes, signature: str) -> bool:
        if not self.settings.cloudflare_stream_webhook_secret:
            return False
        try:
            values = dict(part.split("=", 1) for part in signature.split(","))
            timestamp = int(values["time"])
            supplied = values["sig1"]
        except (KeyError, TypeError, ValueError):
            return False
        if abs(int(time.time()) - timestamp) > 300:
            return False
        source = str(timestamp).encode() + b"." + body
        expected = hmac.new(
            self.settings.cloudflare_stream_webhook_secret.encode(),
            source,
            sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, supplied)

    @staticmethod
    def parse_webhook(body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
            return payload["result"] if isinstance(payload.get("result"), dict) else payload
        except (json.JSONDecodeError, TypeError, KeyError) as error:
            raise MediaProviderError("Invalid Stream webhook payload") from error
