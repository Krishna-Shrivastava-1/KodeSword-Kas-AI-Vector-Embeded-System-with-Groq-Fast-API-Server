import os
import pika
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from app.vector.qdrant import init_collection, store_embedding, delete_embeddings_by_blog_id

import uuid
from app.vector.qdrant import init_collection, store_embedding

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")



BLOG_API_BASE = "https://kodesword.vercel.app/api/post/getpostbyid"

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL not found in .env")

QUEUE_NAME = "blog_embedding_jobs"

params = pika.URLParameters(RABBITMQ_URL)
connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.queue_declare(queue=QUEUE_NAME, durable=True)

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator=" ")

    # Normalize whitespace
    text = " ".join(text.split())

    return text

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def fetch_blog_by_id(blog_id: str) -> dict:
    url = f"{BLOG_API_BASE}/{blog_id}"

    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch blog {blog_id}")

    data = response.json()

    if "postbyid" not in data:
        raise RuntimeError("Invalid blog API response")

    return data["postbyid"]

def create_embedding(text: str) -> list[float]:
    vector = embedding_model.encode(text)
    return vector.tolist()

def process_blog_job(ch, method, properties, body):
    blog_id = body.decode()
    print(f"[WORKER] Received blog_id: {blog_id}")

    try:
        blog = fetch_blog_by_id(blog_id)

        title = blog.get("title", "")
        subtitle = blog.get("subtitle", "")
        tags = blog.get("tag", "")
        content_html = blog.get("content", "")

        # 1️⃣ Clean HTML
        content_text = html_to_text(content_html)

        # 2️⃣ Combine metadata + content
        full_text = f"{title}\n{subtitle}\n{content_text}"

        # 3️⃣ Chunk text
        chunks = chunk_text(full_text)

        print(f"[WORKER] Total chunks: {len(chunks)}")
        delete_embeddings_by_blog_id(blog_id)
        # 4️⃣ Create embedding per chunk & store
        for idx, chunk in enumerate(chunks):
            if len(chunk.strip()) < 50:
                continue
            embedding = create_embedding(chunk)

            store_embedding(
                vector_id=str(uuid.uuid4()),
                embedding=embedding,
                payload={
                    "blog_id": blog_id,
                    "chunk_index": idx,
                    "text": chunk,
                    "title": title,
                    "tags": tags
                }
            )

        print("[WORKER] All embeddings stored successfully")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[ERROR] blog_id={blog_id} → {e}")






def start_worker():
    init_collection()
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=process_blog_job
    )

    print("[WORKER] Waiting for messages...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()



