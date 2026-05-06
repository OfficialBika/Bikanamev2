from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from aiogram.types import Message


@dataclass(frozen=True)
class ExtractedMedia:
    obj: Any
    media_type: str
    source_message: Message


def extract_media(message: Message) -> ExtractedMedia | None:
    """Use replied media first, otherwise the message itself."""
    target = message.reply_to_message or message
    if target.photo:
        return ExtractedMedia(target.photo[-1], "photo", target)
    if target.video:
        return ExtractedMedia(target.video, "video", target)
    if target.animation:
        return ExtractedMedia(target.animation, "video", target)
    if target.document:
        mt = (target.document.mime_type or "").lower()
        if mt.startswith("image/"):
            return ExtractedMedia(target.document, "photo", target)
        if mt.startswith("video/"):
            return ExtractedMedia(target.document, "video", target)
    return None


def has_media(message: Message) -> bool:
    return extract_media(message) is not None
