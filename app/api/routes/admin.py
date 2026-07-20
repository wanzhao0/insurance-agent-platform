"""管理后台 API：用户、知识库、文档、配置版本和运维记录。"""

import asyncio
import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.api.dependencies import require_admin
from app.application.documents.ingestion import (
    DocumentIngestionService,
    DocumentParseError,
    UnsupportedDocumentFormat,
)
from app.domain.models import (
    AdminOverviewResponse,
    AuditLogResponse,
    ConfigVersionCreate,
    ConfigVersionResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentUploadResponse,
    DomainPluginResponse,
    EvaluationReport,
    EvaluationRunRequest,
    EvaluationRunResponse,
    HandoffTicketResponse,
    HandoffTicketUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    RuntimeConfigResponse,
    RuntimeConfigUpdate,
    TaskJobResponse,
    TenantConfigUpdate,
    TenantSummaryResponse,
    UserContext,
    UserCreate,
    UserResponse,
    UserUpdate,
    WorkflowRunResponse,
)
from app.plugins.registry import registered_plugins


router = APIRouter(dependencies=[Depends(require_admin)])
ingestion_service = DocumentIngestionService()


async def read_limited_upload(file: UploadFile, max_bytes: int) -> bytes:
    """分块读取上传内容，在内存累积前强制执行大小上限。"""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"file exceeds the {max_bytes} byte upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def record_audit(
    container,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    tenant_id: str | None = None,
    details: dict | None = None,
) -> None:
    """将高风险后台变更写入审计仓库；未配置仓库时保持本地开发可用。"""
    if container.audit_repository is not None:
        await asyncio.to_thread(
            container.audit_repository.record,
            actor_id,
            action,
            resource_type,
            resource_id,
            tenant_id,
            details,
        )


def validate_user_scope(container, role: str, tenant_ids: list[str]) -> None:
    """防止普通用户被授予全租户范围，并拒绝不存在的租户 ID。"""
    if "*" in tenant_ids and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only administrators can access all tenants",
        )
    unknown = [
        tenant_id
        for tenant_id in tenant_ids
        if tenant_id != "*" and container.knowledge_base_service.tenant_config(tenant_id) is None
    ]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown tenant ids: {', '.join(unknown)}",
        )


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(request: Request) -> AdminOverviewResponse:
    service = request.app.state.container.knowledge_base_service
    knowledge_bases, tenants, documents = await asyncio.gather(
        asyncio.to_thread(service.list_all),
        asyncio.to_thread(service.list_tenants),
        asyncio.to_thread(service.list_all_documents),
    )
    return AdminOverviewResponse(
        tenant_count=len(tenants),
        knowledge_base_count=len(knowledge_bases),
        document_count=len(documents),
        enabled_knowledge_base_count=sum(item.enabled for item in knowledge_bases),
    )


