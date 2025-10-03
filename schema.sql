-- Song Search Arena Database Schema
-- Execute this in your Supabase SQL Editor
-- Note: Track metadata is loaded from JSON file, not stored in database

-- Queries table
CREATE TABLE IF NOT EXISTS queries (
    query_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL CHECK (task_type IN ('text', 'song')),
    query_text TEXT,
    seed_track_id TEXT,
    intents TEXT[],
    genres TEXT[],
    era TEXT,
    CONSTRAINT query_type_check CHECK (
        (task_type = 'text' AND query_text IS NOT NULL AND seed_track_id IS NULL) OR
        (task_type = 'song' AND seed_track_id IS NOT NULL AND query_text IS NULL)
    )
);

-- Systems table
CREATE TABLE IF NOT EXISTS systems (
    system_id TEXT PRIMARY KEY,
    system_version TEXT,
    config_json JSONB,
    config_hash TEXT,
    dataset_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Candidates table (raw system outputs)
CREATE TABLE IF NOT EXISTS candidates (
    system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    query_id TEXT REFERENCES queries(query_id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    extras JSONB,
    PRIMARY KEY (system_id, query_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_candidates_system_query ON candidates(system_id, query_id);

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    policy_version TEXT PRIMARY KEY,
    policy_json JSONB NOT NULL,
    active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure only one active policy
CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_active ON policies(active) WHERE active = TRUE;

-- Final lists table (post-processed results)
CREATE TABLE IF NOT EXISTS final_lists (
    policy_version TEXT REFERENCES policies(policy_version) ON DELETE CASCADE,
    system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    query_id TEXT REFERENCES queries(query_id) ON DELETE CASCADE,
    final_order TEXT[] NOT NULL,
    filter_counts JSONB NOT NULL,
    depth_scanned INTEGER NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (policy_version, system_id, query_id)
);

CREATE INDEX IF NOT EXISTS idx_final_lists_system_query ON final_lists(system_id, query_id);

-- Pairs table (system comparisons)
CREATE TABLE IF NOT EXISTS pairs (
    pair_id TEXT PRIMARY KEY,
    left_system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    right_system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    UNIQUE (left_system_id, right_system_id)
);

-- Tasks table (query × pair scheduling)
CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id TEXT REFERENCES queries(query_id) ON DELETE CASCADE,
    pair_id TEXT REFERENCES pairs(pair_id) ON DELETE CASCADE,
    target_judgments INTEGER NOT NULL,
    collected_judgments INTEGER NOT NULL DEFAULT 0,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    is_practice BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(done);
CREATE INDEX IF NOT EXISTS idx_tasks_query ON tasks(query_id);
CREATE INDEX IF NOT EXISTS idx_tasks_pair ON tasks(pair_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_query_pair ON tasks(query_id, pair_id);

-- Task assignments (prevent duplicate serving)
CREATE TABLE IF NOT EXISTS task_assignments (
    rater_id TEXT NOT NULL,
    task_id UUID REFERENCES tasks(task_id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (rater_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_task_assignments_rater ON task_assignments(rater_id);
CREATE INDEX IF NOT EXISTS idx_task_assignments_task ON task_assignments(task_id);

-- Raters table
CREATE TABLE IF NOT EXISTS raters (
    rater_id TEXT PRIMARY KEY,
    display_name TEXT,
    email TEXT,
    country TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    soft_cap INTEGER,
    total_cap INTEGER,
    spotify_refresh_token TEXT,
    selected_genres TEXT[]
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rater_id TEXT REFERENCES raters(rater_id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_rater ON sessions(rater_id);

-- Judgments table
CREATE TABLE IF NOT EXISTS judgments (
    judgment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
    rater_id TEXT REFERENCES raters(rater_id) ON DELETE CASCADE,
    query_id TEXT REFERENCES queries(query_id) ON DELETE CASCADE,
    pair_id TEXT REFERENCES pairs(pair_id) ON DELETE CASCADE,
    left_system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    right_system_id TEXT REFERENCES systems(system_id) ON DELETE CASCADE,
    left_list TEXT[] NOT NULL,
    right_list TEXT[] NOT NULL,
    choice TEXT NOT NULL CHECK (choice IN ('left', 'right', 'tie')),
    confidence SMALLINT CHECK (confidence BETWEEN 1 AND 3),
    rng_seed TEXT NOT NULL,
    presented_at TIMESTAMPTZ NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_judgments_rater ON judgments(rater_id);
CREATE INDEX IF NOT EXISTS idx_judgments_session ON judgments(session_id);
CREATE INDEX IF NOT EXISTS idx_judgments_query ON judgments(query_id);
CREATE INDEX IF NOT EXISTS idx_judgments_pair ON judgments(pair_id);

-- Rater Spotify top artists/tracks
-- Stores paginated API responses (50 items per row)
-- Multiple rows per (rater_id, kind, time_range) with different batch_offset values
CREATE TABLE IF NOT EXISTS rater_spotify_top (
    rater_id TEXT REFERENCES raters(rater_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('artists', 'tracks')),
    time_range TEXT NOT NULL CHECK (time_range IN ('short_term', 'medium_term', 'long_term')),
    batch_offset INTEGER NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rater_id, kind, time_range, batch_offset)
);

CREATE INDEX IF NOT EXISTS idx_rater_spotify_top_rater ON rater_spotify_top(rater_id);
CREATE INDEX IF NOT EXISTS idx_rater_spotify_top_lookup ON rater_spotify_top(rater_id, kind, time_range);
