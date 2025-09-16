from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from src.utils.db import fetch, update, delete
from src.utils.auth_utils import verify_password, hash_password, validate_password_strength
from src.utils.serialize_helper import serialize_doc

# -------------------------
# GET USER PROFILE
# -------------------------
# -------------------------
# GET USER PROFILE
# -------------------------
async def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile information without sensitive data."""
    try:
        # Convert string ID to ObjectId for MongoDB query
        object_id = ObjectId(user_id)
        users = await fetch("users", {"_id": object_id})
        if not users:
            return None
        
        user = serialize_doc(users[0])  # ✅ serialize ObjectId and datetime
        
        # Build profile with only existing fields
        profile = {
            "id": user.get("id") or user.get("_id"),
            "email": user["email"],
            "display_name": user.get("display_name", ""),
            "last_name": user.get("last_name", "")
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
    """Change user password after verifying current password."""
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
        return {"success": success, "error": None if success else "Failed to update password"}
        
    except Exception as e:
        print(f"Error in change_user_password: {e}")
        return {"success": False, "error": "Internal server error"}

# -------------------------
# DELETE USER ACCOUNT
# -------------------------
async def delete_user_account(user_id: str, password: str) -> Dict[str, Any]:
    """Delete user account after password verification."""
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
        
        # For users with passwords, verify the password
        if "password" in user:
            if not verify_password(password, user["password"]):
                return {"success": False, "error": "Password is incorrect"}
        else:
            # For Google users, you might want different verification
            # For now, we'll require them to provide any non-empty string
            if not password.strip():
                return {"success": False, "error": "Confirmation required"}
        
        # TODO: You might want to:
        # 1. Delete user's locations
        # 2. Remove user from location memberships  
        # 3. Clean up related data
        # await cleanup_user_data(user_id)
        
        # Delete the user
        success = await delete("users", user_id)
        return {"success": success, "error": None if success else "Failed to delete account"}
        
    except Exception as e:
        print(f"Error in delete_user_account: {e}")
        return {"success": False, "error": "Internal server error"}

# -------------------------
# GET USER STATISTICS
# -------------------------
async def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get user statistics with just member since date."""
    try:
        # Convert string ID to ObjectId for MongoDB query
        object_id = ObjectId(user_id)
        users = await fetch("users", {"_id": object_id})
        if not users:
            return {}
        
        user = serialize_doc(users[0])

        # Calculate member since date
        created_at = user.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    member_since = dt.strftime("%B %Y")
                except:
                    member_since = created_at[:7] if len(created_at) >= 7 else "Unknown"
            else:
                member_since = created_at.strftime("%B %Y")
        else:
            # No created_at → fallback to ObjectId’s timestamp
            creation_time = ObjectId(user["id"]).generation_time
            member_since = creation_time.strftime("%B %Y")
        
        return {
            "member_since": member_since
        }
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return {}