from typing import Optional, List, Dict
from bson import ObjectId
import logging
from src.database.mongo import (
    fetch as find, 
    insert as insert_one, 
    update as update_one, 
    delete as delete_one,
    get_db
)
from src.utils.logger import get_logger

logger = get_logger("DB Manager")

# --- Fetch documents ---
async def fetch(
    collection_name: str, 
    filter: Optional[dict] = None, 
    skip: int = 0,
    limit: int = 1000, 
    sort: Optional[List] = None,
    projection: Optional[dict] = None
) -> List[Dict]:
    filter = filter or {}
    logger.info(f"Fetching from collection '{collection_name}' with filter: {filter}, skip={skip}, limit={limit}")
    result = await find(
        collection_name,
        filter=filter,
        skip=skip,
        limit=limit,
        sort=sort,
        projection=projection
    )
    return result

# --- Insert a single document ---
async def insert(collection_name: str, data: dict) -> str:
    logger.info(f"Inserting into collection '{collection_name}': {data}")
    inserted_id = await insert_one(collection_name, data)
    return str(inserted_id)

# --- Update a single document by _id ---
async def update(collection_name: str, record_id: str, updated_data: dict) -> bool:
    logger.info(f"Updating record {record_id} in '{collection_name}' with {updated_data}")
    success = await update_one(collection_name, record_id, updated_data)
    return success

# --- Delete a single document by _id ---
async def delete(collection_name: str, record_id: str) -> bool:
    logger.info(f"Deleting record {record_id} from '{collection_name}'")
    success = await delete_one(collection_name, record_id)
    return success

# --- Update multiple documents ---
async def update_many(collection_name: str, filter: dict, updated_data: dict) -> int:
    db = await get_db()
    update_doc = {"$set": updated_data}
    result = await db[collection_name].update_many(filter, update_doc)
    logger.info(f"Updated {result.modified_count} documents in '{collection_name}' matching filter {filter}")
    return result.modified_count

# --- Delete multiple documents ---
async def delete_many(collection_name: str, filter: dict) -> int:
    db = await get_db()
    result = await db[collection_name].delete_many(filter)
    logger.info(f"Deleted {result.deleted_count} documents from '{collection_name}' matching filter {filter}")
    return result.deleted_count
