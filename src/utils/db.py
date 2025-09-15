from typing import Optional, List, Dict
from bson import ObjectId
import logging
from src.database.mongo import fetch as find, insert as insert_one, update as update_one, delete as delete_one
from src.utils.logger import get_logger

logger = get_logger("DB Manager")

# --- Fetch documents ---
# services/db.py
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
    inserted_id = await insert_one(collection_name, data)  # use insert as insert_one
    return str(inserted_id)

# --- Update a document by _id ---
async def update(collection_name: str, record_id: str, updated_data: dict) -> bool:
    filter_ = {"_id": ObjectId(record_id)}
    update_doc = {"$set": updated_data}
    logger.info(f"Updating record {record_id} in '{collection_name}' with {updated_data}")
    success = await update_one(collection_name, record_id, updated_data)  # use update as update_one
    return success

# --- Delete a document by _id ---
async def delete(collection_name: str, record_id: str) -> bool:
    logger.info(f"Deleting record {record_id} from '{collection_name}'")
    success = await delete_one(collection_name, record_id)  # use delete as delete_one
    return success
