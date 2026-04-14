#!/bin/bash
# Create pg_stat_statements extension in the postgres database
# This is required for PostgreSQL receiver top query monitoring
# The extension is also created in the otel database via init.sql

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
EOSQL

echo "pg_stat_statements extension created in postgres database"
