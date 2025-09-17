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
    
    query = {"location_id": location_id, "is_active": True}
    if category and category != "all":
        query["category"] = category
    
    skip = (page - 1) * limit
    
    try:
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
            conv["message_count"] = await count_conversation_messages(conv["id"])
            conv["is_unread"] = await has_unread_messages(conv["id"], user_id) if user_id else False
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
            result = serialize_doc(new_conversation)
            result["message_count"] = 0
            result["is_unread"] = False
            return result
        return None

    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        return None


async def get_conversation_by_id(conversation_id: str) -> Optional[Dict]:
    try:
        conversations = await fetch("conversations", {"id": conversation_id, "is_active": True})
        if not conversations:
            return None
        
        conversation = serialize_doc(conversations[0])
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
    query = {"conversation_id": conversation_id}
    
    if before:
        try:
            before_message = await fetch("messages", {"id": before})
            if before_message:
                before_timestamp = before_message[0]["timestamp"]
                query["timestamp"] = {"$lt": before_timestamp}
        except Exception:
            pass
    
    skip = (page - 1) * limit if not before else 0
    
    try:
        messages = await fetch(
            "messages",
            query,
            skip=skip,
            limit=limit,
            sort=[("timestamp", -1)]
        )
        
        if not messages:
            return []

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
        created_id = await insert("messages", new_message)
        if not created_id:
            return None
        await update_conversation_activity(conversation_id, now)
        return serialize_doc(new_message)

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

# -------------------------
# UTILITY FUNCTIONS
# -------------------------

async def count_conversation_messages(conversation_id: str) -> int:
    try:
        messages = await fetch("messages", {"conversation_id": conversation_id, "is_deleted": {"$ne": True}})
        return len(messages) if messages else 0
    except Exception:
        return 0


async def has_unread_messages(conversation_id: str, user_id: str) -> bool:
    try:
        user_activity = await fetch("user_conversation_activity", {
            "user_id": user_id, 
            "conversation_id": conversation_id
        })
        
        if not user_activity:
            return await count_conversation_messages(conversation_id) > 0
        
        last_read = user_activity[0].get("last_read")
        if not last_read:
            return True
        
        recent_messages = await fetch("messages", {
            "conversation_id": conversation_id,
            "timestamp": {"$gt": last_read},
            "author_id": {"$ne": user_id},
            "is_deleted": {"$ne": True}
        })
        
        return len(recent_messages) > 0 if recent_messages else False

    except Exception as e:
        logger.error(f"Error checking unread messages: {e}")
        return False


async def mark_conversation_read(conversation_id: str, user_id: str) -> bool:
    try:
        now = datetime.utcnow()
        existing = await fetch("user_conversation_activity", {
            "user_id": user_id, 
            "conversation_id": conversation_id
        })
        if existing:
            record_id = str(existing[0]["_id"])
            await update("user_conversation_activity", record_id, {"last_read": now, "updated_at": now})
        else:
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
    try:
        conversations = await fetch("conversations", {"id": conversation_id, "is_active": True})
        if not conversations:
            return False
        record_id = str(conversations[0]["_id"])
        await update("conversations", record_id, {"last_activity": activity_time, "updated_at": activity_time})
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

async def delete_conversation_by_id(conversation_id: str, user_id: str) -> bool:
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
    try:
        messages = await fetch("messages", {"id": message_id, "author_id": user_id, "is_deleted": {"$ne": True}})
        if not messages:
            return False
        record_id = str(messages[0]["_id"])
        await update("messages", record_id, {"is_deleted": True, "deleted_at": datetime.utcnow()})
        return True
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return False
