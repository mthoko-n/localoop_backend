from typing import Optional, List, Dict
from datetime import datetime
from bson import ObjectId
from src.utils.db import fetch, insert, update, delete
from src.utils.serialize_helper import serialize_doc
import uuid
import logging

logger = logging.getLogger(__name__)

# -------------------------
# CONVERSATION SERVICES
# -------------------------

async def get_location_conversations(
    location_id: str, 
    category: Optional[str] = None, 
    page: int = 1, 
    limit: int = 20,
    user_id: Optional[str] = None
) -> Optional[List[Dict]]:
    """Get conversations for a location with optional filtering"""
    
    # Build query
    query = {"location_id": location_id, "is_active": True}
    if category and category != "all":
        query["category"] = category
    
    # Calculate pagination
    skip = (page - 1) * limit
    
    try:
        # Get conversations with pagination, sorted by last activity
        conversations = await fetch(
            "conversations",
            query,
            skip=skip,
            limit=limit,
            sort=[("last_activity", -1), ("created_at", -1)]
        )
        
        if not conversations:
            return []

        formatted = []
        for conv in conversations:
            conv = serialize_doc(conv)
            
            # Get latest message count from messages collection
            message_count = await count_conversation_messages(conv["id"])
            conv["message_count"] = message_count
            
            # Check if user has unread messages (if user_id provided)
            if user_id:
                conv["is_unread"] = await has_unread_messages(conv["id"], user_id)
            else:
                conv["is_unread"] = False
            
            formatted.append(conv)

        return formatted

    except Exception as e:
        logger.error(f"Error fetching conversations for location {location_id}: {e}")
        return None


async def create_conversation(
    location_id: str, 
    title: str, 
    body: str, 
    category: str, 
    author_id: str
) -> Optional[Dict]:
    """Create a new conversation"""
    
    # Get author info (you might want to fetch from users table)
    author_info = await get_user_info(author_id)
    author_name = author_info.get("name", "Unknown User") if author_info else "Unknown User"
    
    conversation_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    new_conversation = {
        "id": conversation_id,
        "location_id": location_id,
        "title": title.strip(),
        "body": body.strip(),
        "category": category,
        "author_id": author_id,
        "author_name": author_name,
        "created_at": now,
        "last_activity": now,
        "is_active": True,
        "is_pinned": False,
        "view_count": 0
    }

    try:
        created_id = await insert("conversations", new_conversation)
        if created_id:
            # Return serialized conversation
            result = serialize_doc(new_conversation)
            result["message_count"] = 0
            result["is_unread"] = False
            return result
        return None

    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        return None


async def get_conversation_by_id(conversation_id: str) -> Optional[Dict]:
    """Get a single conversation by ID"""
    try:
        conversations = await fetch("conversations", {"id": conversation_id, "is_active": True})
        if not conversations:
            return None
        
        conversation = serialize_doc(conversations[0])
        
        # Get message count
        conversation["message_count"] = await count_conversation_messages(conversation_id)
        
        return conversation

    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None


# -------------------------
# MESSAGE SERVICES
# -------------------------

async def get_conversation_messages(
    conversation_id: str, 
    page: int = 1, 
    limit: int = 50, 
    before: Optional[str] = None
) -> Optional[List[Dict]]:
    """Get messages for a conversation with pagination"""
    
    # Build query
    query = {"conversation_id": conversation_id}
    
    # Cursor-based pagination if 'before' is provided
    if before:
        try:
            # If before is a message ID, get messages before that timestamp
            before_message = await fetch("messages", {"id": before})
            if before_message:
                before_timestamp = before_message[0]["timestamp"]
                query["timestamp"] = {"$lt": before_timestamp}
        except Exception:
            # If before parsing fails, use offset-based pagination
            pass
    
    # Calculate skip for offset-based pagination
    skip = (page - 1) * limit if not before else 0
    
    try:
        messages = await fetch(
            "messages",
            query,
            skip=skip,
            limit=limit,
            sort=[("timestamp", -1)]  # Latest first, reverse in client
        )
        
        if not messages:
            return []

        # Serialize and reverse order (oldest first for chat display)
        formatted = [serialize_doc(msg) for msg in messages]
        formatted.reverse()
        
        return formatted

    except Exception as e:
        logger.error(f"Error fetching messages for conversation {conversation_id}: {e}")
        return None


