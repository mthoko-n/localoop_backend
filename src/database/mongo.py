import os
import logging
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.collection import Collection
from bson import ObjectId
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()

# ---------------------
# Logger setup
# ---------------------
logger = logging.getLogger("mongo")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# ---------------------
# MongoDB Context
# ---------------------
class DBContext:
    client: Optional[AsyncIOMotorClient] = None

db_context = DBContext()

# ---------------------
# Startup / Shutdown
# ---------------------
async def connect_to_mongo():
    """Connects to MongoDB."""
    uri = os.getenv("DATABASE_URL", "mongodb://localhost:27017/")
    db_context.client = AsyncIOMotorClient(uri)
    logger.info(f"Connected to MongoDB at {uri}")

async def close_mongo_connection():
    """Closes MongoDB connection."""
    if db_context.client:
        db_context.client.close()
        logger.info("MongoDB connection closed.")

# ---------------------
# Dependency
# ---------------------
async def get_db():
    """Returns the MongoDB database instance."""
    if not db_context.client:
        raise Exception("Database not initialized. Call connect_to_mongo() first.")
    db_name = os.getenv("DATABASE_NAME", "localoop_db")
    return db_context.client[db_name]

# ---------------------
# Helper functions
# ---------------------
async def fetch(
    collection_name: str, 
    filter: Optional[dict] = None, 
    skip: int = 0,
    limit: int = 1000, 
    sort: Optional[List] = None, 
    projection: Optional[dict] = None
) -> List[Dict]:
    filter = filter or {}
    db = await get_db()
    cursor = db[collection_name].find(filter, projection)

    if sort:
        cursor = cursor.sort(sort)
    if skip:
        cursor = cursor.skip(skip)
    if limit:
        cursor = cursor.limit(limit)

    return await cursor.to_list(length=None if limit == 0 else limit)


async def insert(collection_name: str, data: dict) -> str:
    db = await get_db()
    result = await db[collection_name].insert_one(data)
    logger.debug(f"Inserted document into '{collection_name}' with _id={result.inserted_id}")
    return str(result.inserted_id)

async def update(collection_name: str, record_id: str, updated_data: dict) -> bool:
    db = await get_db()
    filter_ = {"_id": ObjectId(record_id)}
    update_doc = {"$set": updated_data}
    result = await db[collection_name].update_one(filter_, update_doc)
    logger.debug(f"Updated {result.modified_count} document(s) in '{collection_name}' with _id={record_id}")
    return result.modified_count > 0

async def delete(collection_name: str, record_id: str) -> bool:
    db = await get_db()
    filter_ = {"_id": ObjectId(record_id)}
    result = await db[collection_name].delete_one(filter_)
    logger.debug(f"Deleted {result.deleted_count} document(s) from '{collection_name}' with _id={record_id}")
    return result.deleted_count > 0
