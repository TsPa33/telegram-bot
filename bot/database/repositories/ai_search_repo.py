import logging

from bot.database.base import execute

logger = logging.getLogger(__name__)


async def ensure_ai_search_logs_table() -> None:
    await execute(
        """
        CREATE TABLE IF NOT EXISTS ai_search_logs (
            id SERIAL PRIMARY KEY,
            raw_query TEXT,
            normalized_query TEXT,
            intent TEXT,
            category TEXT,
            confidence NUMERIC(4,3),
            clarification_needed BOOLEAN NOT NULL DEFAULT FALSE,
            result_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    await execute("CREATE INDEX IF NOT EXISTS idx_ai_search_logs_created_at ON ai_search_logs(created_at DESC);")
    await execute("CREATE INDEX IF NOT EXISTS idx_ai_search_logs_intent_category ON ai_search_logs(intent, category);")


async def log_ai_search(
    *,
    raw_query: str | None,
    normalized_query: str | None,
    intent: str | None,
    category: str | None,
    confidence: float | None,
    clarification_needed: bool,
    result_count: int,
) -> None:
    try:
        await ensure_ai_search_logs_table()
        await execute(
            """
            INSERT INTO ai_search_logs (
                raw_query,
                normalized_query,
                intent,
                category,
                confidence,
                clarification_needed,
                result_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            (raw_query or "")[:700],
            (normalized_query or "")[:700],
            (intent or "unknown")[:40],
            (category or "unknown")[:40],
            confidence,
            bool(clarification_needed),
            max(0, int(result_count or 0)),
        )
    except Exception:
        logger.exception("Failed to write AI search log")
