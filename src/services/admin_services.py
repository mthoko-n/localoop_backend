from typing import Optional, Dict, Any, List
from bson import ObjectId
from datetime import datetime, timedelta
from src.utils.db import fetch, update, update_many
from src.utils.serialize_helper import serialize_doc
from src.services.refresh_token_services import revoke_all_user_tokens

# -------------------------
# ADMIN ROLE MANAGEMENT
# -------------------------
async def check_user_admin_status(user_id: str) -> bool:
    """Check if user is an admin."""
    try:
        users = await fetch("users", {"_id": ObjectId(user_id), "is_active": True})
        if not users:
            return False
        
        user = users[0]
        return user.get("is_admin", False)
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False

async def make_user_admin(admin_user_id: str, target_user_id: str) -> Dict[str, Any]:
    """Make a user an admin. Only existing admins can do this."""
    try:
        # Check if requesting user is admin
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Only admins can promote users"}
        
        # Update target user
        success = await update("users", target_user_id, {
            "is_admin": True,
            "promoted_at": datetime.utcnow(),
            "promoted_by": admin_user_id
        })
        
        return {"success": success, "error": None if success else "Failed to promote user"}
    except Exception as e:
        return {"success": False, "error": f"Error promoting user: {e}"}

async def remove_admin_status(admin_user_id: str, target_user_id: str) -> Dict[str, Any]:
    """Remove admin status from a user."""
    try:
        # Check if requesting user is admin
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Only admins can demote users"}
        
        # Prevent self-demotion (optional safety measure)
        if admin_user_id == target_user_id:
            return {"success": False, "error": "Cannot remove your own admin status"}
        
        success = await update("users", target_user_id, {
            "is_admin": False,
            "demoted_at": datetime.utcnow(),
            "demoted_by": admin_user_id
        })
        
        return {"success": success, "error": None if success else "Failed to demote user"}
    except Exception as e:
        return {"success": False, "error": f"Error demoting user: {e}"}

