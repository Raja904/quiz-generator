"""Enable RLS

Revision ID: f414dfb880fb
Revises: 61630cabe6a8
Create Date: 2026-07-12 13:59:56.927271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f414dfb880fb'
down_revision: Union[str, Sequence[str], None] = '61630cabe6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable Row Level Security (RLS) on all user tables
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pdf_metadata ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE quizzes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE quiz_questions ENABLE ROW LEVEL SECURITY")

    # Create policies to ensure users can only access their own data
    # (These policies primarily protect data if accessed via Supabase's PostgREST API)
    op.execute('CREATE POLICY "Users can access their own user record" ON users FOR ALL USING (auth.uid() = id)')
    op.execute('CREATE POLICY "Users can access their own pdfs" ON pdf_metadata FOR ALL USING (auth.uid() = user_id)')
    op.execute('CREATE POLICY "Users can access their own quizzes" ON quizzes FOR ALL USING (auth.uid() = user_id)')
    
    # Quiz questions are owned by the quiz's user
    op.execute('''
        CREATE POLICY "Users can access their own quiz questions" ON quiz_questions FOR ALL 
        USING (quiz_id IN (SELECT id FROM quizzes WHERE user_id = auth.uid()))
    ''')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "Users can access their own quiz questions" ON quiz_questions')
    op.execute('DROP POLICY IF EXISTS "Users can access their own quizzes" ON quizzes')
    op.execute('DROP POLICY IF EXISTS "Users can access their own pdfs" ON pdf_metadata')
    op.execute('DROP POLICY IF EXISTS "Users can access their own user record" ON users')
    
    op.execute("ALTER TABLE quiz_questions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE quizzes DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pdf_metadata DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
