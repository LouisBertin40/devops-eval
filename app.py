import os
import time

import redis
from flask import Flask, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

app = Flask(__name__)
REQUESTS = Counter("http_requests_total", "Nombre de requêtes HTTP", ["endpoint", "code"])
LATENCY = Histogram("http_request_duration_seconds", "Durée des requêtes HTTP", ["endpoint"])
VERSION = Gauge("app_version_info", "Version deployee (SHA du commit)", ["version"])
VERSION.labels(version=os.environ.get("GIT_SHA", "dev")).set(1)


@app.before_request
def start_timer():
    g.start = time.perf_counter()


@app.after_request
def record_metrics(response):
    if request.path != "/metrics":
        endpoint = request.url_rule.rule if request.url_rule else "unknown"
        REQUESTS.labels(endpoint, str(response.status_code)).inc()
        LATENCY.labels(endpoint).observe(time.perf_counter() - g.start)
    return response


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


def get_redis():
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", 6379))
    return redis.Redis(host=host, port=port, socket_connect_timeout=2)


@app.route("/health")
def health():
    try:
        get_redis().ping()
    except redis.RedisError:
        return jsonify(status="error"), 503
    return jsonify(status="ok"), 200


@app.route("/visits")
def visits():
    count = get_redis().incr("visits")
    return jsonify(visits=count), 200
