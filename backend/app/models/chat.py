from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str
    sources: list[dict] | None = None
    pinned_docs: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    pinned_doc_ids: list[str] | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]


class SourceReference(BaseModel):
    doc_id: str
    filename: str
    folder: str
    relevance_score: float
    snippet: str
