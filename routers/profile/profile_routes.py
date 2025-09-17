from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, Any
from src.services.profile_services import (
    get_user_profile,
    update_user_profile,
    delete_user_account,
    change_user_password,
    get_user_stats
)
from src.utils.dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["Profile"])

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class UpdateProfileSchema(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)

class ChangePasswordSchema(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

class DeleteAccountSchema(BaseModel):
    password: str = Field(..., min_length=1)

# -------------------------
# RESPONSE MODELS
# -------------------------
class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    last_name: str
    member_since: str  

class MessageResponse(BaseModel):
    message: str


# -------------------------
# ROUTES
# -------------------------
@router.get("/me", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user)):
    # Fetch user profile
    profile = await get_user_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    # Ensure 'id' is a string for FastAPI validation
    profile_id = profile.get("id") or str(user_id)
    profile["id"] = str(profile_id)

    # Fetch user stats safely
    stats = await get_user_stats(user_id) or {}
    member_since = stats.get("member_since", "Unknown")
    profile["member_since"] = member_since

    # Ensure all fields exist to match ProfileResponse
    profile.setdefault("email", "")
    profile.setdefault("display_name", "")
    profile.setdefault("last_name", "")

    return profile


@router.put("/update", response_model=MessageResponse)
async def update_profile(
    data: UpdateProfileSchema, 
    user_id: str = Depends(get_current_user)
):
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
    result = await change_user_password(user_id, data.current_password, data.new_password)
    
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
    result = await delete_user_account(user_id, data.password)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=result["error"]
        )
    
    return MessageResponse(message="Account deleted successfully")


