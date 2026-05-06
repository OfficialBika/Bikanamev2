import logging

logger = logging.getLogger(__name__)


async def ensure_indexes(*args, **kwargs):
    """
    MongoDB read-only mode.

    This bot must not create, update, delete, or modify MongoDB indexes.
    Existing Waifu Database V2 data and indexes are left untouched.
    """
    logger.info("Mongo indexes skipped: read-only mode enabled")
    return