@router.get("/plugins", response_model=list[DomainPluginResponse])
async def list_plugins() -> list[DomainPluginResponse]:
    return [
        DomainPluginResponse(
            plugin_id=plugin.plugin_id,
            name=plugin.name,
            version=plugin.version,
            workflow_version=plugin.workflow_version,
            workflow_steps=[step.name for step in plugin.workflow],
            tools=list(plugin.tool_names),
        )
        for plugin in registered_plugins()
    ]


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request) -> list[UserResponse]:
    return await asyncio.to_thread(request.app.state.container.auth_service.list_users)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> UserResponse:
    container = request.app.state.container
    validate_user_scope(container, payload.role, payload.tenant_ids)
    try:
        user = await asyncio.to_thread(container.auth_service.create_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit(container, actor.user_id, "user.create", "user", user.user_id)
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> UserResponse:
    container = request.app.state.container
    current_users = await asyncio.to_thread(container.auth_service.list_users)
    current = next((item for item in current_users if item.user_id == user_id), None)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    validate_user_scope(
        container,
        payload.role or current.role,
        payload.tenant_ids if payload.tenant_ids is not None else current.tenant_ids,
    )
    try:
        user = await asyncio.to_thread(container.auth_service.update_user, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await record_audit(container, actor.user_id, "user.update", "user", user_id)
    return user


@router.get("/config-versions", response_model=list[ConfigVersionResponse])
async def list_config_versions(
    request: Request,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> list[ConfigVersionResponse]:
    return await asyncio.to_thread(
        request.app.state.container.config_repository.list,
        scope_type,
        scope_id,
    )


@router.post(
    "/config-versions", response_model=ConfigVersionResponse, status_code=status.HTTP_201_CREATED
)
async def create_config_version(
    payload: ConfigVersionCreate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> ConfigVersionResponse:
    container = request.app.state.container
    try:
        if payload.scope_type == "platform":
            values = container.runtime_snapshot(
                RuntimeConfigUpdate.model_validate(payload.values)
            ).model_dump(exclude_none=True)
        else:
            tenant_update = TenantConfigUpdate.model_validate(payload.values)
            tenant = next(
                (
                    item
                    for item in container.knowledge_base_service.list_tenants()
                    if item.tenant_id == payload.scope_id
                ),
                None,
            )
            tenant_config = container.knowledge_base_service.tenant_config(payload.scope_id)
            if tenant is None or tenant_config is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="tenant not found",
                )
            values = {
                "name": tenant.name,
                "plan": tenant.plan,
                "default_knowledge_base_id": tenant.default_knowledge_base_id,
                "enabled": tenant.enabled,
                "settings": tenant_config.settings,
            }
            values.update(tenant_update.model_dump(exclude_unset=True))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    created = await asyncio.to_thread(
        container.config_repository.create,
        payload.scope_type,
        payload.scope_id,
        values,
        payload.note,
        actor.user_id,
    )
    await record_audit(
        container,
        actor.user_id,
        "config.create",
        "config_version",
        created.config_id,
        payload.scope_id if payload.scope_type == "tenant" else None,
    )
    return created


@router.post("/config-versions/{config_id}/publish", response_model=ConfigVersionResponse)
async def publish_config_version(
    config_id: str,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> ConfigVersionResponse:
    container = request.app.state.container
    versions = await asyncio.to_thread(container.config_repository.list)
    target = next((item for item in versions if item.config_id == config_id), None)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="config version not found"
        )
    try:
        if target.scope_type == "platform":
            await container.publish_config(config_id)
            published = await asyncio.to_thread(container.config_repository.published)
        else:
            tenant_update = TenantConfigUpdate.model_validate(target.values)
            await asyncio.to_thread(
                container.knowledge_base_service.update_tenant,
                target.scope_id,
                tenant_update,
            )
            published = await asyncio.to_thread(container.config_repository.publish, config_id)
            await container.config_bus.publish(config_id, "tenant", target.scope_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit(
        container,
        actor.user_id,
        "config.publish",
        "config_version",
        config_id,
        target.scope_id if target.scope_type == "tenant" else None,
    )
    return published


@router.get("/tasks", response_model=list[TaskJobResponse])
async def list_tasks(request: Request, limit: int = 100) -> list[TaskJobResponse]:
    return await asyncio.to_thread(
        request.app.state.container.task_repository.list, min(limit, 500)
    )


@router.get("/workflow-runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(request: Request, limit: int = 100) -> list[WorkflowRunResponse]:
    return await asyncio.to_thread(
        request.app.state.container.workflow_repository.list, min(limit, 500)
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    request: Request,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[AuditLogResponse]:
    return await asyncio.to_thread(
        request.app.state.container.audit_repository.list,
        tenant_id,
        min(limit, 500),
    )


@router.get("/handoffs", response_model=list[HandoffTicketResponse])
async def list_handoffs(
    request: Request,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[HandoffTicketResponse]:
    return await asyncio.to_thread(
        request.app.state.container.handoff_repository.list,
        tenant_id,
        min(limit, 500),
    )


@router.patch("/handoffs/{ticket_id}", response_model=HandoffTicketResponse)
async def update_handoff(
    ticket_id: str,
    payload: HandoffTicketUpdate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> HandoffTicketResponse:
    container = request.app.state.container
    ticket = await asyncio.to_thread(
        container.handoff_repository.update_status,
        ticket_id,
        payload.status,
    )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="handoff ticket not found"
        )
    await record_audit(
        container,
        actor.user_id,
        "handoff.update",
        "handoff_ticket",
        ticket_id,
        ticket.tenant_id,
        {"status": payload.status},
    )
    return ticket


@router.post("/evaluations/run", response_model=EvaluationReport)
async def run_evaluation(payload: EvaluationRunRequest, request: Request) -> EvaluationReport:
    service = request.app.state.container.evaluation_service
    cases = payload.cases if payload.cases is not None else service.load_default_cases()
    try:
        return await service.run(cases, payload.judge)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/evaluations", response_model=list[EvaluationRunResponse])
async def list_evaluations(request: Request, limit: int = 50) -> list[EvaluationRunResponse]:
    return await asyncio.to_thread(
        request.app.state.container.evaluation_repository.list,
        min(limit, 200),
    )


@router.get("/tenants", response_model=list[TenantSummaryResponse])
async def list_tenants(request: Request) -> list[TenantSummaryResponse]:
    return await asyncio.to_thread(request.app.state.container.knowledge_base_service.list_tenants)


@router.patch("/tenants/{tenant_id}", response_model=TenantSummaryResponse)
async def update_tenant(
    tenant_id: str,
    payload: TenantConfigUpdate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> TenantSummaryResponse:
    container = request.app.state.container
    try:
        result = await asyncio.to_thread(
            container.knowledge_base_service.update_tenant, tenant_id, payload
        )
        version = await asyncio.to_thread(
            container.config_repository.create,
            "tenant",
            tenant_id,
            {
                "name": result.name,
                "plan": result.plan,
                "default_knowledge_base_id": result.default_knowledge_base_id,
                "enabled": result.enabled,
                "settings": (container.knowledge_base_service.tenant_config(tenant_id).settings),
            },
            "租户配置更新",
            actor.user_id,
        )
        await asyncio.to_thread(container.config_repository.publish, version.config_id)
        await container.config_bus.publish(version.config_id, "tenant", tenant_id)
        await record_audit(
            container, actor.user_id, "tenant.update", "tenant", tenant_id, tenant_id
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseResponse])
async def list_all_knowledge_bases(request: Request) -> list[KnowledgeBaseResponse]:
    return await asyncio.to_thread(request.app.state.container.knowledge_base_service.list_all)


@router.post(
    "/knowledge-bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> KnowledgeBaseResponse:
    container = request.app.state.container
    try:
        result = await asyncio.to_thread(
            container.knowledge_base_service.create_knowledge_base, payload
        )
        await record_audit(
            container,
            actor.user_id,
            "knowledge_base.create",
            "knowledge_base",
            payload.knowledge_base_id,
            payload.tenant_id,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> KnowledgeBaseResponse:
    container = request.app.state.container
    try:
        result = await asyncio.to_thread(
            container.knowledge_base_service.update_knowledge_base,
            knowledge_base_id,
            payload,
        )
        knowledge_base = container.knowledge_base_service.get(knowledge_base_id)
        await record_audit(
            container,
            actor.user_id,
            "knowledge_base.update",
            "knowledge_base",
            knowledge_base_id,
            knowledge_base.tenant_id if knowledge_base else None,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentResponse])
async def list_all_documents(request: Request) -> list[DocumentResponse]:
    return await asyncio.to_thread(
        request.app.state.container.knowledge_base_service.list_all_documents
    )


@router.post(
    "/documents/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    request: Request,
    knowledge_base_id: str = Form(...),
    title: str | None = Form(default=None),
    category: str = Form(default="未分类"),
    file: UploadFile = File(...),
    actor: UserContext = Depends(require_admin),
) -> DocumentUploadResponse:
    container = request.app.state.container
    knowledge_base = container.knowledge_base_service.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found"
        )
    payload = await read_limited_upload(file, container.settings.max_upload_bytes)
    try:
        parsed = await asyncio.to_thread(
            ingestion_service.parse,
            file.filename or "uploaded-file",
            payload,
            file.content_type,
        )
    except UnsupportedDocumentFormat as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    document_input = DocumentCreate(
        title=title.strip() if title and title.strip() else parsed.title,
        content=parsed.content,
        metadata={**parsed.metadata, "category": category},
    )
    source_uri = await container.object_store.put(
        knowledge_base.tenant_id,
        knowledge_base_id,
        document_input.document_id,
        file.filename or "uploaded-file",
        payload,
    )
    try:
        document = await asyncio.to_thread(
            container.knowledge_base_service.add_document,
            knowledge_base_id,
            document_input,
        )
        document = await asyncio.to_thread(
            container.document_repository.update_lifecycle,
            knowledge_base_id,
            document.document_id,
            {
                "status": "parsed",
                "source_uri": source_uri,
                "checksum": hashlib.sha256(payload).hexdigest(),
            },
        )
    except Exception:
        await container.object_store.delete(source_uri)
        raise

    index_status = "ready"
    task_id = None
    if container.settings.task_queue.lower() == "redis":
        task_id = str(uuid4())
        task_payload = {
            "knowledge_base_id": knowledge_base_id,
            "document_id": document.document_id,
        }
        await asyncio.to_thread(
            container.task_repository.create,
            task_id,
            "index_document",
            task_payload,
            container.settings.task_max_attempts,
        )
        try:
            await container.task_queue.enqueue(
                "index_document",
                task_payload,
                task_id=task_id,
            )
        except Exception as exc:
            await asyncio.to_thread(
                container.task_repository.update,
                task_id,
                status="failed",
                error=str(exc),
            )
            raise
        index_status = "queued"
    else:
        await container.rag_service.index_document(document)
        document = await asyncio.to_thread(
            container.document_repository.get,
            knowledge_base_id,
            document.document_id,
        )
    await record_audit(
        container,
        actor.user_id,
        "document.upload",
        "document",
        document.document_id,
        knowledge_base.tenant_id,
        {"filename": file.filename, "parser": parsed.metadata["parser"]},
    )
    return DocumentUploadResponse(
        **document.model_dump(),
        parser=parsed.metadata["parser"],
        source_filename=parsed.metadata["source_filename"],
        index_status=index_status,
        task_id=task_id,
    )


@router.delete(
    "/documents/{knowledge_base_id}/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_document(
    knowledge_base_id: str,
    document_id: str,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> None:
    container = request.app.state.container
    document = await asyncio.to_thread(
        container.document_repository.get, knowledge_base_id, document_id
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    deleted = await asyncio.to_thread(
        container.knowledge_base_service.delete_document,
        knowledge_base_id,
        document_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    await container.rag_service.delete_document(knowledge_base_id, document_id)
    if document.source_uri:
        await container.object_store.delete(document.source_uri)
    knowledge_base = container.knowledge_base_service.get(knowledge_base_id)
    await record_audit(
        container,
        actor.user_id,
        "document.delete",
        "document",
        document_id,
        knowledge_base.tenant_id if knowledge_base else None,
    )


@router.get("/runtime", response_model=RuntimeConfigResponse)
async def runtime_config(request: Request) -> RuntimeConfigResponse:
    return request.app.state.container.runtime_config()


@router.patch("/runtime", response_model=RuntimeConfigResponse)
async def update_runtime(
    payload: RuntimeConfigUpdate,
    request: Request,
    actor: UserContext = Depends(require_admin),
) -> RuntimeConfigResponse:
    container = request.app.state.container
    try:
        result = await container.create_and_publish_runtime(payload, actor.user_id)
        await record_audit(
            container,
            actor.user_id,
            "runtime.update",
            "platform_config",
            "global",
            details=payload.model_dump(exclude_unset=True),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
