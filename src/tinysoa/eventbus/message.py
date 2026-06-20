from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
import json


@dataclass
class EventMessage:
    """Event message for the internal event bus.
    
    Supports serialization and carries metadata for routing and observability.
    """
    
    topic: str
    payload: Any
    message_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: Dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json"
    
    # Optional tracing/correlation
    correlation_id: Optional[UUID] = None
    trace_id: Optional[UUID] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "topic": self.topic,
            "payload": self.payload,
            "message_id": str(self.message_id),
            "timestamp": self.timestamp.isoformat(),
            "headers": self.headers,
            "content_type": self.content_type,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "trace_id": str(self.trace_id) if self.trace_id else None,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventMessage":
        """Deserialize from dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc)
        message_id = UUID(data["message_id"]) if "message_id" in data else uuid4()
        correlation_id = UUID(data["correlation_id"]) if data.get("correlation_id") else None
        trace_id = UUID(data["trace_id"]) if data.get("trace_id") else None
        
        return cls(
            topic=data["topic"],
            payload=data["payload"],
            message_id=message_id,
            timestamp=timestamp,
            headers=data.get("headers", {}),
            content_type=data.get("content_type", "application/json"),
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "EventMessage":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
