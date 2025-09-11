from typing import Optional
from datetime import datetime
from bson import ObjectId
from src.utils.db import fetch, insert, update
import uuid

async def get_user_locations(user_id: str) -> Optional[list]:
    """Get all active locations for a user"""
    locations = await fetch("user_locations", {
        "user_id": user_id,
        "is_active": True
    })
    
    if not locations:
        return None
    
    # Convert ObjectId to string and format response
    formatted_locations = []
    for loc in locations:
        formatted_locations.append({
            "id": loc.get("id", str(loc["_id"])),
            "name": loc["name"],
            "unread_count": loc.get("unread_count", 0),
            "status": loc.get("status", "caught_up"),
            "joined_at": loc["joined_at"].isoformat(),
            "is_active": loc["is_active"],
            "last_activity": loc.get("last_activity", loc["joined_at"]).isoformat(),
            "coordinates": loc["coordinates"]
        })
    
    # Sort by joined_at descending
    formatted_locations.sort(key=lambda x: x["joined_at"], reverse=True)
    return formatted_locations

async def add_user_location(user_id: str, location_name: str, coordinates: dict) -> Optional[dict]:
    """Add a new location for the user"""
    location_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    new_location = {
        "id": location_id,
        "user_id": user_id,
        "name": location_name,
        "coordinates": coordinates,
        "unread_count": 0,
        "status": "caught_up",
        "joined_at": now,
        "is_active": True,
        "last_activity": now,
        "created_at": now,
        "updated_at": now
    }
    
    created_id = await insert("user_locations", new_location)
    
    if created_id:
        # Return the created location with formatted dates
        new_location["joined_at"] = new_location["joined_at"].isoformat()
        new_location["last_activity"] = new_location["last_activity"].isoformat()
        new_location["created_at"] = new_location["created_at"].isoformat()
        new_location["updated_at"] = new_location["updated_at"].isoformat()
        return new_location
    
    return None

async def remove_user_location(user_id: str, location_id: str) -> bool:
    """Remove a location (soft delete by setting is_active to False)"""
    # First check if location exists for this user
    locations = await fetch("user_locations", {
        "user_id": user_id, 
        "id": location_id,
        "is_active": True
    })
    
    if not locations:
        return False
    
    # Get the MongoDB _id for the update
    location = locations[0]
    location_mongo_id = str(location["_id"])
    
    success = await update("user_locations", location_mongo_id, {
        "is_active": False,
        "updated_at": datetime.utcnow()
    })
    
    return success

async def get_location_status(location_id: str, user_id: str) -> Optional[dict]:
    """Get real-time status for a location"""
    # Get location info
    locations = await fetch("user_locations", {
        "id": location_id,
        "user_id": user_id,
        "is_active": True
    })
    
    if not locations:
        return None
    
    location = locations[0]
    
    # Get active users count from chat_participants collection
    participants = await fetch("chat_participants", {
        "location_id": location_id,
        "is_online": True
    })
    active_users = len(participants) if participants else 0
    
    return {
        "location_id": location_id,
        "unread_count": location.get("unread_count", 0),
        "status": location.get("status", "caught_up"),
        "last_activity": location.get("last_activity", location["joined_at"]).isoformat(),
        "active_users": active_users
    }

async def search_locations(query: str, coordinates: dict = None, radius_km: int = 10) -> list:
    """Search for available locations (you can integrate with Google Places API or your own database)"""
    # This is a simple implementation - you can enhance with real location search
    # You could also search your existing locations database here
    
    # For now, return some mock results based on the query
    mock_results = [
        {
            "id": f"place_{query.lower().replace(' ', '_')}",
            "name": f"{query} Area",
            "display_name": f"{query}, Johannesburg",
            "coordinates": coordinates or {"latitude": -26.1496, "longitude": 28.0406},
            "type": "neighborhood"
        }
    ]
    
    return mock_results

# -------------------------
# ADDITIONAL HELPER FUNCTIONS
# -------------------------

async def get_location_by_id(location_id: str) -> Optional[dict]:
    """Get a location by its ID"""
    locations = await fetch("user_locations", {"id": location_id})
    return locations[0] if locations else None

async def update_location_activity(location_id: str, user_id: str) -> bool:
    """Update last activity timestamp for a location"""
    locations = await fetch("user_locations", {
        "id": location_id,
        "user_id": user_id,
        "is_active": True
    })
    
    if not locations:
        return False
    
    location = locations[0]
    location_mongo_id = str(location["_id"])
    
    success = await update("user_locations", location_mongo_id, {
        "last_activity": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    return success

async def update_unread_count(location_id: str, user_id: str, unread_count: int, status: str = None) -> bool:
    """Update unread count and status for a location"""
    locations = await fetch("user_locations", {
        "id": location_id,
        "user_id": user_id,
        "is_active": True
    })
    
    if not locations:
        return False
    
    location = locations[0]
    location_mongo_id = str(location["_id"])
    
    update_data = {
        "unread_count": unread_count,
        "updated_at": datetime.utcnow()
    }
    
    if status:
        update_data["status"] = status
    
    success = await update("user_locations", location_mongo_id, update_data)
    return success