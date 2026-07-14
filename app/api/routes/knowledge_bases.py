from fastapi import APIRouter, HTTPException, Request, status

from app.domain.models import DocumentCreate, DocumentResponse, KnowledgeBaseResponse, SearchRequest, SearchResponse


router = APIRouter()


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(request: Request, tenant_id: str = "demo") -> list[KnowledgeBaseResponse]:
    return request.app.state.container.knowledge_base_service.list_for_tenant(tenant_id)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentResponse])
async def list_documents(knowledge_base_id: str, request: Request) -> list[DocumentResponse]:
    container = request.app.state.container
    if container.knowledge_base_service.get(knowledge_base_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    return container.document_repository.list(knowledge_base_id)


@router.post("/{knowledge_base_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def add_document(knowledge_base_id: str, payload: DocumentCreate, request: Request) -> DocumentResponse:
    container = request.app.state.container
    if container.knowledge_base_service.get(knowledge_base_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    return container.knowledge_base_service.add_document(knowledge_base_id, payload)


@router.post("/{knowledge_base_id}/search", response_model=SearchResponse)
async def search_documents(knowledge_base_id: str, payload: SearchRequest, request: Request) -> SearchResponse:
    container = request.app.state.container
    if container.knowledge_base_service.get(knowledge_base_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="knowledge base not found")
    results = await container.rag_service.search(knowledge_base_id, payload.query, payload.top_k)
    return SearchResponse(query=payload.query, results=results)
