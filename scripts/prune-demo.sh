#!/usr/bin/env bash
# Demo maintenance — bound volume growth on long-running k3d clusters.
#
# Safe to run on cron (e.g. hourly). Default mode is non-destructive:
#   - prune unused containerd images + exited containers on each k3d node
#   - report DB sizes
#   - run online maintenance (PostgreSQL VACUUM, SQL Server tlog shrink if SIMPLE)
#
# --aggressive flag additionally:
#   - DBCC SHRINKFILE on SQL Server data file (brief I/O spike)
#   - PostgreSQL VACUUM FULL (locks tables — pods may stall briefly)
#   - Kafka pod restart to drop topic backlog (ephemeral, no PVC)
#
# Usage:
#   ./prune-demo.sh                          # safe maintenance
#   ./prune-demo.sh --aggressive             # also do disruptive reclaim
#   ./prune-demo.sh --cluster other-cluster  # different k3d cluster name
#
# Requires: kubectl context pointing at the target cluster, sudo docker
# access for k3d node exec.

set -euo pipefail

CLUSTER="${CLUSTER:-astronomyshop-eu}"
AGGRESSIVE=0
SQL_USER="${SQL_USER:-sa}"
SQL_PASS="${SQL_PASS:-ChangeMe_SuperStrong123!}"
SQL_DB="${SQL_DB:-FraudDetection}"
PG_USER="${PG_USER:-otelu}"
PG_DB="${PG_DB:-otel}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aggressive)  AGGRESSIVE=1; shift ;;
    --cluster)     CLUSTER="$2"; shift 2 ;;
    -h|--help)     sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

log() { printf '\n=== %s ===\n' "$*"; }

# ----------------------------------------------------------------------
log "k3d node prune — containerd unused images + exited containers"
# ----------------------------------------------------------------------
NODES=$(sudo docker ps --filter "name=k3d-${CLUSTER}-cluster-(server|agent)" \
        --format '{{.Names}}' | sort)
for n in $NODES; do
  echo "-- $n --"
  sudo docker exec "$n" sh -c '
    BEFORE=$(du -sh /var/lib/rancher/k3s/agent/containerd 2>/dev/null | cut -f1)
    crictl rmi --prune 2>&1 | grep -c "^Deleted:" | xargs -I{} echo "images pruned: {}"
    EX=$(crictl ps -a -q --state exited 2>/dev/null)
    if [ -n "$EX" ]; then
      crictl rm $EX >/dev/null 2>&1
      echo "exited containers removed: $(echo "$EX" | wc -l)"
    fi
    AFTER=$(du -sh /var/lib/rancher/k3s/agent/containerd 2>/dev/null | cut -f1)
    echo "containerd: $BEFORE -> $AFTER"
  '
done

# ----------------------------------------------------------------------
log "SQL Server (fraud-detection) — sizes + tlog maintenance"
# ----------------------------------------------------------------------
SQLCMD='kubectl exec sql-server-fraud-0 -- /opt/mssql-tools18/bin/sqlcmd -S localhost -U '"$SQL_USER"' -P '"$SQL_PASS"' -C -h -1 -W'

eval "$SQLCMD -Q \"SET NOCOUNT ON;
  SELECT name, recovery_model_desc FROM sys.databases WHERE name='${SQL_DB}';
  USE ${SQL_DB};
  SELECT name + ' ' + type_desc + ' ' + FORMAT(size*8.0/1024,'N1') + ' MB'
    FROM sys.database_files;
  SELECT 'OrderLogs rows='+FORMAT(COUNT(*),'N0') FROM OrderLogs;
  SELECT 'FraudAlerts rows='+FORMAT(COUNT(*),'N0') FROM FraudAlerts;\""

# Ensure SIMPLE recovery (idempotent — no-op if already SIMPLE)
eval "$SQLCMD -Q \"ALTER DATABASE ${SQL_DB} SET RECOVERY SIMPLE;\""

# Shrink the transaction log (always safe under SIMPLE — only reclaims free space)
eval "$SQLCMD -d ${SQL_DB} -Q \"DBCC SHRINKFILE (${SQL_DB}_log, 64);\"" \
  | tail -2

if [ "$AGGRESSIVE" -eq 1 ]; then
  echo "-- aggressive: shrink data file (brief I/O hit) --"
  eval "$SQLCMD -d ${SQL_DB} -Q \"DBCC SHRINKFILE (${SQL_DB}, 0, TRUNCATEONLY);\"" \
    | tail -2
fi

# ----------------------------------------------------------------------
log "PostgreSQL (product-catalog) — sizes + VACUUM"
# ----------------------------------------------------------------------
PSQL='kubectl exec deploy/postgresql -- psql -U '"$PG_USER"' -d '"$PG_DB"' -t -A -c'

eval "$PSQL \"SELECT datname || ' ' || pg_size_pretty(pg_database_size(datname))
              FROM pg_database WHERE datname NOT IN ('template0','template1');\""

if [ "$AGGRESSIVE" -eq 1 ]; then
  echo "-- aggressive: VACUUM FULL (locks tables briefly) --"
  eval "$PSQL 'VACUUM FULL;'"
else
  # Online vacuum — no locks, reclaims dead tuples back to the file system
  # only when at the table tail (otherwise marks space reusable in-place).
  eval "$PSQL 'VACUUM (ANALYZE);'"
fi

# ----------------------------------------------------------------------
log "Valkey (cart) — memory + key count"
# ----------------------------------------------------------------------
kubectl exec deploy/valkey-cart -- valkey-cli INFO memory \
  | grep -E '^used_memory_human|^maxmemory_human' || true
kubectl exec deploy/valkey-cart -- valkey-cli DBSIZE

# ----------------------------------------------------------------------
log "Kafka — log dir sizes"
# ----------------------------------------------------------------------
kubectl exec deploy/kafka -- sh -c '
  echo "topic data: $(du -sh /tmp/kafka-logs 2>/dev/null | cut -f1)"
  echo "broker logs: $(du -sh /opt/kafka/logs 2>/dev/null | cut -f1)"
'

if [ "$AGGRESSIVE" -eq 1 ]; then
  echo "-- aggressive: restarting kafka to drop topic backlog (ephemeral, no PVC) --"
  kubectl rollout restart deploy/kafka
  kubectl rollout status  deploy/kafka --timeout=120s
fi

log "done. Re-run \`du -sh /var/lib/docker/volumes/*\` on the host to confirm reclaim."
