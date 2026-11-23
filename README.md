# PDF-to-Quiz 🎓

AI-powered backend that converts PDF documents into structured multiple-choice quizzes using an LLM.

---

## Architecture

| Component  | Technology                          | Deployment         |
|------------|-------------------------------------|--------------------|
| Frontend   | Next.js                             | Vercel             |
| Backend    | FastAPI + Gunicorn + Uvicorn        | Azure App Service (Docker) |
| Database   | PostgreSQL                          | Supabase           |
| LLM        | Qwen via Groq SDK                   | Groq API            |

---

## 1. Local Development (No Docker Required)

### Prerequisites

- Python ≥ 3.11
- Node.js ≥ 18
- A Supabase project
- A Groq API key

### Backend Setup

```bash
# 1. Clone the repository
git clone https://github.com/Raja904/quiz-generator.git
cd quiz-generator

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Configure environment
cp .env.example .env
# Set GROQ_API_KEY and your database/Supabase values in .env

# 5. Start the development server (auto-reload)
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### Frontend Setup

```bash
cd frontend
npm install
# Create frontend/.env.local with NEXT_PUBLIC_API_URL and Supabase settings
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## 2. Frontend Deployment — Vercel

Vercel is the recommended deployment target for the Next.js frontend.

1. Import the repository into Vercel and set the **Root Directory** to `frontend`.
2. Set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in Vercel Project Settings.
3. Deploy. Every push to `main` triggers an automatic redeploy.

---

## 3. Backend Deployment — Azure App Service (Docker)

Build and push the Docker image to a container registry, then configure the Azure App Service to use it. Set the following application settings (along with your existing database and Supabase credentials):

```text
LLM_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=your-groq-api-key
DATABASE_URL=your-database-url
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

Set `WEBSITES_PORT=8000` for Azure App Service. Other chunking and server settings can be configured as documented in `.env.example`.

---

## 4. Docker Deployment

```bash
cp .env.example .env
# Set GROQ_API_KEY and other credentials in .env
docker compose up --build
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | Groq API key used by the Groq SDK |
| `LLM_MODEL` | ❌ | `qwen/qwen3.8-27b` | Groq model identifier |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string (Supabase) |
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | — | Supabase public/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Supabase service role key |
| `SUPABASE_JWT_SECRET` | ✅ | — | JWT secret for token validation |
| `PREFERRED_CHUNK_SIZE` | ❌ | `1000` | Target tokens per chunk |
| `CHUNK_OVERLAP` | ❌ | `100` | Overlap tokens between chunks |
| `WORKERS` | ❌ | `2` | Gunicorn worker count (Docker only) |
| `PORT` | ❌ | `8000` | Container port |
| `LOG_LEVEL` | ❌ | `INFO` | Logging verbosity |

---

## Pipeline Overview

```
PDF Upload
    ↓
Parse selected pages
    ↓
Page-level filter  →  drops TOC, Index, Copyright, blank pages
    ↓
Fixed semantic chunking  (1000 tokens, 100 overlap — document-driven)
    ↓
Chunk-level filter  →  drops non-educational chunks before LLM
    ↓
Compute QPQ = clamp(ceil(N / chunks), min=2, max=5)
    ↓
LLM (3 concurrent calls, 30 s timeout) → post-validate each question
    ↓
Deduplicate → Trim to N requested questions
    ↓
Top-up (only if still short) → Dedup → Trim
    ↓
Return exactly N questions  (or show banner if short)
```
