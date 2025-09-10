from typing import Optional, List, Dict, Any
from bson import ObjectId
import logging
from src.database.mongo import find, insert_one, update_one, delete_one
from src.utils.logger import get_logger

logger = get_logger("DB Manager", log_to_std_out=True)

# --- Fetch documents ---
async def fetch(collection_name: str, filter: Optional[dict] = None, limit: int = 1000) -> List[Dict]:
    filter = filter or {}
    logger.info(f"Fetching from collection '{collection_name}' with filter: {filter}")
    result = await find(filter, collection_name=collection_name, limit=limit)
    return result

# --- Insert a single document ---
async def insert(collection_name: str, data: dict) -> str:
    logger.info(f"Inserting into collection '{collection_name}': {data}")
    inserted_id = await insert_one(data, collection_name=collection_name)
    return str(inserted_id)

# --- Update a document by _id ---
async def update(collection_name: str, record_id: str, updated_data: dict) -> bool:
    filter_ = {"_id": ObjectId(record_id)}
    update_doc = {"$set": updated_data}
    logger.info(f"Updating record {record_id} in '{collection_name}' with {updated_data}")
    result = await update_one(filter_, update_doc, collection_name=collection_name)
    return result.modified_count > 0

# --- Delete a document by _id ---
async def delete(collection_name: str, record_id: str) -> bool:
    filter_ = {"_id": ObjectId(record_id)}
    logger.info(f"Deleting record {record_id} from '{collection_name}'")
    success = await delete_one(filter_, collection_name=collection_name)
    return success
