from pydantic import BaseModel

class BlogIndexJob(BaseModel):
    blog_id: int
    action: str  # "CREATE" | "UPDATE" | "DELETE"
