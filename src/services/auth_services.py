from typing import Optional
from bson import ObjectId
from src.utils.auth_utils import hash_password, verify_password, create_access_token
from src.utils.db import fetch, insert, update
from src.utils.auth_utils import validate_password_strength
from google.oauth2 import id_token
from google.auth.transport import requests

# -------------------------
# USER REGISTRATION
# -------------------------
async def register_user(email: str, password: str, display_name: str, last_name: str) -> Optional[str]:
    """Register a new user. Returns user ID if successful."""
    # Check if user already exists
    existing = await fetch("users", {"email": email})
    if existing:
        return None  # User already exists

    # Validate password strength
    if not validate_password_strength(password):
        raise ValueError("Password too weak. Must be 8+ chars, with lowercase, uppercase, number, and special char.")

    # Hash password
    hashed_pw = hash_password(password)

    # Insert user into DB
    user_doc = {
        "email": email,
        "password": hashed_pw,
        "display_name": display_name,
        "last_name": last_name
    }
    user_id = await insert("users", user_doc)
    return user_id


# -------------------------
# USER LOGIN
# -------------------------
async def authenticate_user(email: str, password: str) -> Optional[str]:
    """Verify credentials. Returns JWT token if successful."""
    users = await fetch("users", {"email": email})
    if not users:
        return None  # User not found

    user = users[0]
    if not verify_password(password, user["password"]):
        return None  # Wrong password

    # Create JWT token
    token_data = {"sub": user["email"], "user_id": str(user["_id"])}
    access_token = create_access_token(token_data)
    return access_token

# -------------------------
# GET USER BY EMAIL
# -------------------------
async def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch user details without password."""
    users = await fetch("users", {"email": email})
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

async def authenticate_google_user(id_token_str: str) -> str:
    """Verify Google ID token, create/find user, return JWT."""
    id_info = id_token.verify_oauth2_token(
        id_token_str, requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
    )
    email = id_info.get("email")
    google_id = id_info.get("sub")
    display_name = id_info.get("name")

    users = await fetch("users", {"email": email})
    if not users:
        user_doc = {
            "email": email,
            "google_id": google_id,
            "display_name": display_name,
            "auth_provider": "google",
        }
        user_id = await insert("users", user_doc)
    else:
        user_id = str(users[0]["_id"])

    token_data = {"sub": email, "user_id": user_id}
    return create_access_token(token_data)
