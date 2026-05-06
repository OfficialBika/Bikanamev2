from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import imagehash
from PIL import Image, ImageOps

from config import settings


@dataclass(frozen=True)
class MediaHash:
    sha256: str | None = None
    phash: str | None = None
    frame_hashes: Tuple[str, ...] = ()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phash_image_bytes(data: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            return str(imagehash.phash(img))
    except Exception:
        return None


def hamming_hex(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return bin(int(str(a), 16) ^ int(str(b), 16)).count("1")
    except Exception:
        return None


def frame_hashes_from_video_bytes(data: bytes) -> Tuple[str, ...]:
    tmp = None
    cap = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".mp4")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cap = cv2.VideoCapture(tmp)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return ()
        hashes: List[str] = []
        for pct in settings.video_sample_points:
            idx = max(0, min(total - 1, int(total * pct)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            hashes.append(str(imagehash.phash(img)))
        return tuple(hashes)
    except Exception:
        return ()
    finally:
        if cap is not None:
            cap.release()
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def hash_photo(data: bytes) -> MediaHash:
    return MediaHash(sha256=sha256_bytes(data), phash=phash_image_bytes(data), frame_hashes=())


def hash_video(data: bytes) -> MediaHash:
    return MediaHash(sha256=sha256_bytes(data), phash=None, frame_hashes=frame_hashes_from_video_bytes(data))
