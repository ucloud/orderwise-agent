"""Session manager for MCP takeover state persistence."""

import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
from queue import Queue, Empty


@dataclass
class TaskState:
    """Task state for session recovery."""
    device_id: str
    app_name: str
    task: str
    model_config: Dict[str, Any]
    agent_config: Dict[str, Any]
    keyword: str
    task_id: str
    user_id: str
    app_package: Optional[str] = None
    created_at: float = 0.0
    
    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


class SessionManager:
    """Thread-safe session manager for MCP takeover state."""
    
    def __init__(self, ttl_seconds: float = 3600.0):
        """
        Initialize session manager.
        
        Args:
            ttl_seconds: Time-to-live for sessions in seconds (default: 1 hour)
        """
        self._sessions: Dict[str, TaskState] = {}
        self._reply_queues: Dict[str, Queue] = {}  # session_id -> Queue for user reply
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
    
    def save(self, session_id: str, state: TaskState) -> None:
        """Save task state for session recovery."""
        with self._lock:
            self._sessions[session_id] = state
            # Create reply queue if not exists
            if session_id not in self._reply_queues:
                self._reply_queues[session_id] = Queue()
    
    def get(self, session_id: str) -> Optional[TaskState]:
        """Get task state by session_id. Returns None if not found or expired."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            
            # Check TTL
            if time.time() - state.created_at > self._ttl:
                del self._sessions[session_id]
                if session_id in self._reply_queues:
                    del self._reply_queues[session_id]
                return None
            
            return state
    
    def wait_for_reply(self, session_id: str, timeout: Optional[float] = None) -> Optional[str]:
        """Wait for user reply. Returns reply string or None if timeout."""
        with self._lock:
            queue = self._reply_queues.get(session_id)
            if queue is None:
                return None
        
        try:
            return queue.get(timeout=timeout)
        except Empty:
            return None
    
    def send_reply(self, session_id: str, reply: str) -> bool:
        """Send user reply to waiting process. Returns True if sent, False if queue not found."""
        with self._lock:
            queue = self._reply_queues.get(session_id)
            if queue is None:
                return False
        
        queue.put(reply)
        return True
    
    def delete(self, session_id: str) -> bool:
        """Delete session. Returns True if deleted, False if not found."""
        with self._lock:
            deleted = False
            if session_id in self._sessions:
                del self._sessions[session_id]
                deleted = True
            if session_id in self._reply_queues:
                del self._reply_queues[session_id]
            return deleted
    
    def cleanup_expired(self) -> int:
        """Clean up expired sessions. Returns number of sessions cleaned."""
        with self._lock:
            now = time.time()
            expired = [
                sid for sid, state in self._sessions.items()
                if now - state.created_at > self._ttl
            ]
            for sid in expired:
                del self._sessions[sid]
                if sid in self._reply_queues:
                    del self._reply_queues[sid]
            return len(expired)
    
    def count(self) -> int:
        """Get current number of active sessions."""
        with self._lock:
            return len(self._sessions)


# Global session manager instance
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Get global session manager instance."""
    return _session_manager