# -------------------------
# USER MANAGEMENT
# -------------------------
async def get_all_users(admin_user_id: str, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Get paginated list of all users. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Calculate skip for pagination
        skip = (page - 1) * limit
        
        # Get total count
        total_users = len(await fetch("users", {}))
        
        # Get users with pagination
        users = await fetch("users", {}, limit=limit, skip=skip)
        
        # Serialize and clean sensitive data
        user_list = []
        for user in users:
            user_doc = serialize_doc(user)
            # Remove sensitive fields
            user_doc.pop("password", None)
            user_doc["id"] = str(user_doc.get("id", user_doc.get("_id")))
            user_list.append(user_doc)
        
        return {
            "success": True,
            "users": user_list,
            "pagination": {
                "current_page": page,
                "total_pages": (total_users + limit - 1) // limit,
                "total_users": total_users,
                "limit": limit
            }
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching users: {e}"}

async def ban_user(admin_user_id: str, target_user_id: str, reason: str = None) -> Dict[str, Any]:
    """Ban a user (soft delete). Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Cannot ban yourself
        if admin_user_id == target_user_id:
            return {"success": False, "error": "Cannot ban yourself"}
        
        # Check if target user exists and is active
        users = await fetch("users", {"_id": ObjectId(target_user_id), "is_active": True})
        if not users:
            return {"success": False, "error": "User not found or already banned"}
        
        now = datetime.utcnow()
        
        # Revoke all refresh tokens (immediate logout)
        await revoke_all_user_tokens(target_user_id)
        
        # Soft delete user
        success = await update("users", target_user_id, {
            "is_active": False,
            "deleted_at": now,
            "deletion_reason": "admin_ban",
            "banned_by": admin_user_id,
            "ban_reason": reason or "No reason provided"
        })
        
        if success:
            # Soft delete user's conversations (using correct field structure)
            await update_many("conversations", 
                {"author_id": target_user_id, "is_active": True}, 
                {"is_active": False, "deleted_at": now, "deletion_reason": "user_banned"}
            )
            
            # Soft delete user's messages (using correct field structure)
            await update_many("messages", 
                {"author_id": target_user_id, "is_deleted": {"$ne": True}}, 
                {"is_deleted": True, "deleted_at": now, "deletion_reason": "user_banned"}
            )
        
        return {"success": success, "error": None if success else "Failed to ban user"}
    except Exception as e:
        return {"success": False, "error": f"Error banning user: {e}"}

async def unban_user(admin_user_id: str, target_user_id: str) -> Dict[str, Any]:
    """Unban a user (reactivate). Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Check if user is banned
        users = await fetch("users", {
            "_id": ObjectId(target_user_id), 
            "is_active": False,
            "deletion_reason": "admin_ban"
        })
        if not users:
            return {"success": False, "error": "User not found or not banned"}
        
        # Reactivate user
        success = await update("users", target_user_id, {
            "is_active": True,
            "deleted_at": None,
            "deletion_reason": None,
            "unbanned_at": datetime.utcnow(),
            "unbanned_by": admin_user_id
        })
        
        if success:
            # Reactivate user's content
            await update_many("conversations", 
                {"author_id": target_user_id, "deletion_reason": "user_banned"}, 
                {"is_active": True, "deleted_at": None, "deletion_reason": None}
            )
            
            await update_many("messages", 
                {"author_id": target_user_id, "deletion_reason": "user_banned"}, 
                {"is_deleted": False, "deleted_at": None, "deletion_reason": None}
            )
        
        return {"success": success, "error": None if success else "Failed to unban user"}
    except Exception as e:
        return {"success": False, "error": f"Error unbanning user: {e}"}

async def force_logout_user(admin_user_id: str, target_user_id: str) -> Dict[str, Any]:
    """Force logout a specific user. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        success = await revoke_all_user_tokens(target_user_id)
        return {"success": success, "error": None if success else "Failed to logout user"}
    except Exception as e:
        return {"success": False, "error": f"Error forcing logout: {e}"}

async def force_logout_all_users(admin_user_id: str) -> Dict[str, Any]:
    """Force logout ALL users (nuclear option). Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Get all active users
        users = await fetch("users", {"is_active": True})
        
        logout_count = 0
        for user in users:
            user_id = str(user["_id"])
            if await revoke_all_user_tokens(user_id):
                logout_count += 1
        
        return {
            "success": True, 
            "message": f"Logged out {logout_count} users",
            "logged_out_count": logout_count
        }
    except Exception as e:
        return {"success": False, "error": f"Error logging out all users: {e}"}

# -------------------------
# SYSTEM METRICS
# -------------------------
async def get_system_metrics(admin_user_id: str) -> Dict[str, Any]:
    """Get system-wide metrics. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # User metrics
        total_users = len(await fetch("users", {}))
        active_users = len(await fetch("users", {"is_active": True}))
        banned_users = len(await fetch("users", {"is_active": False, "deletion_reason": "admin_ban"}))
        admin_users = len(await fetch("users", {"is_admin": True, "is_active": True}))
        
        # Content metrics
        try:
            total_conversations = len(await fetch("conversations", {}))
            active_conversations = len(await fetch("conversations", {"is_active": True}))
            total_messages = len(await fetch("messages", {}))
            active_messages = len(await fetch("messages", {"is_deleted": {"$ne": True}}))
        except:
            # If collections don't exist yet
            total_conversations = active_conversations = 0
            total_messages = active_messages = 0
        
        # Location metrics
        try:
            total_locations = len(await fetch("user_locations", {}))
            active_locations = len(await fetch("user_locations", {"is_active": True}))
            # Get unique location IDs
            unique_locations = set()
            all_user_locs = await fetch("user_locations", {})
            for loc in all_user_locs:
                unique_locations.add(loc.get("id"))
            unique_location_count = len(unique_locations)
        except:
            total_locations = active_locations = unique_location_count = 0
        
        # Session metrics
        try:
            active_sessions = len(await fetch("refresh_tokens", {
                "is_revoked": False,
                "expires_at": {"$gt": datetime.utcnow()}
            }))
        except:
            active_sessions = 0
        
        # Recent activity (users created in last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        try:
            recent_users = len(await fetch("users", {
                "_id": {"$gte": ObjectId.from_datetime(week_ago)}
            }))
        except:
            recent_users = 0
        
        return {
            "success": True,
            "metrics": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "banned": banned_users,
                    "admins": admin_users,
                    "new_this_week": recent_users
                },
                "content": {
                    "total_conversations": total_conversations,
                    "active_conversations": active_conversations,
                    "total_messages": total_messages,
                    "active_messages": active_messages
                },
                "locations": {
                    "total_user_locations": total_locations,
                    "active_user_locations": active_locations,
                    "unique_locations": unique_location_count
                },
                "sessions": {
                    "active_sessions": active_sessions
                }
            }
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching metrics: {e}"}

# -------------------------
# LOCATION MANAGEMENT
# -------------------------
async def get_all_locations(admin_user_id: str, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Get all user locations across the system. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        skip = (page - 1) * limit
        
        # Get all user locations with user info
        locations = await fetch("user_locations", {}, limit=limit, skip=skip, sort=[("created_at", -1)])
        total_locations = len(await fetch("user_locations", {}))
        
        location_list = []
        for loc in locations:
            loc_doc = serialize_doc(loc)
            
            # Get user info for this location
            try:
                users = await fetch("users", {"_id": ObjectId(loc_doc["user_id"])})
                if users:
                    user = users[0]
                    loc_doc["user_email"] = user.get("email", "Unknown")
                    loc_doc["user_name"] = f"{user.get('display_name', '')} {user.get('last_name', '')}".strip()
                else:
                    loc_doc["user_email"] = "Unknown"
                    loc_doc["user_name"] = "Unknown User"
            except:
                loc_doc["user_email"] = "Unknown"
                loc_doc["user_name"] = "Unknown User"
            
            # Get activity stats for this location
            try:
                conversation_count = len(await fetch("conversations", {"location_id": loc_doc["id"], "is_active": True}))
                message_count = len(await fetch("messages", {
                    "conversation_id": {"$in": [conv["id"] for conv in await fetch("conversations", {"location_id": loc_doc["id"]})]},
                    "is_deleted": {"$ne": True}
                }))
                loc_doc["conversation_count"] = conversation_count
                loc_doc["message_count"] = message_count
            except:
                loc_doc["conversation_count"] = 0
                loc_doc["message_count"] = 0
            
            location_list.append(loc_doc)
        
        return {
            "success": True,
            "locations": location_list,
            "pagination": {
                "current_page": page,
                "total_pages": (total_locations + limit - 1) // limit,
                "total_locations": total_locations,
                "limit": limit
            }
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching locations: {e}"}

async def get_location_analytics(admin_user_id: str, location_id: str) -> Dict[str, Any]:
    """Get detailed analytics for a specific location. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Get location info
        user_locations = await fetch("user_locations", {"id": location_id})
        if not user_locations:
            return {"success": False, "error": "Location not found"}
        
        location = serialize_doc(user_locations[0])
        
        # Get conversations for this location
        conversations = await fetch("conversations", {"location_id": location_id})
        active_conversations = await fetch("conversations", {"location_id": location_id, "is_active": True})
        
        # Get messages for this location
        conversation_ids = [conv["id"] for conv in conversations]
        all_messages = []
        active_messages = []
        
        for conv_id in conversation_ids:
            conv_messages = await fetch("messages", {"conversation_id": conv_id})
            active_conv_messages = await fetch("messages", {"conversation_id": conv_id, "is_deleted": {"$ne": True}})
            all_messages.extend(conv_messages)
            active_messages.extend(active_conv_messages)
        
        # Get unique users who have posted
        unique_authors = set()
        for msg in all_messages:
            unique_authors.add(msg.get("author_id"))
        
        # Get users who have this location
        location_users = await fetch("user_locations", {"id": location_id, "is_active": True})
        
        return {
            "success": True,
            "location": location,
            "analytics": {
                "total_conversations": len(conversations),
                "active_conversations": len(active_conversations),
                "total_messages": len(all_messages),
                "active_messages": len(active_messages),
                "unique_contributors": len(unique_authors),
                "subscribed_users": len(location_users)
            }
        }
    except Exception as e:
        return {"success": False, "error": f"Error getting location analytics: {e}"}

async def moderate_location(admin_user_id: str, location_id: str, action: str, reason: str = None) -> Dict[str, Any]:
    """Moderate a location (disable, enable, etc.). Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        if action == "disable_all_conversations":
            # Disable all conversations in this location
            conversations = await fetch("conversations", {"location_id": location_id, "is_active": True})
            disabled_count = 0
            
            for conv in conversations:
                record_id = str(conv["_id"])
                success = await update("conversations", record_id, {
                    "is_active": False,
                    "deleted_at": datetime.utcnow(),
                    "deletion_reason": "admin_location_moderation",
                    "deleted_by_admin": admin_user_id,
                    "admin_delete_reason": reason or "Location moderated"
                })
                if success:
                    disabled_count += 1
            
            return {
                "success": True,
                "message": f"Disabled {disabled_count} conversations in location"
            }
        
        elif action == "remove_all_users":
            # Remove all users from this location
            user_locations = await fetch("user_locations", {"id": location_id, "is_active": True})
            removed_count = 0
            
            for user_loc in user_locations:
                record_id = str(user_loc["_id"])
                success = await update("user_locations", record_id, {
                    "is_active": False,
                    "updated_at": datetime.utcnow(),
                    "removed_by_admin": admin_user_id,
                    "removal_reason": reason or "Admin action"
                })
                if success:
                    removed_count += 1
            
            return {
                "success": True,
                "message": f"Removed {removed_count} users from location"
            }
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
        
    except Exception as e:
        return {"success": False, "error": f"Error moderating location: {e}"}

# -------------------------
# CONTENT MODERATION
# -------------------------
async def get_conversations_by_location(admin_user_id: str, location_id: str, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Get conversations for a specific location. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        skip = (page - 1) * limit
        
        # Get conversations for location
        conversations = await fetch("conversations", 
            {"location_id": location_id}, 
            limit=limit, 
            skip=skip,
            sort=[("created_at", -1)]
        )
        
        # Get total count
        total_conversations = len(await fetch("conversations", {"location_id": location_id}))
        
        conv_list = []
        for conv in conversations:
            conv_doc = serialize_doc(conv)
            # Add message count
            message_count = len(await fetch("messages", {
                "conversation_id": conv_doc["id"], 
                "is_deleted": {"$ne": True}
            }))
            conv_doc["message_count"] = message_count
            conv_list.append(conv_doc)
        
        return {
            "success": True,
            "conversations": conv_list,
            "pagination": {
                "current_page": page,
                "total_pages": (total_conversations + limit - 1) // limit,
                "total_conversations": total_conversations,
                "limit": limit
            }
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching conversations: {e}"}

async def delete_conversation_admin(admin_user_id: str, conversation_id: str, reason: str = None) -> Dict[str, Any]:
    """Delete a conversation as admin. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Find conversation by id field (not _id)
        conversations = await fetch("conversations", {"id": conversation_id, "is_active": True})
        if not conversations:
            return {"success": False, "error": "Conversation not found"}
        
        # Soft delete conversation
        record_id = str(conversations[0]["_id"])
        success = await update("conversations", record_id, {
            "is_active": False,
            "deleted_at": datetime.utcnow(),
            "deletion_reason": "admin_moderation",
            "deleted_by_admin": admin_user_id,
            "admin_delete_reason": reason or "No reason provided"
        })
        
        return {"success": success, "error": None if success else "Failed to delete conversation"}
    except Exception as e:
        return {"success": False, "error": f"Error deleting conversation: {e}"}

async def delete_message_admin(admin_user_id: str, message_id: str, reason: str = None) -> Dict[str, Any]:
    """Delete a message as admin. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # Find message by id field (not _id)
        messages = await fetch("messages", {"id": message_id, "is_deleted": {"$ne": True}})
        if not messages:
            return {"success": False, "error": "Message not found"}
        
        # Soft delete message
        record_id = str(messages[0]["_id"])
        success = await update("messages", record_id, {
            "is_deleted": True,
            "deleted_at": datetime.utcnow(),
            "deletion_reason": "admin_moderation",
            "deleted_by_admin": admin_user_id,
            "admin_delete_reason": reason or "No reason provided"
        })
        
        return {"success": success, "error": None if success else "Failed to delete message"}
    except Exception as e:
        return {"success": False, "error": f"Error deleting message: {e}"}

async def get_flagged_content(admin_user_id: str) -> Dict[str, Any]:
    """Get content that might need moderation. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # This is a placeholder - you could implement content flagging later
        # For now, return recent content that might need review
        recent_conversations = await fetch("conversations", 
            {"is_active": True}, 
            limit=10,
            sort=[("created_at", -1)]
        )
        
        recent_messages = await fetch("messages", 
            {"is_deleted": {"$ne": True}}, 
            limit=20,
            sort=[("timestamp", -1)]
        )
        
        return {
            "success": True,
            "recent_conversations": [serialize_doc(conv) for conv in recent_conversations],
            "recent_messages": [serialize_doc(msg) for msg in recent_messages]
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching flagged content: {e}"}

# -------------------------
# ACTIVITY LOGS (Optional)
# -------------------------
async def get_admin_activity_log(admin_user_id: str, limit: int = 100) -> Dict[str, Any]:
    """Get recent admin actions. Admin only."""
    try:
        if not await check_user_admin_status(admin_user_id):
            return {"success": False, "error": "Admin access required"}
        
        # This would require a separate admin_logs collection
        # For now, return empty - you can implement later if needed
        return {
            "success": True,
            "activities": [],
            "message": "Activity logging not implemented yet"
        }
    except Exception as e:
        return {"success": False, "error": f"Error fetching activity log: {e}"}