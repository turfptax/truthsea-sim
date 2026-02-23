-- TruthSea Local Simulation Schema (SQLite)

-- Core data tables (mirror existing TruthSea data model)

CREATE TABLE IF NOT EXISTS chain_definition (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    discipline  TEXT NOT NULL,
    crown_claim TEXT NOT NULL,
    node_count  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chain_node (
    id              TEXT PRIMARY KEY,
    chain_id        TEXT NOT NULL REFERENCES chain_definition(id),
    claim           TEXT NOT NULL,
    discipline      TEXT NOT NULL,
    layer           INTEGER NOT NULL,  -- -1=Alternative, 0=Foundation, 1=Method, 2=Inference, 3=Crown
    source_type     TEXT NOT NULL,
    correspondence  INTEGER NOT NULL DEFAULT 0,
    coherence       INTEGER NOT NULL DEFAULT 0,
    convergence     INTEGER NOT NULL DEFAULT 0,
    pragmatism      INTEGER NOT NULL DEFAULT 0,
    intrinsic_score REAL,
    chain_score     REAL,
    weakest_link    TEXT,
    moral_care                INTEGER DEFAULT 0,
    moral_fairness            INTEGER DEFAULT 0,
    moral_loyalty             INTEGER DEFAULT 0,
    moral_authority           INTEGER DEFAULT 0,
    moral_sanctity            INTEGER DEFAULT 0,
    moral_liberty             INTEGER DEFAULT 0,
    moral_epistemic_humility  INTEGER DEFAULT 0,
    moral_temporal_stewardship INTEGER DEFAULT 0,
    score_reasoning TEXT,  -- JSON
    key_metrics     TEXT,  -- JSON
    depends         TEXT DEFAULT '',  -- comma-separated node IDs
    contradicts     TEXT DEFAULT '',  -- comma-separated node IDs
    agent_id        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chain_node_chain ON chain_node(chain_id);
CREATE INDEX IF NOT EXISTS idx_chain_node_layer ON chain_node(layer);

CREATE TABLE IF NOT EXISTS evidence_source (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quanta_id   TEXT NOT NULL REFERENCES chain_node(id),
    chain_id    TEXT NOT NULL REFERENCES chain_definition(id),
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    finding     TEXT NOT NULL,
    year        INTEGER,
    source_type TEXT DEFAULT 'paper',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_quanta ON evidence_source(quanta_id);
CREATE INDEX IF NOT EXISTS idx_evidence_chain ON evidence_source(chain_id);

CREATE TABLE IF NOT EXISTS chain_edge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id    TEXT NOT NULL REFERENCES chain_definition(id),
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    edge_type   TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(chain_id, source_node, target_node, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_chain_edge_chain ON chain_edge(chain_id);

-- Simulation tables

CREATE TABLE IF NOT EXISTS agent (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    agent_type            TEXT NOT NULL CHECK(agent_type IN ('honest','random','malicious','strategic')),
    stake                 REAL DEFAULT 100.0,
    reputation            REAL DEFAULT 0.5,
    accuracy_rate         REAL DEFAULT 0.0,
    total_verifications   INTEGER DEFAULT 0,
    correct_verifications INTEGER DEFAULT 0,
    created_at            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulation_run (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    config       TEXT,  -- JSON
    status       TEXT DEFAULT 'pending' CHECK(status IN ('pending','running','complete')),
    started_at   TEXT,
    completed_at TEXT,
    summary      TEXT   -- JSON
);

CREATE TABLE IF NOT EXISTS verification (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quanta_id   TEXT NOT NULL REFERENCES chain_node(id),
    agent_id    TEXT NOT NULL REFERENCES agent(id),
    run_id      INTEGER NOT NULL REFERENCES simulation_run(id),
    verdict     TEXT NOT NULL CHECK(verdict IN ('accept','reject','flag')),
    confidence  REAL DEFAULT 0.5,
    round       INTEGER NOT NULL,
    timestamp   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_verification_quanta ON verification(quanta_id);
CREATE INDEX IF NOT EXISTS idx_verification_agent ON verification(agent_id);
CREATE INDEX IF NOT EXISTS idx_verification_run ON verification(run_id);

CREATE TABLE IF NOT EXISTS round_snapshot (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES simulation_run(id),
    round              INTEGER NOT NULL,
    quanta_id          TEXT NOT NULL REFERENCES chain_node(id),
    consensus_score    REAL,
    verification_count INTEGER DEFAULT 0,
    accept_rate        REAL DEFAULT 0.0,
    flag_rate          REAL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_snapshot_run ON round_snapshot(run_id);

CREATE TABLE IF NOT EXISTS stake_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT NOT NULL REFERENCES agent(id),
    run_id     INTEGER NOT NULL REFERENCES simulation_run(id),
    round      INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('reward','slash','deposit')),
    amount     REAL NOT NULL,
    reason     TEXT,
    timestamp  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS anomaly_flag (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    quanta_id       TEXT NOT NULL REFERENCES chain_node(id),
    run_id          INTEGER NOT NULL REFERENCES simulation_run(id),
    flag_type       TEXT NOT NULL CHECK(flag_type IN ('fabrication','genuine','misinterpretation')),
    probability     REAL NOT NULL,
    flagged_by_agent TEXT REFERENCES agent(id),
    round           INTEGER,
    resolved        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_anomaly_run ON anomaly_flag(run_id);

-- Worldview lens table

CREATE TABLE IF NOT EXISTS worldview_lens (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    correspondence          INTEGER DEFAULT 25,
    coherence               INTEGER DEFAULT 25,
    relativism              INTEGER DEFAULT 25,
    pragmatism              INTEGER DEFAULT 25,
    moral_care              REAL DEFAULT 1.0,
    moral_fairness          REAL DEFAULT 1.0,
    moral_loyalty           REAL DEFAULT 1.0,
    moral_authority         REAL DEFAULT 1.0,
    moral_sanctity          REAL DEFAULT 1.0,
    moral_liberty           REAL DEFAULT 1.0,
    moral_epistemic_humility REAL DEFAULT 1.0,
    moral_temporal_stewardship REAL DEFAULT 1.0,
    global_conviction       REAL DEFAULT 1.0,
    epistemic_humility      INTEGER DEFAULT 50,
    direct_evidence_purity  INTEGER DEFAULT 50,
    chain_rigidity          INTEGER DEFAULT 50,
    pragmatic_skepticism    INTEGER DEFAULT 50,
    created_at              TEXT DEFAULT (datetime('now'))
);
