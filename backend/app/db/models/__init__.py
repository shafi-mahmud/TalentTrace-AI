"""Register the implemented knowledge tables with the shared SQLAlchemy Base."""

from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.models.recruiter import Recruiter, RecruiterSession, RecruiterConversation, ChatTurn, JobProfile
from app.db.models.interview_transcript import InterviewTranscriptSession, InterviewTranscriptTurn
from app.db.models.application_view import ApplicationView

__all__ = ["KnowledgeDocument", "KnowledgeChunk", "InterviewTranscriptSession", "InterviewTranscriptTurn", "ApplicationView"]
