-- Forex Pipeline SQLite Schema
-- WAL mode enabled at connection time, not in DDL

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          TEXT PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    data_hash       TEXT NOT NULL,
    spec_version    TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    total_trades    INTEGER,
    status          TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'checkpointed'))
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    backtest_run_id TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    entry_time      TEXT NOT NULL,
    exit_time       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    spread_cost     REAL NOT NULL,
    slippage_cost   REAL NOT NULL,
    pnl_pips        REAL NOT NULL,
    session         TEXT NOT NULL,
    lot_size        REAL NOT NULL,
    candidate_id    INTEGER,
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_trades_strategy_id ON trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_candidate_id ON trades(candidate_id);

-- Per-fold score storage for CV-inside-objective optimization (D1 Research Update)
CREATE TABLE IF NOT EXISTS fold_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_run_id TEXT NOT NULL,
    candidate_id    INTEGER,
    fold_id         INTEGER NOT NULL,
    fold_start_bar  INTEGER NOT NULL,
    fold_end_bar    INTEGER NOT NULL,
    sharpe_ratio    REAL,
    profit_factor   REAL,
    max_drawdown_pips REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    total_pnl       REAL,
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_fold_scores_run_id ON fold_scores(backtest_run_id);
CREATE INDEX IF NOT EXISTS idx_fold_scores_candidate ON fold_scores(candidate_id);
