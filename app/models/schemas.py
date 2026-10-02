from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
class RegisterRequest(BaseModel): email: EmailStr; password: str = Field(min_length=8, max_length=128)
class LoginRequest(RegisterRequest): pass
class RefreshRequest(BaseModel): refresh_token: str = Field(min_length=1)
class TokenResponse(BaseModel): access_token: str; token_type: str = "bearer"
class OrganizationAccess(BaseModel):
    id: int
    name: str
    slug: str
    membership_role: str

class WorkspaceResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str
    membership_role: str

class CurrentUserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    organizations: list[OrganizationAccess]
    workspaces: list[WorkspaceResponse]
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
    id: int
    filename: str
    index_status: str = "ready"
    index_error: str | None = None
    knowledge_base_id: int | None = None
    file_size: int = 0
    active_version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
class KnowledgeBaseCreate(BaseModel): name: str = Field(min_length=1, max_length=150); description: str | None = Field(default=None, max_length=2000)
class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workspace_id: int
    name: str
    slug: str
    description: str | None = None
    membership_role: str | None = None


class ModelProviderResponse(BaseModel):
    provider: str
    endpoint: str
    ready: bool


class ManagedModelResponse(BaseModel):
    provider: str
    name: str
    size: int | None = None
    modified_at: str | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    capabilities: list[str] | None = None


class GenerationModelStatus(BaseModel):
    provider: str
    configured_model: str
    ready: bool
    running: bool


class EmbeddingModelStatus(BaseModel):
    configured_model: str
    source: str
    download_allowed: bool
    cache_available: bool | None = None
    ready: bool
    status: str


class ModelSystemStatus(BaseModel):
    providers: list[ModelProviderResponse]
    generation: GenerationModelStatus
    embedding: EmbeddingModelStatus


class ModelPullRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class WebSocketTicketRequest(BaseModel):
    scope: str = Field(pattern="^(chat|rag|indexing|models_pull)$")
    workspace_id: int | None = Field(default=None, gt=0)


class WebSocketTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime | None = None
    actor_user_id: int | None = None
    organization_id: int | None = None
    workspace_id: int | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    success: bool
    metadata_json: dict = Field(default_factory=dict)
    request_id: str | None = None
    source_ip: str | None = None
