from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from src.services.chat_services import (
    get_location_conversations,
    create_conversation,
    get_conversation_messages,
    send_message,
    get_conversation_by_id
)
from src.utils.dependencies import get_current_user
from src.services.websocket_manager import manager

router = APIRouter(prefix="/chat", tags=["Chat"])

# -------------------------
# REQUEST SCHEMAS
# -------------------------
class CreateConversationSchema(BaseModel):
    title: str
    body: str
    category: str  # water, electricity, maintenance, crime, places, general

class SendMessageSchema(BaseModel):
    content: str
    reply_to_id: Optional[str] = None

# -------------------------
# RESPONSE SCHEMAS
# -------------------------
class ConversationSchema(BaseModel):
    id: str
    location_id: str
    title: str
    body: str
    category: str
    author_id: str
    author_name: str
    created_at: str
    last_activity: str
    message_count: int
    is_unread: bool

class MessageSchema(BaseModel):
    id: str
    conversation_id: str
    content: str
    author_id: str
    author_name: str
    timestamp: str
    is_edited: bool
    reply_to_id: Optional[str] = None

# -------------------------
# REST API ROUTES (for refresh/initial loading)
# -------------------------

@router.get("/locations/{location_id}/conversations", response_model=dict)
async def get_conversations(
    location_id: str,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user_id: str = Depends(get_current_user)
):
    """Get conversations for a location with optional category filter"""
    conversations = await get_location_conversations(
        location_id=location_id, 
        category=category, 
        page=page, 
        limit=limit,
        user_id=user_id
    )
    
    return {
        "conversations": conversations or [],
        "page": page,
        "limit": limit,
        "has_more": len(conversations or []) == limit
    }

@router.post("/locations/{location_id}/conversations", response_model=dict)
async def create_new_conversation(
    location_id: str,
    data: CreateConversationSchema,
    user_id: str = Depends(get_current_user)
):
    """Create a new conversation in a location"""
    conversation = await create_conversation(
        location_id=location_id,
        title=data.title,
        body=data.body,
        category=data.category,
        author_id=user_id
    )
    
    if not conversation:
        raise HTTPException(status_code=400, detail="Failed to create conversation")
    
    # Notify WebSocket clients about new conversation
    await manager.broadcast_to_location(location_id, {
        "type": "new_conversation",
        "conversation": conversation
    })
    
    return {"message": "Conversation created successfully", "conversation": conversation}

@router.get("/conversations/{conversation_id}/messages", response_model=dict)
async def get_messages(
    conversation_id: str,
    page: int = 1,
    limit: int = 50,
    before: Optional[str] = None,  # Message ID for cursor-based pagination
    user_id: str = Depends(get_current_user)
):
    """Get messages for a conversation with pagination"""
    # Verify user has access to this conversation
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = await get_conversation_messages(
        conversation_id=conversation_id,
        page=page,
        limit=limit,
        before=before
    )
    
    return {
        "messages": messages or [],
        "conversation": conversation,
        "page": page,
        "limit": limit,
        "has_more": len(messages or []) == limit
    }

@router.post("/conversations/{conversation_id}/messages", response_model=dict)
async def send_message_to_conversation(
    conversation_id: str,
    data: SendMessageSchema,
    user_id: str = Depends(get_current_user)
):
    """Send a message to a conversation"""
    # Verify conversation exists and user has access
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    message = await send_message(
        conversation_id=conversation_id,
        content=data.content,
        author_id=user_id,
        reply_to_id=data.reply_to_id
    )
    
    if not message:
        raise HTTPException(status_code=400, detail="Failed to send message")
    
    # Broadcast to WebSocket clients
    await manager.broadcast_to_conversation(conversation_id, {
        "type": "new_message",
        "message": message
    })
    
    # Also notify location subscribers about conversation activity
    await manager.broadcast_to_location(conversation["location_id"], {
        "type": "conversation_activity",
        "conversation_id": conversation_id,
        "last_activity": message["timestamp"]
    })
    
    return {"message": "Message sent successfully", "data": message}

# -------------------------
# WEBSOCKET ROUTES (for real-time updates)
# -------------------------

@router.websocket("/locations/{location_id}/ws")
async def location_websocket(websocket: WebSocket, location_id: str):
    """WebSocket for location-level updates (new conversations, activity)"""
    await manager.connect_to_location(websocket, location_id)
    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await websocket.receive_text()
            # Handle ping/pong or other control messages
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect_from_location(websocket, location_id)

@router.websocket("/conversations/{conversation_id}/ws")
async def conversation_websocket(websocket: WebSocket, conversation_id: str):
    """WebSocket for conversation-level updates (new messages, typing indicators)"""
    await manager.connect_to_conversation(websocket, conversation_id)
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            if data.get("type") == "typing":
                # Broadcast typing indicator to other users
                await manager.broadcast_to_conversation(conversation_id, {
                    "type": "typing",
                    "user_id": data.get("user_id"),
                    "user_name": data.get("user_name"),
                    "is_typing": data.get("is_typing", False)
                }, exclude_websocket=websocket)
            
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        await manager.disconnect_from_conversation(websocket, conversation_id)

# -------------------------
# UTILITY ROUTES
# -------------------------

@router.get("/conversations/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(conversation_id: str, user_id: str = Depends(get_current_user)):
    """Get a single conversation by ID"""
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.get("/categories", response_model=List[dict])
async def get_conversation_categories():
    """Get available conversation categories"""
    return [
        {"id": "water", "name": "Water", "icon": "💧", "color": "#2196F3"},
        {"id": "electricity", "name": "Electricity", "icon": "⚡", "color": "#FF9800"},
        {"id": "maintenance", "name": "Maintenance", "icon": "🔧", "color": "#4CAF50"},
        {"id": "crime", "name": "Crime & Safety", "icon": "🚨", "color": "#F44336"},
        {"id": "places", "name": "Local Places", "icon": "📍", "color": "#9C27B0"},
        {"id": "general", "name": "General", "icon": "💬", "color": "#607D8B"}
    ]