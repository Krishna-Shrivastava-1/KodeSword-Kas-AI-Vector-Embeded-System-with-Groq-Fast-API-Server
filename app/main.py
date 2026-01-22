# from fastapi import FastAPI, HTTPException
# from sentence_transformers import SentenceTransformer

# from app.producer import publish_blog_job
# from app.vector.qdrant import (
#     delete_embeddings_by_blog_id,
#     search_similar_embeddings
# )
# from app.schemas.query import SearchQuery

# app = FastAPI(title="Embedding & Retrieval Service")

# embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# @app.get("/health")
# def health_check():
#     return {"status": "ok"}


# # 🔹 Index blog (already working)
# @app.post("/index-blog/{blog_id}")
# def index_blog(blog_id: str):
#     publish_blog_job(blog_id)
#     return {
#         "message": "Blog indexing job queued",
#         "blog_id": blog_id
#     }


# # 🔹 Delete embeddings when blog is deleted
# @app.delete("/delete-blog/{blog_id}")
# def delete_blog_embeddings(blog_id: str):
#     try:
#         delete_embeddings_by_blog_id(blog_id)
#         return {
#             "message": "Blog embeddings deleted successfully",
#             "blog_id": blog_id
#         }
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Failed to delete embeddings: {str(e)}"
#         )


# # 🔹 USER QUERY → VECTOR SEARCH
# @app.post("/search")
# def semantic_search(payload: SearchQuery):
#     try:
#         # 1️⃣ Convert user query → embedding
#         query_vector = embedding_model.encode(payload.query).tolist()

#         # 2️⃣ Search Qdrant
#         results = search_similar_embeddings(
#             query_vector=query_vector,
#             top_k=payload.top_k
#         )

#         return {
#             "query": payload.query,
#             "results": results
#         }

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Search failed: {str(e)}"
#         )



from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer

from app.vector.qdrant import (
    search_similar_embeddings,
    delete_embeddings_by_blog_id
)
from app.llm.groq_llm import call_llm
from app.schemas.query import SearchQuery
from app.schemas.blog import BlogIndexRequest
from app.producer import publish_blog_job
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
load_dotenv()
# Allowed frontend origins
ALLOWED_ORIGINS = [
    "http://localhost:3000",     # React local
    "http://localhost:5173",     # Vite
    "http://127.0.0.1:3000",
    os.getenv("Base_Url")  # production frontend
]

# -------------------------------------------------
# App Config
# -------------------------------------------------

app = FastAPI(title="Kodesword RAG Blog API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # use ["*"] ONLY if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

ASSISTANT_NAME = "Kas"
ASSISTANT_IDENTITY = (
    "I am Kas, an AI assistant developed by Kodesword. "
    "I help users understand and explore blog content."
)

# -------------------------------------------------
# Prompt Builder
# -------------------------------------------------

def build_prompt(user_query: str, results: list[dict]) -> str:
    chunks = [r["text"] for r in results]
    context = "\n\n".join(chunks)

    return f"""
You are {ASSISTANT_NAME}, an AI assistant developed by Kodesword.

Rules:
- Answer ONLY using the provided context
- Be clear and concise
- If the answer is not present, say:
  "I don't know based on the blog."

Context:
{context}

Question:
{user_query}

Answer:
""".strip()

# -------------------------------------------------
# Query Classification
# -------------------------------------------------

SMALL_TALK = [
    "hi", "hello", "hey", "how are you",
    "good morning", "good evening"
]

IDENTITY_QUESTIONS = [
    "who are you", "what is your name", "tell me about yourself"
]

GENERAL_QUESTIONS = [
    "what can you do", "how can you help", "help me"
]


def normalize(text: str) -> str:
    return text.lower().strip()


def is_match(query: str, phrases: list[str]) -> bool:
    q = normalize(query)
    return any(q == p or q.startswith(p) for p in phrases)

# -------------------------------------------------
# Health Check
# -------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# Worker Trigger Endpoints
# -------------------------------------------------

@app.post("/index-blog")
def index_blog(payload: BlogIndexRequest):
    """
    Called when a blog is CREATED
    """
    try:
        publish_blog_job(payload.blog_id)
        return {
            "message": "Blog indexing job queued",
            "blog_id": payload.blog_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reindex-blog")
def reindex_blog(payload: BlogIndexRequest):
    """
    Called when a blog is UPDATED
    """
    try:
        publish_blog_job(payload.blog_id)
        return {
            "message": "Blog re-indexing job queued",
            "blog_id": payload.blog_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------
# Chat Endpoint (RAG)
# -------------------------------------------------

@app.post("/chat")
def chat(payload: SearchQuery):
    try:
        query = payload.query.strip()

        # 1️⃣ Identity
        if is_match(query, IDENTITY_QUESTIONS):
            return {"answer": ASSISTANT_IDENTITY}

        # 2️⃣ Small talk
        if is_match(query, SMALL_TALK):
            return {
                "answer": f"Hi! I'm {ASSISTANT_NAME} 🙂 How can I help you with the blogs?"
            }

        # 3️⃣ General help
        if is_match(query, GENERAL_QUESTIONS):
            return {
                "answer": (
                    "I answer questions using the blog content available on this platform. "
                    "Ask me anything related to the blogs."
                )
            }

        # 4️⃣ RAG
        query_vector = embedding_model.encode(query).tolist()

        results = search_similar_embeddings(
            query_vector=query_vector,
            top_k=payload.top_k
        )

        if not results:
            return {
                "answer": "I couldn't find relevant information in the blogs."
            }

        prompt = build_prompt(query, results)
        answer = call_llm(prompt)

        return {
            "question": query,
            "answer": answer,
            "sources": [
                {
                    "blog_id": r["blog_id"],
                    "title": r["title"],
                    "chunk_index": r["chunk_index"]
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------
# Delete Blog Embeddings
# -------------------------------------------------

@app.delete("/delete-blog/{blog_id}")
def delete_blog(blog_id: str):
    try:
        delete_embeddings_by_blog_id(blog_id)
        return {
            "message": "Blog embeddings deleted",
            "blog_id": blog_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
