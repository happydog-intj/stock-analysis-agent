-- =============================================================================
-- 001_init.sql — 初始化数据库表结构
-- 在 docker-compose 首次启动时由 /docker-entrypoint-initdb.d/ 自动执行
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 枚举类型
DO $$ BEGIN
    CREATE TYPE platform_enum AS ENUM (
        'xueqiu', 'reddit', 'futu', 'tiger', 'weibo', 'other'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE sentiment_label_enum AS ENUM (
        'very_bullish', 'bullish', 'neutral', 'bearish', 'very_bearish'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE report_period_enum AS ENUM (
        'morning', 'noon', 'close', 'daily'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE announcement_type_enum AS ENUM (
        'earnings', 'buyback', 'shareholding', 'dividend', 'management', 'general'
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- =============================================================================
-- 舆情情绪记录表
-- =============================================================================
CREATE TABLE IF NOT EXISTS sentiment_records (
    id              BIGSERIAL PRIMARY KEY,
    platform        platform_enum           NOT NULL,
    ticker          VARCHAR(20)             NOT NULL,
    external_id     VARCHAR(128),
    content         TEXT                    NOT NULL,
    author          VARCHAR(128),
    score           FLOAT,
    sentiment       sentiment_label_enum,
    topics          JSONB,
    confidence      FLOAT,
    captured_at     TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    analyzed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_sentiment_ticker_platform_captured
    ON sentiment_records (ticker, platform, captured_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ix_sentiment_external_id
    ON sentiment_records (platform, external_id)
    WHERE external_id IS NOT NULL;

-- =============================================================================
-- 每日情绪快照表
-- =============================================================================
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_time   TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    period          report_period_enum      NOT NULL,
    ticker          VARCHAR(20)             NOT NULL,
    sentiment_avg   FLOAT,
    sentiment_dist  JSONB,
    top_topics      JSONB,
    sample_count    INTEGER                 NOT NULL DEFAULT 0,
    price           FLOAT,
    volume          FLOAT,
    change_pct      FLOAT
);

CREATE INDEX IF NOT EXISTS ix_snapshot_ticker_period_time
    ON daily_snapshots (ticker, period, snapshot_time DESC);

-- =============================================================================
-- 港交所公告表
-- =============================================================================
CREATE TABLE IF NOT EXISTS announcements (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(20)                 NOT NULL,
    title               VARCHAR(512)                NOT NULL,
    announcement_type   announcement_type_enum      NOT NULL DEFAULT 'general',
    priority            SMALLINT                    NOT NULL DEFAULT 1,
    content             TEXT,
    url                 VARCHAR(1024),
    file_url            VARCHAR(1024),
    published_at        TIMESTAMPTZ                 NOT NULL,
    captured_at         TIMESTAMPTZ                 NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_announcement_ticker_published
    ON announcements (ticker, published_at DESC);

-- =============================================================================
-- 竞对行情快照表
-- =============================================================================
CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ticker          VARCHAR(20)     NOT NULL,
    price           FLOAT,
    open_price      FLOAT,
    high_price      FLOAT,
    low_price       FLOAT,
    volume          FLOAT,
    change_pct      FLOAT,
    market_cap      FLOAT,
    revenue_ttm     FLOAT,
    pe_ratio        FLOAT,
    ps_ratio        FLOAT,
    captured_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    trade_date      VARCHAR(10)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_competitor_ticker_date
    ON competitor_snapshots (ticker, trade_date);

SELECT 'Database initialized successfully.' AS status;
