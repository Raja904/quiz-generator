import asyncio
from app.repositories.user_repo import UserRepository
from app.db.database import async_session_maker

async def main():
    async with async_session_maker() as db:
        repo = UserRepository(db)
        user = await repo.upsert_user('fake-id', 'test@test.com', 'Test')
        print(user.id)

if __name__ == '__main__':
    asyncio.run(main())
