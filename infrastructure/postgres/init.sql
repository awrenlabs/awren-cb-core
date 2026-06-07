CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY,
    type VARCHAR(255) NOT NULL,
    label VARCHAR(500) NOT NULL,
    description TEXT,
    properties JSON DEFAULT '{}' NOT NULL,
    identifiers JSON DEFAULT '[]' NOT NULL,
    metadata JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY,
    type VARCHAR(255) NOT NULL,
    source_id UUID NOT NULL REFERENCES entities(id),
    target_id UUID NOT NULL REFERENCES entities(id),
    properties JSON DEFAULT '{}' NOT NULL,
    metadata JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY,
    type VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    source VARCHAR(255) NOT NULL DEFAULT 'system',
    subject_id UUID NOT NULL REFERENCES entities(id),
    object_ids JSON DEFAULT '[]' NOT NULL,
    payload JSON DEFAULT '{}' NOT NULL,
    metadata JSON DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
