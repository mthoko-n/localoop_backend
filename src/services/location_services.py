from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from src.utils.db import fetch, insert, update
from src.utils.serialize_helper import serialize_doc
import uuid
import os
from dotenv import load_dotenv
import httpx

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# -------------------------
# USER LOCATIONS
# -------------------------

async def get_user_locations(user_id: str) -> Optional[List[dict]]:
    """Get all active locations for a user"""
    locations = await fetch("user_locations", {"user_id": user_id, "is_active": True})
    if not locations:
        return None

    formatted = []
    for loc in locations:
        loc = serialize_doc(loc)  # ✅ serialize ObjectId and datetime
        loc["id"] = loc.get("id") or loc.get("_id")
        formatted.append(loc)

    formatted.sort(key=lambda x: x["joined_at"], reverse=True)
    return formatted


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
        "last_activity": now,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }

    created_id = await insert("user_locations", new_location)
    if created_id:
        return serialize_doc(new_location)  # ✅ serialize before returning
    return None


async def remove_user_location(user_id: str, location_id: str) -> bool:
    """Soft delete location by setting is_active=False"""
    locations = await fetch("user_locations", {"user_id": user_id, "id": location_id, "is_active": True})
    if not locations:
        return False

    location_mongo_id = str(locations[0]["_id"])
    success = await update("user_locations", location_mongo_id, {"is_active": False, "updated_at": datetime.utcnow()})
    return success


async def get_location_status(location_id: str, user_id: str) -> Optional[dict]:
    """Get real-time status for a location"""
    locations = await fetch("user_locations", {"id": location_id, "user_id": user_id, "is_active": True})
    if not locations:
        return None

    location = serialize_doc(locations[0])  # ✅ serialize here
    participants = await fetch("chat_participants", {"location_id": location_id, "is_online": True})
    active_users = len(participants) if participants else 0

    return {
        "location_id": location_id,
        "unread_count": location.get("unread_count", 0),
        "status": location.get("status", "caught_up"),
        "last_activity": location.get("last_activity", location["joined_at"]),
        "active_users": active_users
    }


# -------------------------
# GOOGLE PLACES SEARCH
# -------------------------

async def search_locations(query: str, coordinates: dict = None, radius_km: int = 10) -> List[dict]:
    """Search locations using Google Places API"""
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_API_KEY}

    if coordinates:
        lat = coordinates.get("lat") or coordinates.get("latitude")
        lng = coordinates.get("lng") or coordinates.get("longitude")
        params["location"] = f"{lat},{lng}"
        params["radius"] = radius_km * 1000

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()

    results = []
    for place in data.get("results", []):
        loc_geometry = place.get("geometry", {}).get("location")
        if not loc_geometry:
            continue

        results.append({
            "id": place.get("place_id") or str(uuid.uuid4()),
            "name": place.get("name", "Unknown"),
            "address": place.get("formatted_address") or place.get("vicinity") or "",
            "coordinates": {
                "lat": loc_geometry.get("lat", 0.0),
                "lng": loc_geometry.get("lng", 0.0)
            },
            "status": "caught_up",
            "unread_count": 0,
            "joined_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "is_active": True,
            "type": (place.get("types") or ["unknown"])[0]
        })

    return results