async def send_message(
    conversation_id: str, 
    content: str, 
    author_id: str, 
    reply_to_id: Optional[str] = None
) -> Optional[Dict]:
    """Send a message to a conversation"""
    
    # Get author info
    author_info = await get_user_info(author_id)
    author_name = author_info.get("name", "Unknown User") if author_info else "Unknown User"
    
    message_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    new_message = {
        "id": message_id,
        "conversation_id": conversation_id,
        "content": content.strip(),
        "author_id": author_id,
        "author_name": author_name,
        "timestamp": now,
        "is_edited": False,
        "reply_to_id": reply_to_id,
        "is_deleted": False
    }

    try:
        # Insert message
        created_id = await insert("messages", new_message)
        if not created_id:
            return None
        
        # Update conversation last_activity
        await update_conversation_activity(conversation_id, now)
        
        # Return serialized message
        return serialize_doc(new_message)

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None


# -------------------------
# UTILITY FUNCTIONS
# -------------------------

async def count_conversation_messages(conversation_id: str) -> int:
    """Count messages in a conversation"""
    try:
        messages = await fetch("messages", {"conversation_id": conversation_id, "is_deleted": {"$ne": True}})
        return len(messages) if messages else 0
    except Exception:
        return 0


async def has_unread_messages(conversation_id: str, user_id: str) -> bool:
    """Check if user has unread messages in conversation"""
    try:
        # Get user's last read timestamp for this conversation
        user_activity = await fetch("user_conversation_activity", {
            "user_id": user_id, 
            "conversation_id": conversation_id
        })
        
        if not user_activity:
            # No activity record means all messages are unread
            message_count = await count_conversation_messages(conversation_id)
            return message_count > 0
        
        last_read = user_activity[0].get("last_read")
        if not last_read:
            return True
        
        # Check if there are messages after last read time
        recent_messages = await fetch("messages", {
            "conversation_id": conversation_id,
            "timestamp": {"$gt": last_read},
            "author_id": {"$ne": user_id},  # Don't count own messages
            "is_deleted": {"$ne": True}
        })
        
        return len(recent_messages) > 0 if recent_messages else False

    except Exception as e:
        logger.error(f"Error checking unread messages: {e}")
        return False


async def mark_conversation_read(conversation_id: str, user_id: str) -> bool:
    """Mark conversation as read for user"""
    try:
        now = datetime.utcnow()
        
        # Update or insert user activity record
        existing = await fetch("user_conversation_activity", {
            "user_id": user_id, 
            "conversation_id": conversation_id
        })
        
        if existing:
            # Update existing record
            record_id = str(existing[0]["_id"])
            await update("user_conversation_activity", record_id, {
                "last_read": now,
                "updated_at": now
            })
        else:
            # Create new record
            await insert("user_conversation_activity", {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "last_read": now,
                "created_at": now,
                "updated_at": now
            })
        
        return True

    except Exception as e:
        logger.error(f"Error marking conversation read: {e}")
        return False


async def update_conversation_activity(conversation_id: str, activity_time: datetime) -> bool:
    """Update conversation's last activity time"""
    try:
        conversations = await fetch("conversations", {"id": conversation_id, "is_active": True})
        if not conversations:
            return False
        
        record_id = str(conversations[0]["_id"])
        await update("conversations", record_id, {
            "last_activity": activity_time,
            "updated_at": activity_time
        })
        
        return True

    except Exception as e:
        logger.error(f"Error updating conversation activity: {e}")
        return False


async def get_user_info(user_id: str) -> Optional[Dict]:
    try:
        users = await fetch("users", {"_id": ObjectId(user_id)})
    except Exception:
        return None

    if users:
        user = serialize_doc(users[0])
        return {
            "id": str(user.get("_id")),
            "name": f"{user.get('display_name', '')} {user.get('last_name', '')}".strip() or "Unknown User",
            "email": user.get("email", ""),
            "avatar_url": user.get("avatar_url")
        }
    return None



# -------------------------
# ADMIN/MODERATION FUNCTIONS
# -------------------------

async def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """Soft delete a conversation (mark as inactive)"""
    try:
        conversations = await fetch("conversations", {"id": conversation_id, "author_id": user_id, "is_active": True})
        if not conversations:
            return False
        
        record_id = str(conversations[0]["_id"])
        await update("conversations", record_id, {
            "is_active": False,
            "deleted_at": datetime.utcnow()
        })
        
        return True

    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return False


async def delete_message(message_id: str, user_id: str) -> bool:
    """Soft delete a message"""
    try:
        messages = await fetch("messages", {"id": message_id, "author_id": user_id, "is_deleted": {"$ne": True}})
        if not messages:
            return False
        
        record_id = str(messages[0]["_id"])
        await update("messages", record_id, {
            "is_deleted": True,
            "deleted_at": datetime.utcnow()
        })
        
        return True

    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return False