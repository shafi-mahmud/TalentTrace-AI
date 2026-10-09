"""Register the implemented knowledge tables with the shared SQLAlchemy Base."""

from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.models.recruiter import Recruiter, RecruiterSession, RecruiterConversation, ChatTurn, JobProfile

__all__ = ["KnowledgeDocument", "KnowledgeChunk"]
