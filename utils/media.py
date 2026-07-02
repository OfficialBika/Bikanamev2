from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from aiogram.types import Message


@dataclass(frozen=True)
class ExtractedMedia:
    obj: Any
    media_type: str
    source_message: Message


def _document_media_type(document) -> str | None:
    if not document:
        return None
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    file_name = str(getattr(document, "file_name", "") or "").lower()
    if mime_type.startswith("image/") or file_name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return "photo"
    if mime_type.startswith("video/") or file_name.endswith((".mp4", ".mkv", ".mov", ".webm")):
        return "video"
    return None


def extract_media(message: Message) -> ExtractedMedia | None:
    """Use replied media first for manual lookup; otherwise use the message itself."""
    target = message.reply_to_message or message
    if getattr(target, "photo", None):
        return ExtractedMedia(target.photo[-1], "photo", target)
    if getattr(target, "video", None):
        return ExtractedMedia(target.video, "video", target)
    if getattr(target, "animation", None):
        return ExtractedMedia(target.animation, "video", target)
    document = getattr(target, "document", None)
    doc_type = _document_media_type(document)
    if document and doc_type:
        return ExtractedMedia(document, doc_type, target)
    return None


def has_media(message: Message) -> bool:
    return extract_media(message) is not None
