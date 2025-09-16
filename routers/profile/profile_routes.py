from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from src.services.profile_services import (
    get_user_profile,
    update_user_profile,
    delete_user_account,
    change_user_password,
    get_user_stats,
    get_profile_user_locations
)
from src.utils.dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class UpdateProfileSchema(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "display_name": "John",
                "last_name": "Doe"
            }
        }

class ChangePasswordSchema(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "current_password123",
                "new_password": "new_secure_password123!"
            }
        }

class DeleteAccountSchema(BaseModel):
    password: str = Field(..., min_length=1)  # Require password confirmation

    class Config:
        json_schema_extra = {
            "example": {
                "password": "your_password123"
            }
        }

# -------------------------
# RESPONSE MODELS
# -------------------------
class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    last_name: str
    auth_provider: str
    updated_at: Optional[Any] = None

class MessageResponse(BaseModel):
    message: str

class StatsResponse(BaseModel):
    locations_joined: int
    member_since: str
    account_type: str
    total_locations: int

class LocationSummary(BaseModel):
    id: Optional[str]
    name: str
    last_activity: Optional[Any] = None
    unread_count: int = 0

class LocationStatsResponse(BaseModel):
    total_locations: int
    recent_locations: List[LocationSummary]
    most_active_location: Optional[LocationSummary] = None

# -------------------------
# ROUTES
# -------------------------
@router.get("/me", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user)):
    """Get current user's profile information."""
    profile = await get_user_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Profile not found"
        )
    return profile

@router.put("/update", response_model=MessageResponse)
async def update_profile(
    data: UpdateProfileSchema, 
    user_id: str = Depends(get_current_user)
):
    """Update user profile information."""
    # Only update fields that are provided (not None)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No fields to update"
        )
    
    success = await update_user_profile(user_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Profile update failed"
        )
    
    return MessageResponse(message="Profile updated successfully")

@router.put("/change-password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordSchema,
    user_id: str = Depends(get_current_user)
):
    """Change user password."""
    result = await change_user_password(
        user_id, 
        data.current_password, 
        data.new_password
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=result["error"]
        )
    
    return MessageResponse(message="Password changed successfully")

@router.delete("/delete-account", response_model=MessageResponse)
async def delete_account(
    data: DeleteAccountSchema,
    user_id: str = Depends(get_current_user)
):
    """Delete user account (requires password confirmation)."""
    result = await delete_user_account(user_id, data.password)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=result["error"]
        )
    
    return MessageResponse(message="Account deleted successfully")

@router.get("/stats", response_model=StatsResponse)
async def get_profile_stats(user_id: str = Depends(get_current_user)):
    """Get user statistics (locations joined, etc.)."""
    stats = await get_user_stats(user_id)
    
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User statistics not found"
        )
    
    return stats

@router.get("/locations", response_model=LocationStatsResponse)
async def get_profile_locations(user_id: str = Depends(get_current_user)):
    """Get detailed location statistics for user profile."""
    location_stats = await get_profile_user_locations(user_id)
    
    return location_stats