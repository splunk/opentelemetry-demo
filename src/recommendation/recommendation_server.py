#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


# Python
import os
import random
import time
from concurrent import futures

# Pip
import grpc
import psycopg2
from psycopg2 import pool
from opentelemetry import trace, metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

from openfeature.contrib.hook.opentelemetry import TracingHook

# Local
import logging
import demo_pb2
import demo_pb2_grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from metrics import (
    init_metrics
)

cached_ids = []
first_run = True


class PeerServiceInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
    grpc.StreamUnaryClientInterceptor,
    grpc.StreamStreamClientInterceptor,
):
    """gRPC client interceptor that sets peer.service on the active OTel span.

    Runs the call first (so auto-instrumentation creates the span),
    then sets peer.service on the resulting span."""

    def __init__(self, peer_service):
        self._peer_service = peer_service

    def _set_peer_service(self):
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("peer.service", self._peer_service)

    def intercept_unary_unary(self, continuation, client_call_details, request):
        response = continuation(client_call_details, request)
        self._set_peer_service()
        return response

    def intercept_unary_stream(self, continuation, client_call_details, request):
        response = continuation(client_call_details, request)
        self._set_peer_service()
        return response

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        response = continuation(client_call_details, request_iterator)
        self._set_peer_service()
        return response

    def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        response = continuation(client_call_details, request_iterator)
        self._set_peer_service()
        return response

# DBMon Cartesian Demo - PostgreSQL queries
# Bad query: ON 1=1 creates Cartesian product (5000 x 100000 = 500M rows)
CARTESIAN_BAD_QUERY = '''
    SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
    FROM products p
    JOIN product_tags pt ON 1=1
    WHERE p.category = %s AND pt.tag = %s
    ORDER BY pt.relevance_score DESC LIMIT 10'''

# Good query: proper JOIN condition
CARTESIAN_GOOD_QUERY = '''
    SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
    FROM products p
    JOIN product_tags pt ON pt.product_id = p.product_id
    WHERE p.category = %s AND pt.tag = %s
    ORDER BY pt.relevance_score DESC LIMIT 10'''

# Normalized query forms for db.statement attribute (matches pg_stat_statements fingerprint)
# Normalized forms must match pg_stat_statements output exactly.
# PostgreSQL normalizes literal 1=1 as $1=$2, shifting WHERE params to $3/$4.
CARTESIAN_BAD_QUERY_NORMALIZED = '''
    SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
    FROM products p
    JOIN product_tags pt ON $1=$2
    WHERE p.category = $3 AND pt.tag = $4
    ORDER BY pt.relevance_score DESC LIMIT $5'''

CARTESIAN_GOOD_QUERY_NORMALIZED = '''
    SELECT p.product_id, p.name, p.price, pt.tag, pt.relevance_score
    FROM products p
    JOIN product_tags pt ON pt.product_id = p.product_id
    WHERE p.category = $1 AND pt.tag = $2
    ORDER BY pt.relevance_score DESC LIMIT $3'''

CATEGORIES = ['telescope', 'eyepiece', 'mount', 'camera', 'filter']
TAGS = ['beginner', 'advanced', 'astrophotography', 'visual', 'planetary']

# PostgreSQL connection pool (lazy initialized)
pg_pool = None

# Cartesian query rate: flag variant -> (base_interval_seconds, jitter_seconds).
# The slow query fires at most once per (base +/- jitter). Jitter models a
# cache that refreshes after ~N queries rather than on a fixed clock, adding
# realistic variance on top of the steady loadgen cadence.
CARTESIAN_RATE_TIERS = {
    'normal':  (300, 20),  # 5 min +/- 20s
    'fast':    (180, 15),  # 3 min +/- 15s
    'faster':  (60, 10),   # 1 min +/- 10s
    'fastest': (30, 5),    # 30s +/- 5s
}
# Legacy boolean 'on' maps to this tier for backward compatibility.
CARTESIAN_LEGACY_ON_TIER = 'normal'

cartesian_last_exec = 0.0
cartesian_next_interval = 0.0  # base +/- jitter, recomputed after each fire
cartesian_tier = None


