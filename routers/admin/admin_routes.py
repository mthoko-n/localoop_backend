from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from src.services.admin_services import (
    check_user_admin_status,
    get_all_users,
    ban_user,
    unban_user,
    force_logout_user,
    force_logout_all_users,
    get_system_metrics,
    make_user_admin,
    remove_admin_status,
    get_admin_activity_log,
    get_conversations_by_location,
    delete_conversation_admin,
    delete_message_admin,
    get_flagged_content,
    get_all_locations,
    get_location_analytics,
    moderate_location
)
from src.utils.dependencies import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])

# -------------------------
# ADMIN MIDDLEWARE
# -------------------------
async def require_admin(user_id: str = Depends(get_current_user)) -> str:
    """Dependency to ensure user is an admin."""
    is_admin = await check_user_admin_status(user_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user_id

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class BanUserSchema(BaseModel):
    user_id: str = Field(..., description="User ID to ban")
    reason: Optional[str] = Field(None, description="Reason for ban")

class UnbanUserSchema(BaseModel):
    user_id: str = Field(..., description="User ID to unban")

class PromoteUserSchema(BaseModel):
    user_id: str = Field(..., description="User ID to promote to admin")

class DemoteUserSchema(BaseModel):
    user_id: str = Field(..., description="User ID to remove admin status from")

class ForceLogoutSchema(BaseModel):
    user_id: str = Field(..., description="User ID to force logout")

class DeleteConversationSchema(BaseModel):
    conversation_id: str = Field(..., description="Conversation ID to delete")
    reason: Optional[str] = Field(None, description="Reason for deletion")

class DeleteMessageSchema(BaseModel):
    message_id: str = Field(..., description="Message ID to delete")
    reason: Optional[str] = Field(None, description="Reason for deletion")

class ModerateLocationSchema(BaseModel):
    location_id: str = Field(..., description="Location ID to moderate")
    action: str = Field(..., description="Action to take: disable_all_conversations, remove_all_users")
    reason: Optional[str] = Field(None, description="Reason for moderation")

# -------------------------
# RESPONSE MODELS
# -------------------------
class MessageResponse(BaseModel):
    message: str

class AdminStatusResponse(BaseModel):
    is_admin: bool

class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    last_name: str
    is_active: bool
    is_admin: Optional[bool] = False
    deleted_at: Optional[str] = None
    deletion_reason: Optional[str] = None

class UsersListResponse(BaseModel):
    success: bool
    users: List[UserResponse]
    pagination: dict

class SystemMetricsResponse(BaseModel):
    success: bool
    metrics: dict

# -------------------------
# ROUTES
# -------------------------

@router.get("/check-status", response_model=AdminStatusResponse)
async def check_admin_status(user_id: str = Depends(get_current_user)):
    """Check if current user is an admin."""
    is_admin = await check_user_admin_status(user_id)
    return AdminStatusResponse(is_admin=is_admin)

@router.get("/users", response_model=UsersListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin_id: str = Depends(require_admin)
):
    """Get paginated list of all users. Admin only."""
    result = await get_all_users(admin_id, page, limit)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return UsersListResponse(**result)

@router.post("/ban-user", response_model=MessageResponse)
async def ban_user_endpoint(
    data: BanUserSchema,
    admin_id: str = Depends(require_admin)
):
    """Ban a user. Admin only."""
    result = await ban_user(admin_id, data.user_id, data.reason)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="User banned successfully")

@router.post("/unban-user", response_model=MessageResponse)
async def unban_user_endpoint(
    data: UnbanUserSchema,
    admin_id: str = Depends(require_admin)
):
    """Unban a user. Admin only."""
    result = await unban_user(admin_id, data.user_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="User unbanned successfully")

@router.post("/promote-user", response_model=MessageResponse)
async def promote_user(
    data: PromoteUserSchema,
    admin_id: str = Depends(require_admin)
):
    """Promote a user to admin. Admin only."""
    result = await make_user_admin(admin_id, data.user_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="User promoted to admin successfully")

@router.post("/demote-user", response_model=MessageResponse)
async def demote_user(
    data: DemoteUserSchema,
    admin_id: str = Depends(require_admin)
):
    """Remove admin status from a user. Admin only."""
    result = await remove_admin_status(admin_id, data.user_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="Admin status removed successfully")

@router.post("/force-logout", response_model=MessageResponse)
async def force_logout(
    data: ForceLogoutSchema,
    admin_id: str = Depends(require_admin)
):
    """Force logout a specific user. Admin only."""
    result = await force_logout_user(admin_id, data.user_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="User logged out successfully")

@router.post("/force-logout-all", response_model=MessageResponse)
async def force_logout_all(admin_id: str = Depends(require_admin)):
    """Force logout ALL users (nuclear option). Admin only."""
    result = await force_logout_all_users(admin_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message=result["message"])

@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_metrics(admin_id: str = Depends(require_admin)):
    """Get system-wide metrics. Admin only."""
    result = await get_system_metrics(admin_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return SystemMetricsResponse(**result)

@router.get("/activity-log")
async def get_activity_log(
    limit: int = Query(100, ge=1, le=500),
    admin_id: str = Depends(require_admin)
):
    """Get admin activity log. Admin only."""
    result = await get_admin_activity_log(admin_id, limit)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result

# -------------------------
# LOCATION MANAGEMENT ROUTES
# -------------------------

@router.get("/locations")
async def get_all_locations_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin_id: str = Depends(require_admin)
):
    """Get all user locations across the system. Admin only."""
    result = await get_all_locations(admin_id, page, limit)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result

@router.get("/location-analytics/{location_id}")
async def get_location_analytics_endpoint(
    location_id: str,
    admin_id: str = Depends(require_admin)
):
    """Get detailed analytics for a specific location. Admin only."""
    result = await get_location_analytics(admin_id, location_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result

@router.post("/moderate-location", response_model=MessageResponse)
async def moderate_location_endpoint(
    data: ModerateLocationSchema,
    admin_id: str = Depends(require_admin)
):
    """Moderate a location (disable conversations, remove users). Admin only."""
    result = await moderate_location(admin_id, data.location_id, data.action, data.reason)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message=result["message"])

# -------------------------
# CONTENT MODERATION ROUTES
# -------------------------

@router.get("/conversations/{location_id}")
async def get_location_conversations(
    location_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin_id: str = Depends(require_admin)
):
    """Get conversations for a location. Admin only."""
    result = await get_conversations_by_location(admin_id, location_id, page, limit)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result

@router.delete("/conversation", response_model=MessageResponse)
async def delete_conversation(
    data: DeleteConversationSchema,
    admin_id: str = Depends(require_admin)
):
    """Delete a conversation. Admin only."""
    result = await delete_conversation_admin(admin_id, data.conversation_id, data.reason)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="Conversation deleted successfully")

@router.delete("/message", response_model=MessageResponse)
async def delete_message(
    data: DeleteMessageSchema,
    admin_id: str = Depends(require_admin)
):
    """Delete a message. Admin only."""
    result = await delete_message_admin(admin_id, data.message_id, data.reason)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return MessageResponse(message="Message deleted successfully")

@router.get("/flagged-content")
async def get_flagged_content_endpoint(admin_id: str = Depends(require_admin)):
    """Get content that might need moderation. Admin only."""
    result = await get_flagged_content(admin_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result