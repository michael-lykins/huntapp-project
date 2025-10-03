from app.es import get_search_client

INDEX_PREFIX = "hunt-images-"
TEMPLATE_NAME = "hunt-images-template"

MAPPINGS = {
  "dynamic": True,
  "properties": {
    "@timestamp": {"type": "date"},
    "camera": {
      "properties": {
        "id": {"type": "keyword"},
        "location": {"type": "geo_point"},
        "heading": {
          "properties": {
            "deg": {"type": "float"},
            "cardinal_16": {"type": "keyword"},
          }
        },
      }
    },
    "labels": {
      "properties": {
        "user": {"type": "keyword"}
      }
    },
    "media": {
      "properties": {
        "url": {"type": "keyword"},
        "size_bytes": {"type": "long"}
      }
    },
    "context": {"dynamic": True}
  }
}

SETTINGS = {
  "number_of_shards": 1,
  "number_of_replicas": 0
}

def ensure_template():
    es = get_search_client()
    exists = es.indices.exists_index_template(name=TEMPLATE_NAME)
    if not exists:
        es.indices.put_index_template(
            name=TEMPLATE_NAME,
            body={
              "index_patterns": [f"{INDEX_PREFIX}*"],
              "template": {"settings": SETTINGS, "mappings": MAPPINGS},
              "priority": 100
            }
        )
