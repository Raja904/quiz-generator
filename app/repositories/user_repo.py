from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db_session: AsyncSession):
        super().__init__(User, db_session)

    async def upsert_user(self, user_id: str, email: str, full_name: str) -> User:
        """Upserts a user record and returns the user."""
        stmt = select(self.model).where(self.model.id == user_id)
        result = await self.db_session.execute(stmt)
        user = result.scalar_one_or_none()

        from datetime import datetime, timezone

        if not user:
            user = User(
                id=user_id,
                email=email,
                full_name=full_name,
                last_login=datetime.now(timezone.utc),
            )
            self.add(user)
            await self.db_session.commit()
            await self.db_session.refresh(user)
        else:
            user.last_login = datetime.now(timezone.utc)
            await self.db_session.commit()
            await self.db_session.refresh(user)

        return user
