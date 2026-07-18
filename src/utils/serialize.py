import json


def serialize_row(d: dict) -> dict:
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            d[k] = json.dumps(v)
    return d
