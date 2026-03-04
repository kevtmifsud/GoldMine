from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response

from app.auth.users import USERS
from app.exceptions import GoldMineError, NotFoundError
from app.logging_config import get_logger
from app.studios.factory import get_studios_provider
from app.studios.models import (
    ChatMessage,
    Studio,
    StudioChatRequest,
    StudioChatResponse,
    StudioCreate,
    StudioUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/studios", tags=["studios"])


def _enrich_studio(studio: Studio) -> Studio:
    """Fill in owner_display_name from the USERS registry."""
    user_data = USERS.get(studio.owner)
    if user_data:
        studio.owner_display_name = user_data["display_name"]
    else:
        studio.owner_display_name = studio.owner
    return studio


@router.get("/")
async def list_studios(request: Request) -> list[Studio]:
    user = request.state.user
    provider = get_studios_provider()
    return [_enrich_studio(s) for s in provider.list_studios(owner=user.username)]


@router.post("/", status_code=201)
async def create_studio(request: Request, body: StudioCreate) -> Studio:
    user = request.state.user
    provider = get_studios_provider()
    return _enrich_studio(provider.create_studio(body, owner=user.username))


@router.get("/{studio_id}")
async def get_studio(request: Request, studio_id: str) -> Studio:
    user = request.state.user
    provider = get_studios_provider()
    studio = provider.get_studio(studio_id)
    if studio is None:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    if studio.owner != user.username and not studio.is_shared:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    return _enrich_studio(studio)


@router.put("/{studio_id}")
async def update_studio(request: Request, studio_id: str, body: StudioUpdate) -> Studio:
    user = request.state.user
    provider = get_studios_provider()
    studio = provider.get_studio(studio_id)
    if studio is None:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    if studio.owner != user.username:
        raise GoldMineError("Cannot modify another user's studio", status_code=403)
    updated = provider.update_studio(studio_id, body)
    if updated is None:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    return _enrich_studio(updated)


@router.delete("/{studio_id}", status_code=204, response_class=Response)
async def delete_studio(request: Request, studio_id: str) -> Response:
    user = request.state.user
    provider = get_studios_provider()
    studio = provider.get_studio(studio_id)
    if studio is None:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    if studio.owner != user.username:
        raise GoldMineError("Cannot delete another user's studio", status_code=403)
    provider.delete_studio(studio_id)


@router.post("/{studio_id}/chat")
async def chat_studio(request: Request, studio_id: str, body: StudioChatRequest) -> StudioChatResponse:
    user = request.state.user
    provider = get_studios_provider()
    studio = provider.get_studio(studio_id)
    if studio is None:
        raise NotFoundError(f"Studio '{studio_id}' not found")
    if studio.owner != user.username and not studio.is_shared:
        raise NotFoundError(f"Studio '{studio_id}' not found")

    # Import LLM provider lazily
    from app.llm.studio_provider import StudioLLMProvider

    llm = StudioLLMProvider()

    # Copy current widgets and row_columns so the LLM can mutate them
    widgets = [w.model_copy(deep=True) for w in studio.widgets]
    row_columns = list(studio.row_columns)

    # Run tool-calling loop in thread (synchronous Anthropic client)
    reply, updated_widgets, updated_row_columns, model, token_usage = await asyncio.to_thread(
        llm.chat,
        body.message,
        body.conversation_history,
        widgets,
        row_columns,
    )

    # Persist updated state
    all_messages = list(body.conversation_history)
    # The conversation_history from the frontend already includes the user message
    # Add the assistant reply
    all_messages.append(ChatMessage(role="assistant", content=reply))

    provider.update_studio(studio_id, StudioUpdate(
        widgets=updated_widgets,
        row_columns=updated_row_columns,
        messages=all_messages,
    ))

    return StudioChatResponse(
        reply=reply,
        widgets=updated_widgets,
        row_columns=updated_row_columns,
        model=model,
        token_usage=token_usage,
    )
