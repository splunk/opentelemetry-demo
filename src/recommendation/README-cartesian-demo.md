# Splunk DBMon Demo: The Cartesian Join Catastrophe

**Splunk Observability Cloud - Database Monitoring | OTel Astronomy Shop | PostgreSQL**

## Overview

This demo is integrated into the existing **recommendation service** and controlled via **flagd** feature flag. When enabled, every recommendation request also executes a PostgreSQL query that creates a Cartesian join, processing 500 million rows to return just 10 results.

## Quick Start

### 1. Initialize the Database

Run the SQL setup script against your PostgreSQL instance:

```bash
kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}') -- \
  psql -U root -d astronomy_shop -f /path/to/init-db.sql
```

Or copy and run manually:
```bash
kubectl cp init-db.sql postgres-pod:/tmp/init-db.sql
kubectl exec -it postgres-pod -- psql -U root -d astronomy_shop -f /tmp/init-db.sql
```

### 2. Enable the Feature Flag

Via flagd UI or API:
```bash
# Set the flag to "on"
curl -X PUT http://flagd:8016/flags/recommendationCartesianQuery \
  -H "Content-Type: application/json" \
  -d '{"defaultVariant": "on"}'
```

Or edit `src/flagd/demo.flagd.json` and redeploy:
```json
"recommendationCartesianQuery": {
  "defaultVariant": "on"   // Change from "off" to "on"
}
```

### 3. Generate Load

The existing load generator will trigger the slow queries through normal recommendation requests.

## Demo Scenario

A developer rewrites the product recommendation query and accidentally drops the JOIN condition, creating a Cartesian product between two tables. The query still returns correct results - it just processes 500 million intermediate rows to do so, taking 12+ seconds per call.

### Why This Scenario Works Well

- The bug passes code review and functional testing - it only fails at production data volume
- The execution plan shows a dramatic row explosion (500M rows for 10 results)
- The 12+ second runtime reliably exceeds the DBMon 10s sampling window
- Resolution is instant - just toggle the flag off

## Query Comparison

### Bad Query (Cartesian Join)

`ON 1=1` creates a Cartesian product: 5,000 products x 100,000 tags = **500,000,000 intermediate rows**.

```sql
SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
FROM products p
JOIN product_tags pt ON 1=1              -- CARTESIAN JOIN - missing condition
WHERE p.category = $1
  AND pt.tag     = $2
ORDER BY pt.relevance_score DESC
LIMIT 10;
```

### Good Query (Correct JOIN)

```sql
SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
FROM products p
JOIN product_tags pt ON pt.product_id = p.product_id   -- correct JOIN condition
WHERE p.category = $1
  AND pt.tag     = $2
ORDER BY pt.relevance_score DESC
LIMIT 10;
```

### Performance Comparison

| Metric | Bad Query | Fixed Query |
|--------|-----------|-------------|
| Join type | Nested Loop Cartesian | Index Scan |
| Rows processed | 500,000,000 | ~20 |
| Execution time | ~12,800 ms | ~0.8 ms |

## Demo Steps (8 minutes)

| # | Step | Actions | Say |
|---|------|---------|-----|
| 01 | **The Alert** | Open APM Service Map. Point to `recommendationservice` in red. Show P99 latency spike. | "The SRE just got paged. Is this the app or the database?" |
| 02 | **Trace Drill-Down** | Click into a slow trace. Show the waterfall - `db.get_product_recommendations` span takes 11+ seconds. | "We can see it's a DB call. OTel gives us the span - but not why it's slow internally." |
| 03 | **Jump to DBMon** | Click 'View in Database Monitoring' on the DB span. Show query stats: avg 12.8s, 100% of calls slow. | "One click from the trace to the query. No DBA required. No ticket queue." |
| 04 | **Execution Plan** | Open the execution plan. Point to: Nested Loop, 500M rows, product_tags scanned 5,000 times. Highlight `ON 1=1` in the query text. | "500 million rows for a query that returns 10. One missing JOIN condition. Worked fine in staging." |
| 05 | **The Fix** | Toggle the feature flag off (or show the code fix). | "Let me show you the fix in real-time..." |
| 06 | **Resolution** | Watch APM latency drop immediately. | "Instant resolution. Toggle the flag - the bad query stops executing." |

## Configuration

### Environment Variables for Recommendation Service

Add these to your recommendation service deployment:

```yaml
env:
  - name: POSTGRES_HOST
    value: "postgres"
  - name: POSTGRES_PORT
    value: "5432"
  - name: POSTGRES_DB
    value: "astronomy_shop"
  - name: POSTGRES_USER
    value: "demo_app_user"
  - name: POSTGRES_PASSWORD
    value: "demo_password"
```

### Feature Flag

The flag is defined in `src/flagd/demo.flagd.json`:

```json
"recommendationCartesianQuery": {
  "description": "DBMon Demo: Triggers a Cartesian join query (500M rows) in recommendation service PostgreSQL calls.",
  "state": "ENABLED",
  "variants": {
    "on": true,
    "off": false
  },
  "defaultVariant": "off"
}
```

## Files

| File | Description |
|------|-------------|
| `init-db.sql` | Database setup script - creates tables and seeds 5K products, 100K tags |
| `README.md` | This documentation |

## Integration Points

The demo is integrated into:
- `src/recommendation/recommendation_server.py` - Added Cartesian query execution
- `src/recommendation/requirements.txt` - Added psycopg2-binary
- `src/flagd/demo.flagd.json` - Added `recommendationCartesianQuery` flag

## Troubleshooting

### Query Not Slow Enough?

Increase the number of tags per product in `init-db.sql`:
```sql
-- Change from 20 to 40 tags per product
FROM generate_series(1, 5000) gs, generate_series(1, 40);
```

### PostgreSQL Connection Fails

Check that the recommendation service can reach PostgreSQL and credentials are correct:
```bash
kubectl exec -it recommendation-pod -- python -c "
import psycopg2
conn = psycopg2.connect(host='postgres', database='astronomy_shop', user='demo_app_user', password='demo_password')
print('Connected successfully')
conn.close()
"
```

### Verify Data Volume

```sql
SELECT 'products' as t, COUNT(*) FROM products
UNION ALL
SELECT 'product_tags', COUNT(*) FROM product_tags;
```

Expected: 5,000 products, 100,000 tags.
