from elasticsearch import Elasticsearch

def get_elasticsearch_client(host: str, api_key: str) -> Elasticsearch:
    return Elasticsearch(
        hosts=[host],
        api_key=api_key,
    )
