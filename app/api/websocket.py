from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import Dict, List, Optional
import json
import asyncio
from app.auth.security import decode_access_token
from jose import JWTError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.import_progress: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)

    def disconnect(self, websocket: WebSocket, client_id: str):
        if client_id in self.active_connections:
            self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]

    async def send_personal_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                try:
                    await connection.send_text(message)
                except:
                    pass

    async def broadcast_to_user(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            message_text = json.dumps(message)
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message_text)
                except:
                    pass

    def update_import_progress(self, import_id: str, progress: dict):
        self.import_progress[import_id] = progress

    def get_import_progress(self, import_id: str):
        return self.import_progress.get(import_id, {})

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    # Verify token
    if not token:
        logger.warning("WebSocket connection attempt without token")
        await websocket.close(code=1008, reason="Missing token")
        return
        
    # Decode token without raising HTTPException
    payload = decode_access_token(token)
    if not payload:
        logger.warning("WebSocket connection attempt with invalid token")
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    user_id = payload.get("sub")
    if not user_id:
        logger.warning("WebSocket token missing user ID")
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    logger.info(f"WebSocket connection established for user {user_id}")
    
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
            
            # Send current import progress if requested
            elif data.startswith("get_progress:"):
                import_id = data.split(":", 1)[1]
                progress = manager.get_import_progress(import_id)
                await websocket.send_text(json.dumps({
                    "type": "import_progress",
                    "import_id": import_id,
                    "progress": progress
                }))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

# Helper function to send import progress updates
async def send_import_update(user_id: str, source_id: int, status: str, progress: dict):
    update = {
        "type": "import_update",
        "source_id": source_id,
        "status": status,  # 'started', 'progress', 'completed', 'failed'
        "progress": progress
    }
    
    await manager.broadcast_to_user(update, user_id)