from fastapi import APIRouter

from app.api.routes import admin, chat, config, health, knowledge_bases, tools


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(knowledge_bases.router, prefix="/knowledge-bases", tags=["knowledge-bases"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
