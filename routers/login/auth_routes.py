from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from src.services.auth_services import (
    register_user,
    authenticate_user,
    get_user_by_email,
    update_display_name,
    authenticate_google_user
)
from src.services.refresh_token_services import (
    refresh_access_token,
    revoke_refresh_token,
    revoke_all_user_tokens
)
from src.utils.dependencies import get_current_user
from src.utils.auth_utils import decode_refresh_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class RegisterSchema(BaseModel):
    email: str
    password: str
    display_name: str
    last_name: str

class LoginSchema(BaseModel):
    email: str
    password: str

class UpdateDisplayNameSchema(BaseModel):
    display_name: str

class GoogleLoginSchema(BaseModel):
    id_token: str

class RefreshTokenSchema(BaseModel):
    refresh_token: str

# -------------------------
# ROUTES
# -------------------------
@router.post("/register")
async def register(data: RegisterSchema):
    try:
        result = await register_user(**data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="User already exists")
        return {
            "user_id": result["user_id"],
            "message": "User registered successfully",
            **result["tokens"]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(data: LoginSchema):
    tokens = await authenticate_user(**data.model_dump())
    if not tokens:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return tokens

@router.post("/refresh")
async def refresh_token(data: RefreshTokenSchema):
    """Refresh access token using refresh token."""
    tokens = await refresh_access_token(data.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or expired refresh token"
        )
    return tokens

@router.post("/logout")
async def logout(data: RefreshTokenSchema, user_id: str = Depends(get_current_user)):
    """Logout by revoking the refresh token."""
    # Decode refresh token to get JTI
    payload = decode_refresh_token(data.refresh_token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid refresh token")
    
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=400, detail="Invalid refresh token format")
    
    success = await revoke_refresh_token(jti)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to revoke token")
    
    return {"message": "Logged out successfully"}

@router.post("/logout-all")
async def logout_all_devices(user_id: str = Depends(get_current_user)):
    """Logout from all devices by revoking all user's refresh tokens."""
    success = await revoke_all_user_tokens(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to revoke tokens")
    
    return {"message": "Logged out from all devices successfully"}

@router.get("/me")
async def get_current_user_info(user_id: str = Depends(get_current_user)):
    user = await get_user_by_email(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/display-name")
async def change_display_name(
    new_data: UpdateDisplayNameSchema, user_id: str = Depends(get_current_user)
):
    success = await update_display_name(user_id, new_data.display_name)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or update failed")
    return {"message": "Display name updated successfully"}

@router.post("/google")
async def google_login(data: GoogleLoginSchema):
    try:
        tokens = await authenticate_google_user(data.id_token)
        return tokens
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google login failed: {str(e)}")