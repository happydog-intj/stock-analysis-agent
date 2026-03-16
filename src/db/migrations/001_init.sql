-- 初始化数据库表结构
-- 版本：001

CREATE TABLE IF NOT EXISTS sentiment_records (
    id           SERIAL PRIMARY KEY,
    platform     VARCHAR(32)  NOT NULL,
    ticker       VARCHAR(16)  NOT NULL,
    content      TEXT         NOT NULL,
    score        FLOAT        NOT NULL,
    sentiment    VARCHAR(16)  NOT NULL,
    topics       JSONB        NOT NULL DEFAULT '[]',
    confidence   FLOAT        NOT NULL DEFAULT 0.5,
    captured_at  TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sentiment_platform_ticker_time
    ON sentiment_records (platform, ticker, captured_at DESC);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    id               SERIAL PRIMARY KEY,
    snapshot_time    TIMESTAMPTZ NOT NULL,
    period           VARCHAR(16) NOT NULL,
    ticker           VARCHAR(16) NOT NULL,
    sentiment_avg    FLOAT,
    sentiment_dist   JSONB,
    top_topics       JSONB,
    price            FLOAT,
    change_pct       FLOAT,
    volume           BIGINT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_snapshot_ticker_time
    ON daily_snapshots (ticker, snapshot_time DESC);

CREATE TABLE IF NOT EXISTS announcements (
    id           SERIAL PRIMARY KEY,
    ticker       VARCHAR(16)  NOT NULL,
    doc_id       VARCHAR(64)  NOT NULL UNIQUE,
    title        TEXT         NOT NULL,
    type         VARCHAR(32)  NOT NULL,
    priority     VARCHAR(16)  NOT NULL,
    url          TEXT,
    content      TEXT,
    published_at TIMESTAMPTZ,
    captured_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_announcements_ticker_priority
    ON announcements (ticker, priority, captured_at DESC);

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id           SERIAL PRIMARY KEY,
    ticker       VARCHAR(16)  NOT NULL,
    name         VARCHAR(64),
    price        FLOAT,
    change_pct   FLOAT,
    market_cap   FLOAT,
    pe_ratio     FLOAT,
    revenue_ttm  FLOAT,
    volume       BIGINT,
    captured_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_competitor_ticker_date
    ON competitor_snapshots (ticker, captured_at DESC);
