import json
import hashlib

def hash_body(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()
    ).hexdigest()