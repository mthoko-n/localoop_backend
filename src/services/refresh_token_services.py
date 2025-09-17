from typing import Optional
from datetime import datetime, timedelta
from bson import ObjectId
from src.utils.db import fetch, insert, update, delete
from src.utils.auth_utils import decode_refresh_token, generate_token_pair

async def store_refresh_token(user_id: str, refresh_token: str, jti: str) -> bool:
    """Store refresh token in database."""
    token_doc = {
        "user_id": ObjectId(user_id),
        "jti": jti,
        "token": refresh_token,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30),
        "is_revoked": False,
        "last_used": datetime.utcnow()
    }
    
    result = await insert("refresh_tokens", token_doc)
    return result is not None

async def get_refresh_token(jti: str) -> Optional[dict]:
    """Get refresh token from database by JTI."""
    tokens = await fetch("refresh_tokens", {"jti": jti, "is_revoked": False})
    if not tokens:
        return None
    
    token = tokens[0]
    # Check if token is expired
    if token["expires_at"] < datetime.utcnow():
        await revoke_refresh_token(jti)
        return None
    
    return token

async def update_refresh_token_usage(jti: str) -> bool:
    """Update last_used timestamp for refresh token."""
    tokens = await fetch("refresh_tokens", {"jti": jti})
    if not tokens:
        return False
    
    token_id = str(tokens[0]["_id"])
    return await update("refresh_tokens", token_id, {"last_used": datetime.utcnow()})

async def revoke_refresh_token(jti: str) -> bool:
    """Revoke a refresh token."""
    tokens = await fetch("refresh_tokens", {"jti": jti})
    if not tokens:
        return False
    
    token_id = str(tokens[0]["_id"])
    return await update("refresh_tokens", token_id, {"is_revoked": True})

async def revoke_all_user_tokens(user_id: str) -> bool:
    """Revoke all refresh tokens for a user (useful for logout from all devices)."""
    try:
        # This is a bulk update - you might need to implement this in your db utils
        # For now, we'll fetch all tokens and revoke them individually
        tokens = await fetch("refresh_tokens", {
            "user_id": ObjectId(user_id), 
            "is_revoked": False
        })
        
        success = True
        for token in tokens:
            token_id = str(token["_id"])
            result = await update("refresh_tokens", token_id, {"is_revoked": True})
            if not result:
                success = False
        
        return success
    except Exception:
        return False

async def cleanup_expired_tokens() -> int:
    """Clean up expired refresh tokens. Returns count of deleted tokens."""
    try:
        # This should be run periodically (e.g., daily cron job)
        expired_tokens = await fetch("refresh_tokens", {
            "expires_at": {"$lt": datetime.utcnow()}
        })
        
        deleted_count = 0
        for token in expired_tokens:
            token_id = str(token["_id"])
            if await delete("refresh_tokens", token_id):
                deleted_count += 1
        
        return deleted_count
    except Exception:
        return 0

async def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """
    Validate refresh token and generate new access token.
    Returns new token pair or None if invalid.
    """
    # Decode the refresh token
    payload = decode_refresh_token(refresh_token)
    if not payload:
        return None
    
    jti = payload.get("jti")
    user_id = payload.get("user_id")
    user_email = payload.get("sub")
    
    if not all([jti, user_id, user_email]):
        return None
    
    # Check if token exists and is valid in database
    stored_token = await get_refresh_token(jti)
    if not stored_token:
        return None
    
    # Verify the token matches
    if stored_token["token"] != refresh_token:
        await revoke_refresh_token(jti)
        return None
    
    # Update last used timestamp
    await update_refresh_token_usage(jti)
    
    # Generate new token pair
    new_tokens = generate_token_pair(user_id, user_email)
    
    # Store the new refresh token
    new_payload = decode_refresh_token(new_tokens["refresh_token"])
    new_jti = new_payload.get("jti")
    
    if new_jti:
        await store_refresh_token(user_id, new_tokens["refresh_token"], new_jti)
        # Optionally revoke the old refresh token for security
        await revoke_refresh_token(jti)
    
    return new_tokens

async def get_user_active_sessions(user_id: str) -> list:
    """Get all active sessions for a user with metadata."""
    try:
        tokens = await fetch("refresh_tokens", {
            "user_id": ObjectId(user_id),
            "is_revoked": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        sessions = []
        for token in tokens:
            session_info = {
                "jti": token["jti"],
                "created_at": token["created_at"].isoformat() if token.get("created_at") else None,
                "last_used": token["last_used"].isoformat() if token.get("last_used") else None,
                "ip_address": token.get("ip_address", "Unknown"),
                "user_agent": token.get("user_agent", "Unknown Device"),
                "expires_at": token["expires_at"].isoformat() if token.get("expires_at") else None
            }
            sessions.append(session_info)
        
        # Sort by last_used (most recent first)
        sessions.sort(key=lambda x: x["last_used"] or "", reverse=True)
        return sessions
    
    except Exception as e:
        print(f"Error getting user active sessions: {e}")
        return []

async def get_refresh_token_with_user_check(jti: str, user_id: str) -> Optional[dict]:
    """Get refresh token and verify it belongs to the specified user."""
    try:
        tokens = await fetch("refresh_tokens", {
            "jti": jti,
            "user_id": ObjectId(user_id),
            "is_revoked": False
        })
        
        if not tokens:
            return None
        
        token = tokens[0]
        # Check if token is expired
        if token["expires_at"] < datetime.utcnow():
            await revoke_refresh_token(jti)
            return None
        
        return token
    
    except Exception as e:
        print(f"Error getting refresh token with user check: {e}")
        return None