def cartesian_variant():
    """Read the flag as a string variant. Tolerates the legacy boolean 'on'/'off'."""
    client = api.get_client()
    variant = client.get_string_value("recommendationCartesianQuery", "off")
    if variant in ("on", "true", "True"):
        return CARTESIAN_LEGACY_ON_TIER
    return variant


def cartesian_rate_limit_ok(tier):
    """
    Fire at most once per (base_interval +/- jitter) for the given tier.
    The first call for a tier (including right after a tier change) fires
    immediately; spacing is recomputed with fresh jitter after each fire.
    Unknown/off tier never fires.
    """
    global cartesian_last_exec, cartesian_next_interval, cartesian_tier
    if tier not in CARTESIAN_RATE_TIERS:
        cartesian_tier = tier
        return False
    base, jitter = CARTESIAN_RATE_TIERS[tier]
    now = time.time()
    # Tier just changed -- fire on this call so flag flips take effect promptly.
    if tier != cartesian_tier:
        cartesian_tier = tier
        cartesian_next_interval = 0.0
    if now - cartesian_last_exec < cartesian_next_interval:
        return False
    cartesian_last_exec = now
    cartesian_next_interval = base + random.uniform(-jitter, jitter)
    return True

class RecommendationService(demo_pb2_grpc.RecommendationServiceServicer):
    def ListRecommendations(self, request, context):
        span = trace.get_current_span()

        # DBMon Cartesian Demo - variant controls fire cadence
        # (off / normal / fast / faster / fastest).
        tier = cartesian_variant()
        if tier != "off":
            span.set_attribute("app.cartesian_demo.enabled", True)
            span.set_attribute("app.cartesian_demo.tier", tier)
            if cartesian_rate_limit_ok(tier):
                span.set_attribute("app.cartesian_demo.rate_limited", False)
                # Execute the slow Cartesian query (bad query = True)
                cartesian_results = execute_cartesian_query(use_bad_query=True)
                if cartesian_results:
                    span.set_attribute("app.cartesian_demo.results", len(cartesian_results))
            else:
                span.set_attribute("app.cartesian_demo.rate_limited", True)
        else:
            span.set_attribute("app.cartesian_demo.enabled", False)

        prod_list = get_product_list(request.product_ids)
        span.set_attribute("app.products_recommended.count", len(prod_list))
        logger.info(f"Receive ListRecommendations for product ids:{prod_list}")

        # build and return response
        response = demo_pb2.ListRecommendationsResponse()
        response.product_ids.extend(prod_list)

        # Collect metrics for this service
        rec_svc_metrics["app_recommendations_counter"].add(len(prod_list), {'recommendation.type': 'catalog'})

        return response

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)


def get_product_list(request_product_ids):
    global first_run
    global cached_ids
    with tracer.start_as_current_span("get_product_list") as span:
        max_responses = 5

        # Formulate the list of characters to list of strings
        request_product_ids_str = ''.join(request_product_ids)
        request_product_ids = request_product_ids_str.split(',')

        # Feature flag scenario - Cache Leak
        if check_feature_flag("recommendationCacheFailure"):
            span.set_attribute("app.recommendation.cache_enabled", True)
            if random.random() < 0.5 or first_run:
                first_run = False
                span.set_attribute("app.cache_hit", False)
                logger.info("get_product_list: cache miss")
                cat_response = product_catalog_stub.GetProduct(demo_pb2.Empty())
                response_ids = [x.id for x in cat_response.products]
                cached_ids = cached_ids + response_ids
                cached_ids = cached_ids + cached_ids[:len(cached_ids) // 4]
                product_ids = cached_ids
            else:
                span.set_attribute("app.cache_hit", True)
                logger.info("get_product_list: cache hit")
                product_ids = cached_ids
        else:
            span.set_attribute("app.recommendation.cache_enabled", False)
            cat_response = product_catalog_stub.ListProducts(demo_pb2.Empty())
            product_ids = [x.id for x in cat_response.products]

        span.set_attribute("app.products.count", len(product_ids))

        # Create a filtered list of products excluding the products received as input
        filtered_products = list(set(product_ids) - set(request_product_ids))
        num_products = len(filtered_products)
        span.set_attribute("app.filtered_products.count", num_products)
        num_return = min(max_responses, num_products)

        # Sample list of indicies to return
        indices = random.sample(range(num_products), num_return)
        # Fetch product ids from indices
        prod_list = [filtered_products[i] for i in indices]

        span.set_attribute("app.filtered_products.list", prod_list)

        return prod_list


def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value


def check_feature_flag(flag_name: str):
    # Initialize OpenFeature
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)


