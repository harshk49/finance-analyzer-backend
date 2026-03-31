-- =====================================================
-- Finance Analyzer — Database Initialization Script
-- Runs automatically on first container startup
-- =====================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- fuzzy text search for merchants

-- Grant privileges (redundant for default user, but explicit is good)
GRANT ALL PRIVILEGES ON DATABASE finance_analyzer TO postgres;
