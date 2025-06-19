import json

def estimate_tokens(messages):
    """Estimate token count (1 char ≈ 1 token)."""
    return sum(len(json.dumps(msg)) for msg in messages)