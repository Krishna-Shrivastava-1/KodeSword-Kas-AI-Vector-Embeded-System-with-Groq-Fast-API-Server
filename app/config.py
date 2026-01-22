from dotenv import load_dotenv
import os

load_dotenv()

SERVICE_NAME = "embedding-worker"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
