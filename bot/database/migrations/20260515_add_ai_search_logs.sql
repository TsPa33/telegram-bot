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

CREATE INDEX IF NOT EXISTS idx_ai_search_logs_created_at ON ai_search_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_search_logs_intent_category ON ai_search_logs(intent, category);
