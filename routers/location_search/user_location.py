from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from src.services.location_services import (
    get_user_locations,
    add_user_location,
    remove_user_location,
    get_location_status,
    search_locations
)
from src.utils.dependencies import get_current_user

router = APIRouter(prefix="/locations", tags=["User Locations"])

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class CoordinatesSchema(BaseModel):
    lat: float
    lng: float

class AddLocationSchema(BaseModel):
    location_name: str
    coordinates: CoordinatesSchema

class LocationSearchSchema(BaseModel):
    query: str
    coordinates: Optional[CoordinatesSchema] = None
    radius_km: Optional[int] = 10

# -------------------------
# RESPONSE SCHEMAS
# -------------------------
class LocationResponseSchema(BaseModel):
    id: str
    name: str
    unread_count: int
    status: str
    joined_at: str
    is_active: bool
    last_activity: str
    coordinates: CoordinatesSchema

class LocationStatusSchema(BaseModel):
    location_id: str
    unread_count: int
    status: str
    last_activity: str
    active_users: int

class SearchResultSchema(BaseModel):
    place_id: str
    name: str
    address: str
    coordinates: CoordinatesSchema
    type: str

# -------------------------
# ROUTES
# -------------------------

@router.get("/user", response_model=dict)
async def get_my_locations(user_id: str = Depends(get_current_user)):
    locations = await get_user_locations(user_id)
    return {
        "locations": locations or [],
        "total_count": len(locations or []),
        "max_allowed": 4
    }

@router.post("/user", response_model=dict)
async def add_location(
    data: AddLocationSchema,
    user_id: str = Depends(get_current_user)
):
    current_locations = await get_user_locations(user_id)
    if current_locations and len(current_locations) >= 4:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MAX_LOCATIONS_REACHED",
                "message": "You can only join up to 4 locations",
                "current_count": len(current_locations),
                "max_allowed": 4
            }
        )

    location = await add_user_location(
        user_id=user_id,
        location_name=data.location_name,
        coordinates={"lat": data.coordinates.lat, "lng": data.coordinates.lng}
    )
    if not location:
        raise HTTPException(status_code=400, detail="Failed to add location")

    return {"message": "Location added successfully", "location": location}

@router.delete("/user/{location_id}", response_model=dict)
async def remove_location(location_id: str, user_id: str = Depends(get_current_user)):
    success = await remove_user_location(user_id, location_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Location not found or removal failed"
        )
    return {"message": "Location removed successfully"}

@router.get("/{location_id}/status", response_model=LocationStatusSchema)
async def get_location_status_info(location_id: str, user_id: str = Depends(get_current_user)):
    status = await get_location_status(location_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Location status not found")
    return status

@router.post("/search", response_model=dict)
async def search_available_locations(data: LocationSearchSchema):
    raw_results = await search_locations(
        query=data.query,
        coordinates={
            "lat": data.coordinates.lat,
            "lng": data.coordinates.lng
        } if data.coordinates else None,
        radius_km=data.radius_km
    )

    results: List[SearchResultSchema] = []
    for place in raw_results:
        coords = place.get("coordinates", {})
        lat = coords.get("lat")
        lng = coords.get("lng")
        if lat is None or lng is None:
            continue

        results.append(SearchResultSchema(
            place_id=place.get("id") or "",
            name=place.get("name") or "Unknown",
            address=place.get("address") or "",
            coordinates=CoordinatesSchema(lat=lat, lng=lng),
            type=place.get("type") or "unknown"
        ))

    return {"suggestions": results, "count": len(results)}