def get_pg_pool():
    """Initialize PostgreSQL connection pool for DBMon demo."""
    global pg_pool
    if pg_pool is None:
        try:
            pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                host=os.environ.get('POSTGRES_HOST', 'postgres'),
                port=int(os.environ.get('POSTGRES_PORT', '5432')),
                database=os.environ.get('POSTGRES_DB', 'astroshop'),
                user=os.environ.get('POSTGRES_USER', 'demo_app_user'),
                password=os.environ.get('POSTGRES_PASSWORD', 'demo_password')
            )
        except Exception as e:
            logging.getLogger('main').warning(f"Failed to create PostgreSQL pool: {e}")
            return None
    return pg_pool


def execute_cartesian_query(use_bad_query: bool):
    """
    Execute the Cartesian demo query against PostgreSQL.
    When use_bad_query=True, executes the 500M row Cartesian join.
    """
    pool = get_pg_pool()
    if pool is None:
        return None

    query = CARTESIAN_BAD_QUERY if use_bad_query else CARTESIAN_GOOD_QUERY
    query_normalized = CARTESIAN_BAD_QUERY_NORMALIZED if use_bad_query else CARTESIAN_GOOD_QUERY_NORMALIZED
    category = random.choice(CATEGORIES)
    tag = random.choice(TAGS)

    db_name = os.environ.get('POSTGRES_DB', 'astroshop')
    db_user = os.environ.get('POSTGRES_USER', 'demo_app_user')

    tracer = trace.get_tracer_provider().get_tracer('recommendationservice')
    with tracer.start_as_current_span('db.get_product_recommendations') as span:
        span.set_attribute('db.system', 'postgresql')
        # Emit both old (db.name) and new (db.namespace) semconv keys so the
        # inferred DB service resolves consistently across all languages.
        span.set_attribute('db.name', db_name)
        span.set_attribute('db.namespace', db_name)
        span.set_attribute('db.user', db_user)
        span.set_attribute('db.operation', 'SELECT')
        span.set_attribute('db.statement', query_normalized)
        span.set_attribute('recommendation.category', category)
        span.set_attribute('recommendation.tag', tag)
        span.set_attribute('recommendation.cartesian_query', use_bad_query)

        conn = None
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute(query, (category, tag))
                results = cur.fetchall()
                span.set_attribute('db.rows_returned', len(results))
                return results
        except Exception as e:
            span.record_exception(e)
            logging.getLogger('main').error(f"Cartesian query failed: {e}")
            return None
        finally:
            if conn:
                pool.putconn(conn)


if __name__ == "__main__":
    service_name = must_map_env('OTEL_SERVICE_NAME')
    api.set_provider(FlagdProvider(host=os.environ.get('FLAGD_HOST', 'flagd'), port=os.environ.get('FLAGD_PORT', 8013)))
    api.add_hooks([TracingHook()])

    # Initialize Traces and Metrics
    tracer = trace.get_tracer_provider().get_tracer(service_name)
    meter = metrics.get_meter_provider().get_meter(service_name)
    rec_svc_metrics = init_metrics(meter)

    # Initialize Logs
    logger_provider = LoggerProvider(
        resource=Resource.create(
            {
                'service.name': service_name,
            }
        ),
    )
    set_logger_provider(logger_provider)
    log_exporter = OTLPLogExporter(insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

    # Attach OTLP handler to logger
    logger = logging.getLogger('main')
    logger.addHandler(handler)

    catalog_addr = must_map_env('PRODUCT_CATALOG_ADDR')
    pc_channel = grpc.intercept_channel(
        grpc.insecure_channel(catalog_addr),
        PeerServiceInterceptor("product-catalog"),
    )
    product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(pc_channel)

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add class to gRPC server
    service = RecommendationService()
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(service, server)

    # Start server
    port = must_map_env('RECOMMENDATION_PORT')
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info(f'Recommendation service started, listening on port {port}')
    server.wait_for_termination()
