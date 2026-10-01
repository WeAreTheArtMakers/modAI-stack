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
class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=20)
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; filename: str; index_status: str = "ready"; knowledge_base_id: int | None = None
class KnowledgeBaseCreate(BaseModel): name: str = Field(min_length=1, max_length=150); description: str | None = Field(default=None, max_length=2000)
class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; workspace_id: int; name: str; slug: str; description: str | None = None
