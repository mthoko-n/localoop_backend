from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
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
    latitude: float
    longitude: float

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
    status: str  # "new_messages" or "caught_up"
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
    id: str
    name: str
    display_name: str
    coordinates: CoordinatesSchema
    type: str  # "neighborhood", "mall", "area"

# -------------------------
# ROUTES
# -------------------------
@router.get("/user")
async def get_my_locations(user_id: str = Depends(get_current_user)):
    """Get all locations for the current user"""
    locations = await get_user_locations(user_id)
    if locations is None:
        raise HTTPException(status_code=404, detail="No locations found")
    
    return {
        "locations": locations,
        "total_count": len(locations),
        "max_allowed": 4
    }

@router.post("/user")
async def add_location(
    data: AddLocationSchema, 
    user_id: str = Depends(get_current_user)
):
    """Add a new location for the current user"""
    # Check if user already has 4 locations
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
        coordinates=data.coordinates.model_dump()
    )
    
    if not location:
        raise HTTPException(status_code=400, detail="Failed to add location")
    
    return {
        "message": "Location added successfully",
        "location": location
    }

@router.delete("/user/{location_id}")
async def remove_location(
    location_id: str,
    user_id: str = Depends(get_current_user)
):
    """Remove a location from user's list"""
    success = await remove_user_location(user_id, location_id)
    if not success:
        raise HTTPException(
            status_code=404, 
            detail="Location not found or removal failed"
        )
    
    return {"message": "Location removed successfully"}

@router.get("/{location_id}/status")
async def get_location_status_info(
    location_id: str,
    user_id: str = Depends(get_current_user)
):
    """Get real-time status for a specific location"""
    status = await get_location_status(location_id, user_id)
    if not status:
        raise HTTPException(status_code=404, detail="Location status not found")
    
    return status

@router.post("/search")
async def search_available_locations(data: LocationSearchSchema):
    """Search for available locations to join"""
    try:
        results = await search_locations(
            query=data.query,
            coordinates=data.coordinates.model_dump() if data.coordinates else None,
            radius_km=data.radius_km
        )
        
        return {
            "suggestions": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Search failed: {str(e)}")