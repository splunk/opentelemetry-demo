-- Splunk DBMon Demo: The Cartesian Join Catastrophe
-- PostgreSQL v14+ required
-- Run this script to set up the demo database

-- Enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create tables
CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    product_id   VARCHAR(64) UNIQUE NOT NULL,
    name         VARCHAR(255),
    category     VARCHAR(64),
    price        DECIMAL(10,2),
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_tags (
    id              SERIAL PRIMARY KEY,
    product_id      VARCHAR(64) NOT NULL,  -- JOIN key the bad query ignores
    tag             VARCHAR(64),
    relevance_score DECIMAL(4,3)
);

-- Seed data: 5,000 products
INSERT INTO products (product_id, name, category, price)
SELECT 'prod_' || gs, 'Product ' || gs,
       (ARRAY['telescope','eyepiece','mount','camera','filter'])[floor(random()*5+1)],
       (random() * 2000 + 50)::DECIMAL
FROM generate_series(1, 5000) gs
ON CONFLICT (product_id) DO NOTHING;

-- Seed data: 100,000 tags (~20 per product)
-- Increase to 40 if query runs < 12s on your hardware
INSERT INTO product_tags (product_id, tag, relevance_score)
SELECT 'prod_' || gs,
       (ARRAY['beginner','advanced','astrophotography','visual','planetary',
              'deepsky','portable','goto','wifi','budget'])[floor(random()*10+1)],
       (random())::DECIMAL
FROM generate_series(1, 5000) gs, generate_series(1, 20);

-- DO NOT create indexes or run ANALYZE - we want worst-case execution plan

-- Create application user with settings that force Nested Loop Cartesian
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app_user') THEN
        CREATE ROLE demo_app_user WITH LOGIN PASSWORD 'demo_password';
    END IF;
END
$$;

GRANT SELECT ON products TO demo_app_user;
GRANT SELECT ON product_tags TO demo_app_user;

-- Force worst-case execution plan for app user
ALTER ROLE demo_app_user SET work_mem = '64kB';
ALTER ROLE demo_app_user SET enable_hashjoin  = OFF;
ALTER ROLE demo_app_user SET enable_mergejoin = OFF;

-- Verify data counts
SELECT 'products' as table_name, COUNT(*) as row_count FROM products
UNION ALL
SELECT 'product_tags', COUNT(*) FROM product_tags;
