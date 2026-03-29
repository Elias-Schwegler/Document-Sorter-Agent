from pydantic import BaseModel


class TelegramAuthStart(BaseModel):
    phone: str = ""


class TelegramAuthVerify(BaseModel):
    code: str
    password: str | None = None


class TelegramStatus(BaseModel):
    authenticated: bool
    phone: str = ""


class TelegramMessage(BaseModel):
    message_id: int
    date: str
    media_type: str | None = None
    filename: str | None = None
    file_size: int | None = None
    caption: str | None = None
    selected: bool = False


class TelegramFetchRequest(BaseModel):
    message_ids: list[int] | None = None
    limit: int = 50
    offset_date: str | None = None


class TelegramFetchResponse(BaseModel):
    messages: list[TelegramMessage]
    total: int
