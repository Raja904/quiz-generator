from uuid import UUID
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Quiz, PDFMetadata, QuizQuestion
from app.repositories.base import BaseRepository


class QuizRepository(BaseRepository[Quiz]):
    def __init__(self, db_session: AsyncSession):
        super().__init__(Quiz, db_session)

    async def get_user_quizzes(self, user_id: UUID) -> Sequence[tuple[Quiz, str]]:
        """Returns a list of quizzes for a user along with the original filename."""
        stmt = (
            select(Quiz, PDFMetadata.filename)
            .join(PDFMetadata, Quiz.pdf_metadata_id == PDFMetadata.id)
            .where(Quiz.user_id == user_id)
            .order_by(Quiz.created_at.desc())
        )
        result = await self.db_session.execute(stmt)
        return result.all()

    async def get_quiz_with_details(self, quiz_id: UUID, user_id: UUID) -> Quiz | None:
        """Returns a quiz by ID including its metadata and questions."""
        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions), selectinload(Quiz.pdf_metadata))
            .where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_quiz_results(
        self,
        user_id: UUID,
        filename: str,
        total_pages: int,
        total_tokens: int,
        llm_model: str,
        final_generated: int,
        all_questions: list,
    ) -> tuple[PDFMetadata, Quiz]:
        """Saves PDF metadata, Quiz, and Questions inside a transaction."""
        
        # 1. PDF Metadata
        db_metadata = PDFMetadata(
            user_id=user_id,
            filename=filename,
            page_count=total_pages,
            total_tokens=total_tokens,
        )
        self.db_session.add(db_metadata)
        await self.db_session.flush()

        # 2. Quiz Metadata
        db_quiz = Quiz(
            user_id=user_id,
            pdf_metadata_id=db_metadata.id,
            llm_model=llm_model,
            total_questions=final_generated,
        )
        self.db_session.add(db_quiz)
        await self.db_session.flush()

        # 3. Quiz Questions
        db_questions = []
        for q in all_questions:
            db_q = QuizQuestion(
                quiz_id=db_quiz.id,
                question=q.question,
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                source_chunk=q.source_chunk,
            )
            db_questions.append(db_q)
        
        self.db_session.add_all(db_questions)
        await self.db_session.commit()
        
        return db_metadata, db_quiz
