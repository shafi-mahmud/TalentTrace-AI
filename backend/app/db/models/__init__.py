"""Register the implemented knowledge tables with the shared SQLAlchemy Base."""

from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument

__all__ = ["KnowledgeDocument", "KnowledgeChunk"]
