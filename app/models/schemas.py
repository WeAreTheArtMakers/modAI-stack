from pydantic import BaseModel, ConfigDict, EmailStr, Field
class RegisterRequest(BaseModel): email: EmailStr; password: str = Field(min_length=8, max_length=128)
class LoginRequest(RegisterRequest): pass
class TokenResponse(BaseModel): access_token: str; refresh_token: str; token_type: str = "bearer"
class ChatRequest(BaseModel): prompt: str = Field(min_length=1, max_length=12000)
class ChatResponse(BaseModel): answer: str
class Source(BaseModel):
    document: str
    score: float
    document_id: int | None = None
    chunk_index: int | None = None
    text: str | None = None
class RagResponse(BaseModel): answer: str; sources: list[Source]
class RagRequest(BaseModel): question: str = Field(min_length=1, max_length=12000)
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; filename: str
