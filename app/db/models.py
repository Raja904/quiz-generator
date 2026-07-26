"""
app/db/models.py

SQLAlchemy declarative models mapped to Supabase PostgreSQL tables.
"""

import datetime
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class User(Base):
    """
    Mirrors the Supabase auth.users table in the public schema.
    Typically populated via a PostgreSQL trigger on auth.users,
    but can also be upserted manually on first API request.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    quizzes = relationship("Quiz", back_populates="user", cascade="all, delete-orphan")


class PDFMetadata(Base):
    """
    Stores metadata about the parsed PDF.
    """
    __tablename__ = "pdf_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    page_count = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    quizzes = relationship("Quiz", back_populates="pdf_metadata", cascade="all, delete-orphan")


class Quiz(Base):
    """
    Represents a quiz generation session.
    """
    __tablename__ = "quizzes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_metadata_id = Column(UUID(as_uuid=True), ForeignKey("pdf_metadata.id", ondelete="CASCADE"), nullable=False, index=True)
    llm_model = Column(String, nullable=False)
    total_questions = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="quizzes")
    pdf_metadata = relationship("PDFMetadata", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    """
    Individual multiple choice question for a quiz.
    """
    __tablename__ = "quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(String, nullable=False)
    options = Column(JSON, nullable=False)  # JSON array of strings
    correct_answer = Column(String, nullable=False)
    explanation = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    source_chunk = Column(Integer, nullable=False)

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
