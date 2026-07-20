import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import assert_tenant_access, get_current_user
from app.domain.models import ConversationResponse, UserContext


router = APIRouter()


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> ConversationResponse:
    conversation_repository = request.app.state.container.conversation_repository
    if conversation_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="conversation storage unavailable",
        )
    conversation = await asyncio.to_thread(conversation_repository.get, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    assert_tenant_access(user, conversation.tenant_id)
    return conversation
