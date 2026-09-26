import os

import redis
from flask import Flask, jsonify

app = Flask(__name__)


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
