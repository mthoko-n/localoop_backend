from typing import Optional
from bson import ObjectId
from dotenv import load_dotenv  # Add this import
from src.utils.auth_utils import hash_password, verify_password, generate_token_pair, decode_refresh_token
from src.utils.db import fetch, insert, update
from src.utils.auth_utils import validate_password_strength
from src.services.refresh_token_services import store_refresh_token
from google.oauth2 import id_token
from google.auth.transport import requests
import os
from src.utils.logger import get_logger

# Load environment variables
load_dotenv()  

logger = get_logger("DB Manager")

# -------------------------
# USER REGISTRATION
# -------------------------
async def register_user(email: str, password: str, display_name: str, last_name: str) -> Optional[dict]:
    """Register a new user. Returns token pair if successful."""
    # Check if user already exists (only active users)
    existing = await fetch("users", {"email": email, "is_active": {"$ne": False}})
    if existing:
        return None  # User already exists

    # Validate password strength
    if not validate_password_strength(password):
        raise ValueError(
            "Password too weak. Must be 8+ chars, with lowercase, uppercase, number, and special char."
        )

    # Hash password
    hashed_pw = hash_password(password)

    # Insert user into DB with new soft delete fields
    user_doc = {
        "email": email,
        "password": hashed_pw,
        "display_name": display_name,
        "last_name": last_name,
        "is_active": True,
        "deleted_at": None
    }
    user_id = await insert("users", user_doc)
    
    if user_id:
        # Generate token pair for new user
        tokens = generate_token_pair(str(user_id), email)
        
        # Store refresh token
        refresh_payload = decode_refresh_token(tokens["refresh_token"])
        jti = refresh_payload.get("jti")
        
        if jti:
            await store_refresh_token(str(user_id), tokens["refresh_token"], jti)
        
        return {
            "user_id": str(user_id),
            "tokens": tokens
        }
    
    return None

# -------------------------
# USER LOGIN
# -------------------------
async def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns token pair if successful."""
    users = await fetch("users", {"email": email, "is_active": True})
    if not users:
        return None  # User not found or soft-deleted

    user = users[0]

    # Check password
    if "password" in user and not verify_password(password, user["password"]):
        return None  # Wrong password

    user_id = str(user["_id"])
        
    # Generate token pair
    tokens = generate_token_pair(user_id, email)
    
    # Store refresh token
    refresh_payload = decode_refresh_token(tokens["refresh_token"])
    jti = refresh_payload.get("jti")
    
    if jti:
        await store_refresh_token(user_id, tokens["refresh_token"], jti)
    
    return tokens

# -------------------------
# GET USER BY EMAIL
# -------------------------
async def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch user details without password."""
    users = await fetch("users", {"email": email, "is_active": True})
    if not users:
        return None
    user = users[0]
    user.pop("password", None)
    return user

# -------------------------
# UPDATE DISPLAY NAME
# -------------------------
async def update_display_name(user_id: str, new_display_name: str) -> bool:
    """Update a user's display name."""
    # Optional: check if user exists
    users = await fetch("users", {"_id": ObjectId(user_id)})
    if not users:
        return False

    success = await update("users", user_id, {"display_name": new_display_name})
    return success

# -------------------------
# GOOGLE AUTHENTICATION
# -------------------------
async def authenticate_google_user(id_token_str: str) -> dict:
    """Verify Google ID token, create/find user, return token pair."""
    try:
        # Add some logging to debug
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        logger.info(f"Using Google Client ID: {google_client_id[:10]}..." if google_client_id else "No GOOGLE_CLIENT_ID found")
        
        id_info = id_token.verify_oauth2_token(
            id_token_str, requests.Request(), google_client_id
        )
        
        email = id_info.get("email")
        google_id = id_info.get("sub")
        display_name = id_info.get("name")

        logger.info(f"Google auth successful for email: {email}")

        # Only consider active users
        users = await fetch("users", {"email": email, "is_active": {"$ne": False}})
        if not users:
            user_doc = {
                "email": email,
                "google_id": google_id,
                "display_name": display_name,
                "auth_provider": "google",
                "is_active": True,   
                "deleted_at": None   
            }
            user_id = await insert("users", user_doc)
            user_id = str(user_id)
            logger.info(f"Created new Google user with ID: {user_id}")
        else:
            user_id = str(users[0]["_id"])
            logger.info(f"Found existing user with ID: {user_id}")

        # Generate token pair
        tokens = generate_token_pair(user_id, email)
        
        # Store refresh token
        refresh_payload = decode_refresh_token(tokens["refresh_token"])
        jti = refresh_payload.get("jti")
        
        if jti:
            await store_refresh_token(user_id, tokens["refresh_token"], jti)
        
        logger.info("Google authentication completed successfully")
        return tokens
        
    except Exception as e:
        logger.error(f"Google authentication error: {str(e)}")
        raise