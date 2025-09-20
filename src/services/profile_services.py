from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from src.utils.db import fetch, update, delete, update_many
from src.utils.auth_utils import verify_password, hash_password, validate_password_strength
from src.utils.serialize_helper import serialize_doc
from src.services.refresh_token_services import revoke_all_user_tokens

# -------------------------
# GET USER PROFILE
# -------------------------
async def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile information without sensitive data."""
    try:
        object_id = ObjectId(user_id)
        users = await fetch("users", {"_id": object_id})
        if not users:
            return None
        
        user = serialize_doc(users[0])

        profile = {
            "id": str(user.get("id") or user.get("_id")),
            "email": user["email"],
            "display_name": user.get("display_name", ""),
            "last_name": user.get("last_name", ""),
            "hasPassword": "password" in user,
            "is_admin": user.get("is_admin", False)  # Add this line
        }
        
        return profile
    except Exception as e:
        print(f"Error in get_user_profile: {e}")
        return None
# -------------------------
# UPDATE USER PROFILE
# -------------------------
async def update_user_profile(user_id: str, update_data: Dict[str, Any]) -> bool:
    """Update user profile information."""
    try:
        # Validate ObjectId format
        if not ObjectId.is_valid(user_id):
            return False
            
        # Add timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        success = await update("users", user_id, update_data)
        return success
    except Exception as e:
        print(f"Error in update_user_profile: {e}")
        return False

# -------------------------
# CHANGE USER PASSWORD
# -------------------------
async def change_user_password(
    user_id: str, 
    current_password: str, 
    new_password: str
) -> Dict[str, Any]:
    """
    Change user password after verifying current password.
    IMPORTANT: This should revoke all refresh tokens to force re-login on all devices.
    """
    try:
        # Validate ObjectId format
        if not ObjectId.is_valid(user_id):
            return {"success": False, "error": "Invalid user ID"}
            
        # Convert string ID to ObjectId for MongoDB query
        object_id = ObjectId(user_id)
        users = await fetch("users", {"_id": object_id})
        if not users:
            return {"success": False, "error": "User not found"}
        
        user = users[0]
        
        # Check if user has a password (Google users might not)
        if "password" not in user:
            return {"success": False, "error": "Cannot change password for social login users"}
        
        # Verify current password
        if not verify_password(current_password, user["password"]):
            return {"success": False, "error": "Current password is incorrect"}
        
        # Validate new password strength
        if not validate_password_strength(new_password):
            return {"success": False, "error": "New password too weak. Must be 8+ chars, with lowercase, uppercase, number, and special char."}
        
        # Hash new password and update
        hashed_new_password = hash_password(new_password)
        
        update_data = {
            "password": hashed_new_password,
            "updated_at": datetime.utcnow()
        }
        
        success = await update("users", user_id, update_data)
        
        if success:
            # SECURITY: Revoke all refresh tokens to force re-login on all devices
            # This prevents anyone with old tokens from accessing the account
            await revoke_all_user_tokens(user_id)
            print(f"Password changed for user {user_id} - all sessions revoked")
        
        return {"success": success, "error": None if success else "Failed to update password"}
        
    except Exception as e:
        print(f"Error in change_user_password: {e}")
        return {"success": False, "error": "Internal server error"}

# -------------------------
# DELETE USER ACCOUNT
# -------------------------
async def delete_user_account(user_id: str, password: str) -> dict:
    """
    Soft delete a user account:
    1. Verify user and password
    2. Revoke all refresh tokens (immediate logout from all devices)
    3. Mark user as inactive
    4. Soft delete all conversations authored by the user
    5. Soft delete all messages authored by the user
    """
    try:
        # Fetch user
        users = await fetch("users", {"_id": ObjectId(user_id)})
        if not users:
            return {"success": False, "error": "User not found"}

        user = users[0]

        # Verify password (if exists)
        # For Google users without password, we might want additional verification
        if "password" in user and not verify_password(password, user["password"]):
            return {"success": False, "error": "Password is incorrect"}
        elif "password" not in user and password:  # Google user providing password
            return {"success": False, "error": "This account uses social login. No password required."}

        now = datetime.utcnow()

        # CRITICAL: Revoke all refresh tokens FIRST
        # This immediately logs out the user from all devices
        revoke_success = await revoke_all_user_tokens(user_id)
        if not revoke_success:
            print(f"Warning: Failed to revoke some tokens for user {user_id} during account deletion")

        # Soft delete user
        user_update = {
            "is_active": False, 
            "deleted_at": now,
            "deletion_reason": "user_requested"  # Track why account was deleted
        }
        success = await update("users", user_id, user_update)
        if not success:
            return {"success": False, "error": "Failed to soft delete user"}

        # Soft delete user's conversations
        conv_update = {
            "is_active": False, 
            "deleted_at": now,
            "deletion_reason": "user_account_deleted"
        }
        conv_result = await update_many("conversations", {"author_id": user_id, "is_active": True}, conv_update)

        # Soft delete user's messages
        msg_update = {
            "is_deleted": True, 
            "deleted_at": now,
            "deletion_reason": "user_account_deleted"
        }
        msg_result = await update_many("messages", {"author_id": user_id, "is_deleted": {"$ne": True}}, msg_update)

        print(f"Account deletion completed for user {user_id}")
        print(f"- User marked inactive: {success}")
        print(f"- Conversations deleted: {conv_result}")
        print(f"- Messages deleted: {msg_result}")
        print(f"- All sessions revoked: {revoke_success}")

        return {
            "success": True, 
            "error": None,
            "message": "Account and all data successfully deleted. You have been logged out from all devices."
        }

    except Exception as e:
        print(f"Error in delete_user_account: {e}")
        return {"success": False, "error": f"Internal server error: {e}"}

# -------------------------
# REACTIVATE USER ACCOUNT (Optional feature)
# -------------------------
async def reactivate_user_account(email: str, password: str) -> dict:
    """
    Reactivate a soft-deleted account within a grace period (e.g., 30 days).
    This is a common feature for account recovery.
    """
    try:
        # Find soft-deleted user
        users = await fetch("users", {
            "email": email, 
            "is_active": False,
            "deleted_at": {"$exists": True}
        })
        
        if not users:
            return {"success": False, "error": "No deleted account found with this email"}
        
        user = users[0]
        user_id = str(user["_id"])
        
        # Check if deletion was too long ago (30 day grace period)
        deletion_date = user.get("deleted_at")
        if deletion_date:
            days_since_deletion = (datetime.utcnow() - deletion_date).days
            if days_since_deletion > 30:
                return {"success": False, "error": "Account was deleted too long ago and cannot be recovered"}
        
        # Verify password
        if "password" in user and not verify_password(password, user["password"]):
            return {"success": False, "error": "Password is incorrect"}
        
        # Reactivate user
        reactivation_data = {
            "is_active": True,
            "deleted_at": None,
            "deletion_reason": None,
            "reactivated_at": datetime.utcnow()
        }
        
        success = await update("users", user_id, reactivation_data)
        
        if success:
            # Optionally reactivate conversations and messages too
            await update_many("conversations", 
                {"author_id": user_id, "deletion_reason": "user_account_deleted"}, 
                {"is_active": True, "deleted_at": None, "deletion_reason": None}
            )
            
            await update_many("messages", 
                {"author_id": user_id, "deletion_reason": "user_account_deleted"}, 
                {"is_deleted": False, "deleted_at": None, "deletion_reason": None}
            )
        
        return {"success": success, "error": None if success else "Failed to reactivate account"}
        
    except Exception as e:
        print(f"Error in reactivate_user_account: {e}")
        return {"success": False, "error": "Internal server error"}

# -------------------------
# GET USER STATISTICS
# -------------------------
async def get_user_stats(user: dict) -> Optional[Dict[str, Any]]:
    try:
        user_id = str(user.get("id") or user.get("_id"))

        # Fetch messages for this user (only active messages)
        messages = await fetch("messages", {
            "author_id": user_id,
            "is_deleted": {"$ne": True}  # Only count non-deleted messages
        })

        # Sort messages by timestamp ascending (optional, if fetch doesn't guarantee order)
        messages.sort(key=lambda m: m["timestamp"])

        # Get active sessions count (optional monitoring feature)
        active_tokens = await fetch("refresh_tokens", {
            "user_id": ObjectId(user_id),
            "is_revoked": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })

        stats = {
            "id": user_id,
            "total_messages": len(messages),
            "last_activity": messages[-1]["timestamp"] if messages else None,
            "active_sessions": len(active_tokens)  # How many devices/browsers are logged in
        }

        return stats
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return None