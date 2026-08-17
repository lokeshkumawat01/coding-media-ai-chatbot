"""
Pydantic schemas for the /chat endpoint request and response.
"""

from pydantic import BaseModel, Field
from typing import Optional


class ChatMessage(BaseModel):
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(
        ..., description="Unique identifier for this chat session/visitor"
    )
    phone_number: Optional[str] = Field(
        default=None, description="Client's phone number, if already known"
    )


class ChatResponse(BaseModel):
    reply: str
    session_id: str
