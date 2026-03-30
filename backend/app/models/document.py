from pydantic import BaseModel
from datetime import datetime


class DocumentMetadata(BaseModel):
    doc_id: str
    filename: str
    original_filename: str
    folder: str = ""
    file_path: str = ""
    file_type: str = ""
    file_size: int = 0
    page_count: int = 0
    ingested_at: str = ""
    source: str = "upload"  # upload | telegram | watcher


class DocumentResponse(BaseModel):
    doc_id: str
    filename: str
    original_filename: str
    folder: str
    file_type: str
    file_size: int
    page_count: int
    ingested_at: str
    source: str
    text_preview: str = ""


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class SortResult(BaseModel):
    doc_id: str
    folder: str
    confidence: float
    is_new_folder: bool = False


class RenameResult(BaseModel):
    doc_id: str
    original_name: str
    suggested_name: str
    applied: bool = False


class RenameSuggestions(BaseModel):
    doc_id: str
    original_name: str
    suggestions: list[str] = []
    applied: bool = False

class NeedsRenameDocument(BaseModel):
    doc_id: str
    filename: str
    original_filename: str
    folder: str = ""
    file_type: str = ""
    file_size: int = 0
    ingested_at: str = ""
    text_preview: str = ""
    rename_suggestions: list[str] = []


class DuplicateInfo(BaseModel):
    doc_id: str
    existing_doc_id: str
    existing_filename: str
    similarity: float
