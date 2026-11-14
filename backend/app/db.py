"""
backend/app/db.py
Database connection handles for MongoDB Atlas (txn_validation).
Supports both asynchronous (AsyncMongoClient) and synchronous (MongoClient) operations.
"""

import os
from pymongo import MongoClient, AsyncMongoClient

def get_mongodb_uri() -> str:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        # Check .local or .env
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".local")
        if os.path.exists(local_path):
            with open(local_path) as f:
                uri = f.read().strip()
    return uri or "mongodb://localhost:27017"

DB_NAME = os.getenv("DB_NAME", "txn_validation")

def get_sync_db():
    client = MongoClient(get_mongodb_uri())
    return client[DB_NAME]

def get_async_db():
    client = AsyncMongoClient(get_mongodb_uri())
    return client[DB_NAME]
