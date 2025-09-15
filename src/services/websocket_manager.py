from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Location-level connections: location_id -> list of websockets
        self.location_connections: Dict[str, List[WebSocket]] = {}
        
        # Conversation-level connections: conversation_id -> list of websockets
        self.conversation_connections: Dict[str, List[WebSocket]] = {}
        
        # User tracking: websocket -> user_id mapping
        self.websocket_users: Dict[WebSocket, str] = {}
        
        # Active users per conversation for typing indicators
        self.conversation_users: Dict[str, Set[str]] = {}

    # -------------------------
    # LOCATION-LEVEL CONNECTIONS
    # -------------------------
    
    async def connect_to_location(self, websocket: WebSocket, location_id: str, user_id: str = None):
        """Connect a user to location-level updates (new conversations, activity)"""
        await websocket.accept()
        
        if location_id not in self.location_connections:
            self.location_connections[location_id] = []
        
        self.location_connections[location_id].append(websocket)
        
        if user_id:
            self.websocket_users[websocket] = user_id
        
        logger.info(f"User {user_id} connected to location {location_id}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "location_id": location_id,
            "message": "Connected to location updates"
        })

    async def disconnect_from_location(self, websocket: WebSocket, location_id: str):
        """Disconnect user from location updates"""
        if location_id in self.location_connections:
            if websocket in self.location_connections[location_id]:
                self.location_connections[location_id].remove(websocket)
                
                # Clean up empty location
                if not self.location_connections[location_id]:
                    del self.location_connections[location_id]
        
        # Clean up user mapping
        if websocket in self.websocket_users:
            user_id = self.websocket_users.pop(websocket)
            logger.info(f"User {user_id} disconnected from location {location_id}")

    async def broadcast_to_location(self, location_id: str, message: dict, exclude_websocket: WebSocket = None):
        """Broadcast message to all users connected to a location"""
        if location_id not in self.location_connections:
            return

        # Create a copy to avoid modification during iteration
        connections = self.location_connections[location_id].copy()
        disconnected = []

        for websocket in connections:
            if websocket == exclude_websocket:
                continue
                
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to websocket in location {location_id}: {e}")
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect_from_location(websocket, location_id)

    # -------------------------
    # CONVERSATION-LEVEL CONNECTIONS
    # -------------------------
    
    async def connect_to_conversation(self, websocket: WebSocket, conversation_id: str, user_id: str = None):
        """Connect a user to conversation-level updates (messages, typing)"""
        await websocket.accept()
        
        if conversation_id not in self.conversation_connections:
            self.conversation_connections[conversation_id] = []
            self.conversation_users[conversation_id] = set()
        
        self.conversation_connections[conversation_id].append(websocket)
        
        if user_id:
            self.websocket_users[websocket] = user_id
            self.conversation_users[conversation_id].add(user_id)
        
        logger.info(f"User {user_id} connected to conversation {conversation_id}")
        
        # Send welcome message with active users count
        await websocket.send_json({
            "type": "connected",
            "conversation_id": conversation_id,
            "active_users": len(self.conversation_users.get(conversation_id, set())),
            "message": "Connected to conversation"
        })
        
        # Notify others about new user joining
        await self.broadcast_to_conversation(conversation_id, {
            "type": "user_joined",
            "user_id": user_id,
            "active_users": len(self.conversation_users.get(conversation_id, set()))
        }, exclude_websocket=websocket)

    async def disconnect_from_conversation(self, websocket: WebSocket, conversation_id: str):
        """Disconnect user from conversation updates"""
        user_id = self.websocket_users.get(websocket)
        
        if conversation_id in self.conversation_connections:
            if websocket in self.conversation_connections[conversation_id]:
                self.conversation_connections[conversation_id].remove(websocket)
                
                # Clean up empty conversation
                if not self.conversation_connections[conversation_id]:
                    del self.conversation_connections[conversation_id]
                    if conversation_id in self.conversation_users:
                        del self.conversation_users[conversation_id]
        
        # Remove user from active users
        if conversation_id in self.conversation_users and user_id:
            self.conversation_users[conversation_id].discard(user_id)
        
        # Clean up user mapping
        if websocket in self.websocket_users:
            self.websocket_users.pop(websocket)
            logger.info(f"User {user_id} disconnected from conversation {conversation_id}")
        
        # Notify others about user leaving
        if user_id:
            await self.broadcast_to_conversation(conversation_id, {
                "type": "user_left",
                "user_id": user_id,
                "active_users": len(self.conversation_users.get(conversation_id, set()))
            })

    async def broadcast_to_conversation(self, conversation_id: str, message: dict, exclude_websocket: WebSocket = None):
        """Broadcast message to all users in a conversation"""
        if conversation_id not in self.conversation_connections:
            return

        # Create a copy to avoid modification during iteration
        connections = self.conversation_connections[conversation_id].copy()
        disconnected = []

        for websocket in connections:
            if websocket == exclude_websocket:
                continue
                
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to websocket in conversation {conversation_id}: {e}")
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect_from_conversation(websocket, conversation_id)

    # -------------------------
    # UTILITY METHODS
    # -------------------------
    
    def get_active_users_in_conversation(self, conversation_id: str) -> int:
        """Get count of active users in a conversation"""
        return len(self.conversation_users.get(conversation_id, set()))
    
    def get_active_users_in_location(self, location_id: str) -> int:
        """Get count of active users in a location"""
        return len(self.location_connections.get(location_id, []))
    
    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected users (admin feature)"""
        # Broadcast to all locations
        for location_id in self.location_connections:
            await self.broadcast_to_location(location_id, message)
    
    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring"""
        return {
            "total_location_connections": sum(len(conns) for conns in self.location_connections.values()),
            "total_conversation_connections": sum(len(conns) for conns in self.conversation_connections.values()),
            "active_locations": len(self.location_connections),
            "active_conversations": len(self.conversation_connections),
            "total_users": len(self.websocket_users)
        }

# Global connection manager instance
manager = ConnectionManager()

# -------------------------
# BACKGROUND TASKS
# -------------------------

async def cleanup_stale_connections():
    """Background task to clean up stale connections"""
    while True:
        try:
            # This could be enhanced to ping connections and remove stale ones
            await asyncio.sleep(300)  # Check every 5 minutes
            
            # Log current stats
            stats = manager.get_connection_stats()
            logger.info(f"Connection stats: {stats}")
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)