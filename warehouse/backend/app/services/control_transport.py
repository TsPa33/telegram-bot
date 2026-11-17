"""Independent, staging-only signed read contract (no customer identity)."""
import hashlib
import hmac
import json
import os
import time

PATH = "/internal/control/warehouse-directory"

def signature(key, stamp, cursor, limit):
    message = json.dumps(["GET", PATH, "staging", stamp, cursor or "", limit], separators=(",", ":"))
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

def authorized(key, stamp, cursor, limit, proof):
    if len(key) < 32 or len(proof) != 64:
        return False
    try:
        timestamp = int(stamp)
    except (ValueError, TypeError):
        return False
    return abs(time.time() - timestamp) <= 60 and hmac.compare_digest(
        signature(key, stamp, cursor, limit), proof
    )
