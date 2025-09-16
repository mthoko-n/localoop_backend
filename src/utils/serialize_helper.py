from bson import ObjectId
from datetime import datetime
from typing import Any

def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON/Pydantic-safe dict."""
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    # Optionally remove internal MongoDB _id if you want
    serialized.pop("_id", None) 
    return serialized
