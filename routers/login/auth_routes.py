from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from src.services.auth_services import (
    register_user,
    authenticate_user,
    get_user_by_email,
    update_display_name
)
from src.utils.dependencies import get_current_user
from src.services.auth_services import authenticate_google_user

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

# -------------------------
# ROUTES
# -------------------------
@router.post("/register")
async def register(data: RegisterSchema):
    user_id = await register_user(**data.model_dump())
    if not user_id:
        raise HTTPException(status_code=400, detail="User already exists")
    return {"user_id": user_id, "message": "User registered successfully"}

@router.post("/login")
async def login(data: LoginSchema):
    token = await authenticate_user(**data.model_dump())
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": token, "token_type": "bearer"}

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
        token = await authenticate_google_user(data.id_token)
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google login failed: {str(e)}")