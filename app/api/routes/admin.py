from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.api.dependencies import require_admin
from app.application.documents.ingestion import DocumentIngestionService, DocumentParseError, UnsupportedDocumentFormat
from app.domain.models import (
    AdminOverviewResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentUploadResponse,
    EvaluationReport,
    EvaluationRunRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    RuntimeConfigResponse,
    RuntimeConfigUpdate,
    TenantConfigUpdate,
    TenantSummaryResponse,
)


router = APIRouter(dependencies=[Depends(require_admin)])
ingestion_service = DocumentIngestionService()


@router.post("/evaluations/run", response_model=EvaluationReport)
async def run_evaluation(payload: EvaluationRunRequest, request: Request) -> EvaluationReport:
    service = request.app.state.container.evaluation_service
    cases = payload.cases if payload.cases is not None else service.load_default_cases()
    try:
        return await service.run(cases, payload.judge)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(request: Request) -> AdminOverviewResponse:
    service = request.app.state.container.knowledge_base_service
    knowledge_bases = service.list_all()
    return AdminOverviewResponse(
        tenant_count=len(service.list_tenants()),
        knowledge_base_count=len(knowledge_bases),
        document_count=len(service.list_all_documents()),
        enabled_knowledge_base_count=sum(item.enabled for item in knowledge_bases),
    )


@router.get("/tenants", response_model=list[TenantSummaryResponse])
async def list_tenants(request: Request) -> list[TenantSummaryResponse]:
    return request.app.state.container.knowledge_base_service.list_tenants()


@router.patch("/tenants/{tenant_id}", response_model=TenantSummaryResponse)
async def update_tenant(tenant_id: str, payload: TenantConfigUpdate, request: Request) -> TenantSummaryResponse:
    try:
        result = request.app.state.container.knowledge_base_service.update_tenant(tenant_id, payload)
        audit = request.app.state.container.audit_repository
        if audit is not None:
            audit.record("admin", "tenant.update", "tenant", tenant_id, tenant_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseResponse])
async def list_all_knowledge_bases(request: Request) -> list[KnowledgeBaseResponse]:
    return request.app.state.container.knowledge_base_service.list_all()


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(payload: KnowledgeBaseCreate, request: Request) -> KnowledgeBaseResponse:
    try:
        result = request.app.state.container.knowledge_base_service.create_knowledge_base(payload)
        audit = request.app.state.container.audit_repository
        if audit is not None:
            audit.record("admin", "knowledge_base.create", "knowledge_base", payload.knowledge_base_id, payload.tenant_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
    request: Request,
) -> KnowledgeBaseResponse:
    try:
        result = request.app.state.container.knowledge_base_service.update_knowledge_base(knowledge_base_id, payload)
        audit = request.app.state.container.audit_repository
        if audit is not None:
            audit.record("admin", "knowledge_base.update", "knowledge_base", knowledge_base_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentResponse])
async def list_all_documents(request: Request) -> list[DocumentResponse]:
    return request.app.state.container.knowledge_base_service.list_all_documents()


@router.post("/documents/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    knowledge_base_id: str = Form(...),
    title: str | None = Form(default=None),
    category: str = Form(default="未分类"),
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    container = request.app.state.container
    if container.knowledge_base_service.get(knowledge_base_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    payload = await file.read()
    if len(payload) > container.settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds the {container.settings.max_upload_bytes} byte upload limit",
        )
    try:
        parsed = ingestion_service.parse(file.filename or "uploaded-file", payload, file.content_type)
    except UnsupportedDocumentFormat as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    document = container.knowledge_base_service.add_document(
        knowledge_base_id,
        payload=DocumentCreate(
            title=title.strip() if title and title.strip() else parsed.title,
            content=parsed.content,
            metadata={**parsed.metadata, "category": category},
        ),
    )
    index_status = "ready"
    task_id = None
    if container.settings.task_queue.lower() == "redis":
        task_id = await container.task_queue.enqueue(
            "index_document",
            {"knowledge_base_id": knowledge_base_id, "document_id": document.document_id},
        )
        index_status = "queued"
    else:
        await container.rag_service.index_document(document)
    if container.audit_repository is not None:
        container.audit_repository.record(
            "admin", "document.upload", "document", document.document_id, knowledge_base_id,
            {"filename": file.filename, "parser": parsed.metadata["parser"]},
        )
    return DocumentUploadResponse(
        **document.model_dump(),
        parser=parsed.metadata["parser"],
        source_filename=parsed.metadata["source_filename"],
        index_status=index_status,
        task_id=task_id,
    )


@router.delete("/documents/{knowledge_base_id}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(knowledge_base_id: str, document_id: str, request: Request) -> None:
    container = request.app.state.container
    deleted = container.knowledge_base_service.delete_document(knowledge_base_id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    await container.rag_service.delete_document(knowledge_base_id, document_id)
    if container.audit_repository is not None:
        container.audit_repository.record("admin", "document.delete", "document", document_id, knowledge_base_id)


@router.get("/runtime", response_model=RuntimeConfigResponse)
async def runtime_config(request: Request) -> RuntimeConfigResponse:
    return request.app.state.container.runtime_config()


@router.patch("/runtime", response_model=RuntimeConfigResponse)
async def update_runtime(payload: RuntimeConfigUpdate, request: Request) -> RuntimeConfigResponse:
    try:
        return await request.app.state.container.update_runtime(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
