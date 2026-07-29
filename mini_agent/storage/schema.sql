CREATE TABLE IF NOT EXISTS sessions (
    user_id TEXT NOT NULL,
    id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
ON sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'tool')),
    content TEXT,
    tool_calls_json TEXT,
    tool_call_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id, session_id)
        REFERENCES sessions(user_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id
ON messages(user_id, session_id, id);

CREATE INDEX IF NOT EXISTS idx_messages_tool_call_id
ON messages(user_id, session_id, tool_call_id);

CREATE TABLE IF NOT EXISTS session_summaries (
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    summarized_until_message_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, session_id),
    FOREIGN KEY (user_id, session_id)
        REFERENCES sessions(user_id, id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'completed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (user_id, session_id)
        REFERENCES sessions(user_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_todos_session_status
ON todos(user_id, session_id, status, id);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_input TEXT NOT NULL,
    status TEXT NOT NULL,
    total_steps INTEGER NOT NULL DEFAULT 0,
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY (user_id, session_id)
        REFERENCES sessions(user_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_traces_session_started
ON traces(user_id, session_id, started_at DESC);

CREATE TABLE IF NOT EXISTS trace_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    event_index INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    name TEXT,
    input_json TEXT,
    output_json TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trace_id)
        REFERENCES traces(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trace_steps_trace
ON trace_steps(trace_id, step_number, event_index);

