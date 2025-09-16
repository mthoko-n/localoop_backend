from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from src.utils.db import fetch, update, delete
from src.utils.auth_utils import verify_password, hash_password, validate_password_strength
from src.utils.serialize_helper import serialize_doc

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
        
        # Remove sensitive information and structure the response
        profile = {
            "id": user.get("id") or user.get("_id"),
            "email": user["email"],
            "display_name": user.get("display_name", ""),
            "last_name": user.get("last_name", ""),
            "auth_provider": user.get("auth_provider", "email"),
            "updated_at": user.get("updated_at")
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
# GET USER LOCATIONS FOR PROFILE
# -------------------------
async def get_profile_user_locations(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user's location summary for profile stats."""
    try:
        user_locations = await fetch("user_locations", {"user_id": user_id, "is_active": True})
        if not user_locations:
            return {
                "total_locations": 0,
                "recent_locations": [],
                "most_active_location": None
            }
        
        # Serialize all locations
        locations = [serialize_doc(loc) for loc in user_locations]
        
        # Sort by last activity to get most recent
        locations.sort(key=lambda x: x.get("last_activity", x.get("joined_at")), reverse=True)
        
        # Get recent locations (last 5)
        recent_locations = []
        for loc in locations[:5]:
            recent_locations.append({
                "id": loc.get("id"),
                "name": loc.get("name", "Unknown Location"),
                "last_activity": loc.get("last_activity"),
                "unread_count": loc.get("unread_count", 0)
            })
        
        # Find most active location (highest unread count or most recent activity)
        most_active = None
        if locations:
            # Sort by unread count first, then by last activity
            most_active_loc = max(locations, 
                                key=lambda x: (x.get("unread_count", 0), 
                                             x.get("last_activity", x.get("joined_at"))))
            most_active = {
                "id": most_active_loc.get("id"),
                "name": most_active_loc.get("name", "Unknown Location"),
                "unread_count": most_active_loc.get("unread_count", 0)
            }
        
        return {
            "total_locations": len(locations),
            "recent_locations": recent_locations,
            "most_active_location": most_active
        }
        
    except Exception as e:
        print(f"Error in get_profile_user_locations: {e}")
        return {
            "total_locations": 0,
            "recent_locations": [],
            "most_active_location": None
        }

# -------------------------
# GET USER STATISTICS
# -------------------------
async def get_user_locations_count(user_id: str) -> int:
    """Get count of locations user has joined."""
    try:
        # Based on your location services, user_locations uses string user_id
        user_locations = await fetch("user_locations", {"user_id": user_id, "is_active": True})
        return len(user_locations) if user_locations else 0
    except Exception as e:
        print(f"Error in get_user_locations_count: {e}")
        return 0

async def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get comprehensive user statistics."""
    try:
        # Convert string ID to ObjectId for MongoDB query
        object_id = ObjectId(user_id)
        users = await fetch("users", {"_id": object_id})
        if not users:
            return {}
        
        user = serialize_doc(users[0])  # ✅ serialize ObjectId and datetime
        locations_count = await get_user_locations_count(user_id)
        
        # Calculate member since date
        created_at = user.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                # If it's already a string from serialization, try to parse it
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    member_since = dt.strftime("%B %Y")
                except:
                    member_since = created_at[:7] if len(created_at) >= 7 else "Unknown"
            else:
                # If it's still a datetime object
                member_since = created_at.strftime("%B %Y")
        else:
            # Use ObjectId creation time as fallback (since you don't have created_at field)
            creation_time = ObjectId(user["id"]).generation_time
            member_since = creation_time.strftime("%B %Y")
        
        return {
            "locations_joined": locations_count,
            "member_since": member_since,
            "account_type": user.get("auth_provider", "email"),
            "total_locations": locations_count,  # You can add more stats
        }
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return {}