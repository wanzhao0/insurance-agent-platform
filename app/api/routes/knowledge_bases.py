from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import assert_tenant_access, get_current_user, require_admin
from app.domain.models import DocumentCreate, DocumentResponse, KnowledgeBaseResponse, SearchRequest, SearchResponse
from app.domain.models import UserContext


router = APIRouter()


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    request: Request,
    tenant_id: str = "demo",
    user: UserContext = Depends(get_current_user),
) -> list[KnowledgeBaseResponse]:
    assert_tenant_access(user, tenant_id)
    return request.app.state.container.knowledge_base_service.list_for_tenant(tenant_id)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    knowledge_base_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> list[DocumentResponse]:
    container = request.app.state.container
    knowledge_base = container.knowledge_base_service.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    assert_tenant_access(user, knowledge_base.tenant_id)
    return container.document_repository.list(knowledge_base_id)


@router.post("/{knowledge_base_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def add_document(
    knowledge_base_id: str,
    payload: DocumentCreate,
    request: Request,
    _: None = Depends(require_admin),
) -> DocumentResponse:
    container = request.app.state.container
    if container.knowledge_base_service.get(knowledge_base_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    document = container.knowledge_base_service.add_document(knowledge_base_id, payload)
    if container.settings.task_queue.lower() == "redis":
        await container.task_queue.enqueue(
            "index_document",
            {"knowledge_base_id": knowledge_base_id, "document_id": document.document_id},
        )
    else:
        await container.rag_service.index_document(document)
    return document


@router.post("/{knowledge_base_id}/search", response_model=SearchResponse)
async def search_documents(
    knowledge_base_id: str,
    payload: SearchRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> SearchResponse:
    container = request.app.state.container
    knowledge_base = container.knowledge_base_service.get(knowledge_base_id)
    if knowledge_base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    assert_tenant_access(user, knowledge_base.tenant_id)
    results = await container.rag_service.search(knowledge_base_id, payload.query, payload.top_k)
    return SearchResponse(query=payload.query, results=results)
