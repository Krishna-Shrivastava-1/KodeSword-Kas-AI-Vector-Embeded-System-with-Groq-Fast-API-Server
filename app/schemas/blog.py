from pydantic import BaseModel

class BlogIndexRequest(BaseModel):
    blog_id: str