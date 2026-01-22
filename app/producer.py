import os
import pika
from dotenv import load_dotenv
import json
load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
QUEUE_NAME = "blog_embedding_jobs"

params = pika.URLParameters(RABBITMQ_URL)
connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.queue_declare(queue=QUEUE_NAME, durable=True)

def publish_blog_job(blog_id: str):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    message = json.dumps({
        "blog_id": blog_id
    })

    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=message,
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()