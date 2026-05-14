"""Async media pipeline.

Flow:
  upload endpoint → publish `media.uploaded` → this worker:
    1. pulls the original from MinIO
    2. produces a thumbnail (images) or a 720p H.264 variant (videos)
    3. uploads the variants back to MinIO under a sibling key
    4. publishes `media.transcoded` so other systems can react

ffmpeg must be on the container PATH. The Dockerfile installs it.
The original object is never overwritten so failures are recoverable.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.kafka_client import consume_with_dlq, publish
from app.core.minio_client import get_minio, put_object

log = logging.getLogger(__name__)
TOPIC = "media.uploaded"
DLQ_TOPIC = "media.uploaded.dlq"
OUT_TOPIC = "media.transcoded"


async def _handle(msg: dict) -> None:
    object_name: str = msg["object_name"]
    media_type: str = msg["media_type"]

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / Path(object_name).name
        get_minio().fget_object(settings.minio_bucket, object_name, str(src))

        outputs: list[dict] = []
        if media_type == "image":
            thumb = src.with_name("thumb_" + src.name)
            _run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=640:-1", str(thumb)])
            outputs.append(
                _upload(
                    thumb,
                    _sibling_key(object_name, "thumb_"),
                    "image/jpeg",
                    "thumbnail",
                )
            )
        elif media_type == "video":
            poster = src.with_suffix(".jpg")
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-ss",
                    "00:00:01",
                    "-vframes",
                    "1",
                    str(poster),
                ]
            )
            outputs.append(
                _upload(
                    poster,
                    _sibling_key(object_name, "poster_") + ".jpg",
                    "image/jpeg",
                    "poster",
                )
            )

            transcoded = src.with_name("720p_" + src.name)
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-vf",
                    "scale=-2:720",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    str(transcoded),
                ]
            )
            outputs.append(
                _upload(
                    transcoded, _sibling_key(object_name, "720p_"), "video/mp4", "720p"
                )
            )

    await publish(
        OUT_TOPIC, {"object_name": object_name, "variants": outputs}, key=object_name
    )


def _sibling_key(object_name: str, prefix: str) -> str:
    p = Path(object_name)
    return str(p.with_name(prefix + p.name))


def _upload(
    local_path: Path, object_name: str, content_type: str, variant: str
) -> dict:
    data = local_path.read_bytes()
    url = put_object(object_name, data, content_type)
    return {
        "variant": variant,
        "url": url,
        "object_name": object_name,
        "bytes": len(data),
    }


def _run(cmd: list[str]) -> None:
    log.info("ffmpeg %s", " ".join(cmd[1:]))
    subprocess.run(cmd, check=True, capture_output=True)


async def main() -> None:
    stop = asyncio.Event()
    await consume_with_dlq(
        topic=TOPIC,
        group_id=f"{settings.kafka_consumer_group}-transcode",
        handler=_handle,
        dlq_topic=DLQ_TOPIC,
        stop_event=stop,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
