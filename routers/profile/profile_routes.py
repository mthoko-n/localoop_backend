from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, Any
from src.services.profile_services import (
    get_user_profile,
    update_user_profile,
    delete_user_account,
    change_user_password,
    get_user_stats,
    reactivate_user_account  # If you implement this feature
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
    password: Optional[str] = Field(None)  # Optional for Google users

class ReactivateAccountSchema(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

# -------------------------
# RESPONSE MODELS
# -------------------------
class ProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    last_name: str
    hasPassword: bool
    # Optional: Add more fields if needed
    total_messages: Optional[int] = None
    last_activity: Optional[str] = None
    active_sessions: Optional[int] = None

class MessageResponse(BaseModel):
    message: str

class StatsResponse(BaseModel):
    id: str
    total_messages: int
    last_activity: Optional[str]
    active_sessions: int

# -------------------------
# ROUTES
# -------------------------
@router.get("/me", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user)):
    """Get current user's profile information."""
    # Fetch user profile
    profile = await get_user_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    # Ensure 'id' is a string for FastAPI validation
    profile["id"] = str(profile.get("id", user_id))

    # Ensure all required fields exist with defaults
    profile.setdefault("email", "")
    profile.setdefault("display_name", "")
    profile.setdefault("last_name", "")
    profile.setdefault("hasPassword", False)

    return ProfileResponse(**profile)

@router.get("/stats", response_model=StatsResponse)
async def get_user_statistics(user_id: str = Depends(get_current_user)):
    """Get user statistics including active sessions."""
    # Create user dict for get_user_stats function
    user_dict = {"_id": user_id}
    
    stats = await get_user_stats(user_dict)
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User statistics not found"
        )

    return StatsResponse(**stats)

@router.put("/update", response_model=MessageResponse)
async def update_profile(
    data: UpdateProfileSchema,
    user_id: str = Depends(get_current_user)
):
    """Update user profile information."""
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
    """
    Change user password. 
    WARNING: This will log out all devices for security.
    """
    result = await change_user_password(user_id, data.current_password, data.new_password)
    if not result["success"]:
        # Map specific error codes for better UX
        error_message = result["error"]
        if "Current password is incorrect" in error_message:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_message
            )
        elif "too weak" in error_message:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

    return MessageResponse(message="Password changed successfully. Please log in again on all devices.")

@router.delete("/delete-account", response_model=MessageResponse)
async def delete_account(
    data: DeleteAccountSchema,
    user_id: str = Depends(get_current_user)
):
    """
    Delete user account and all associated data.
    This will immediately log out all devices.
    """
    # Handle optional password for Google users
    password = data.password or ""
    
    result = await delete_user_account(user_id, password)
    if not result["success"]:
        error_message = result["error"]
        if "Password is incorrect" in error_message:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

    # Return the custom message from the service
    return MessageResponse(message=result.get("message", "Account deleted successfully"))

# -------------------------
# OPTIONAL: ACCOUNT REACTIVATION
# -------------------------
@router.post("/reactivate", response_model=MessageResponse)
async def reactivate_account(data: ReactivateAccountSchema):
    """
    Reactivate a soft-deleted account within the grace period.
    This endpoint doesn't require authentication since the account is deleted.
    """
    result = await reactivate_user_account(data.email, data.password)
    if not result["success"]:
        error_message = result["error"]
        if "Password is incorrect" in error_message:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_message
            )
        elif "too long ago" in error_message:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=error_message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

    return MessageResponse(message="Account reactivated successfully. Please log in again.")

# -------------------------
# ADMIN/DEBUG ENDPOINTS (Optional)
# -------------------------
@router.get("/active-sessions")
async def get_active_sessions(user_id: str = Depends(get_current_user)):
    """
    Get list of active sessions for the user.
    Useful for showing user where they're logged in.
    """
    from src.services.refresh_token_services import get_user_active_sessions
    
    try:
        sessions = await get_user_active_sessions(user_id)  # You'll need to implement this
        return {
            "active_sessions": len(sessions),
            "sessions": sessions
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch active sessions"
        )

@router.delete("/revoke-session/{jti}")
async def revoke_specific_session(
    jti: str, 
    user_id: str = Depends(get_current_user)
):
    """
    Revoke a specific session/device.
    Useful for "Log out from Device X" functionality.
    """
    from src.services.refresh_token_services import revoke_refresh_token
    
    # First verify this JTI belongs to the current user
    from src.services.refresh_token_services import get_refresh_token
    token_info = await get_refresh_token(jti)
    
    if not token_info or str(token_info["user_id"]) != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    success = await revoke_refresh_token(jti)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to revoke session"
        )
    
    return MessageResponse(message="Session revoked successfully")