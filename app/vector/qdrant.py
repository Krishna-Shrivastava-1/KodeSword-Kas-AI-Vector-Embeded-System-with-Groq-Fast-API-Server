import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams,PayloadSchemaType
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL or QDRANT_API_KEY missing")

COLLECTION_NAME = "blog_embeddings"

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

def init_collection():
    collections = client.get_collections().collections
    names = [c.name for c in collections]

    if COLLECTION_NAME not in names:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE
            )
        )
        print("✅ Qdrant Cloud collection created")

    # ✅ ALWAYS create payload index (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="blog_id",
        field_schema=PayloadSchemaType.KEYWORD
    )

    print("✅ Payload index ensured for blog_id")


def store_embedding(vector_id: str, embedding: list, payload: dict):
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            {
                "id": vector_id,
                "vector": embedding,
                "payload": payload
            }
        ]
    )




def delete_embeddings_by_blog_id(blog_id: str):
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="blog_id",
                    match=MatchValue(value=blog_id)
                )
            ]
        )
    )
    print(f"🗑️ Deleted old embeddings for blog_id={blog_id}")


def search_similar_embeddings(query_vector: list, top_k: int = 5):
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[],
        query=query_vector,
        limit=top_k,
        with_payload=True
    ).points

    return [
        {
            "score": hit.score,
            "blog_id": hit.payload.get("blog_id"),
            "chunk_index": hit.payload.get("chunk_index"),
            "text": hit.payload.get("text"),
            "title": hit.payload.get("title"),
            "tags": hit.payload.get("tags"),
        }
        for hit in results
    ]
