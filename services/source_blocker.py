from __future__ import annotations

import re
from typing import Any, Iterable

from aiogram.types import Message

from config import settings
from locales import en, my


def _norm_username(value: Any) -> str:
    value = str(value or "").strip().lower().lstrip("@")
    return f"@{value}" if value else ""


def _clean_title(value: Any) -> str:
    value = str(value or "").strip().lower()
    if not value:
        return ""
    value = value.replace("_", " ")
    value = value.replace("[", " ").replace("]", " ").replace("(", " ").replace(")", " ")
    value = re.sub(r"[^0-9a-z\u1000-\u109f\u1d00-\u1d7f\u1d80-\u1dbf\u0250-\u02af\u0370-\u03ff\s]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _full_name(user: Any) -> str:
    if not user:
        return ""
    full_name = getattr(user, "full_name", None)
    if full_name:
        return str(full_name)
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    return f"{first} {last}".strip()


def _iter_possible_users(message: Message) -> Iterable[Any]:
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        sender_user = getattr(origin, "sender_user", None)
        if sender_user is not None:
            yield sender_user
    for attr in ("via_bot", "forward_from", "from_user"):
        user = getattr(message, attr, None)
        if user is not None:
            yield user


def _iter_possible_chats(message: Message) -> Iterable[Any]:
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if chat is not None:
            yield chat
    for attr in ("forward_from_chat", "sender_chat", "chat"):
        chat = getattr(message, attr, None)
        if chat is not None:
            yield chat


def source_identity(message: Message) -> dict[str, set[str] | set[int]]:
    """Collect best-effort source identity from forwarded/via/direct bot media."""
    user_ids: set[int] = set()
    usernames: set[str] = set()
    titles: set[str] = set()

    for user in _iter_possible_users(message):
        user_id = getattr(user, "id", None)
        try:
            if user_id is not None:
                user_ids.add(int(user_id))
        except Exception:
            pass
        username = _norm_username(getattr(user, "username", None))
        if username:
            usernames.add(username)
        name = _clean_title(_full_name(user))
        if name:
            titles.add(name)

    for chat in _iter_possible_chats(message):
        username = _norm_username(getattr(chat, "username", None))
        if username:
            usernames.add(username)
        title = _clean_title(getattr(chat, "title", None) or getattr(chat, "full_name", None) or getattr(chat, "first_name", None))
        if title:
            titles.add(title)

    origin = getattr(message, "forward_origin", None)
    hidden = getattr(origin, "sender_user_name", None) if origin is not None else None
    if hidden:
        title = _clean_title(hidden)
        if title:
            titles.add(title)

    forward_sender_name = getattr(message, "forward_sender_name", None)
    if forward_sender_name:
        title = _clean_title(forward_sender_name)
        if title:
            titles.add(title)

    return {"user_ids": user_ids, "usernames": usernames, "titles": titles}


def is_blocked_source(message: Message | None) -> bool:
    if message is None:
        return False

    ident = source_identity(message)
    blocked_ids = set(getattr(settings, "blocked_source_user_ids", set()) or set())
    if blocked_ids and ident["user_ids"] & blocked_ids:  # type: ignore[operator]
        return True

    blocked_usernames = {_norm_username(x) for x in (getattr(settings, "blocked_source_usernames", set()) or set())}
    blocked_usernames.discard("")
    if blocked_usernames and ident["usernames"] & blocked_usernames:  # type: ignore[operator]
        return True

    blocked_titles = {_clean_title(x) for x in (getattr(settings, "blocked_source_titles", []) or [])}
    blocked_titles.discard("")
    for source_title in ident["titles"]:  # type: ignore[assignment]
        for blocked_title in blocked_titles:
            # Keep this strict enough to avoid blocking the legit @Character_Catcher_Bot.
            # The default blocked title includes "beta".
            if source_title == blocked_title:
                return True
            if "beta" in blocked_title and blocked_title in source_title:
                return True
    return False


def blocked_source_text() -> str:
    return f"{my.BLOCKED_SOURCE}\n\n{en.BLOCKED_SOURCE}"
