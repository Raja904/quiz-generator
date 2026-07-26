# PDF-to-Quiz Backend MVP

An AI-powered backend that converts PDF documents into structured multiple-choice quizzes.

## Architecture

```
PDF Upload → PyMuPDF Parser → Text Cleaner → Token-aware Chunker → LiteLLM → Structured Quiz JSON
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager

### 2. Install `uv` (if needed)

```powershell
pip install uv
```

### 3. Clone and set up

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Copy env template
cp .env.example .env
# Edit .env and add your API key
```

### 4. Configure `.env`

```env
LLM_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=sk-your-key-here
CHUNK_SIZE=1500
CHUNK_OVERLAP=150
QUESTIONS_PER_CHUNK=5
```

### 5. Run the server

```bash
uvicorn main:app --reload
```

Visit **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Endpoints

### `POST /generate-quiz`

Upload a PDF to generate multiple-choice questions.

**Request:** `multipart/form-data`
- `file` (required): PDF file
- `questions_per_chunk` (optional): integer 1–20, overrides server default

**Response:**
```json
{
  "questions": [
    {
      "question": "What is the primary goal of machine learning?",
      "options": ["...", "...", "...", "..."],
      "correct_answer": "...",
      "explanation": "...",
      "difficulty": "medium",
      "source_chunk": 0
    }
  ],
  "total_questions": 15,
  "total_chunks": 3,
  "total_pages": 10
}
```

### `GET /health`

```json
{"status": "ok", "version": "0.1.0"}
```

---

## Supported LLM Providers

Set `LLM_MODEL` in `.env` to any [LiteLLM-supported model](https://docs.litellm.ai/docs/providers):

| Provider   | Example model string                        | Env var             |
|------------|---------------------------------------------|---------------------|
| OpenAI     | `openai/gpt-4o-mini`                        | `OPENAI_API_KEY`    |
| Anthropic  | `anthropic/claude-3-5-haiku-20241022`       | `ANTHROPIC_API_KEY` |
| Google     | `google/gemini-2.0-flash`                   | `GOOGLE_API_KEY`    |

---

## Running Tests

```bash
uv run pytest tests/ -v
```

---

## Docker

```bash
docker build -t pdf-to-quiz .
docker run -p 8000:8000 --env-file .env pdf-to-quiz
```

---

## Project Structure

```
app/
  api/          # FastAPI route definitions
  core/         # Settings / config
  llm/          # LiteLLM wrapper
  models/       # Pydantic schemas
  parsers/      # PDF text extraction (PyMuPDF)
  prompts/      # LLM prompt templates
  services/     # Pipeline orchestration
  utils/        # Text cleaner, token-aware chunker
tests/          # Unit + integration tests
main.py         # App entry point
pyproject.toml  # uv project manifest
Dockerfile
```

---

## Roadmap (Post-MVP)

- [ ] OCR fallback for scanned/image-only PDFs (Docling or Tesseract)
- [ ] Adaptive difficulty and spaced repetition
- [ ] User accounts and quiz history
- [ ] Analytics dashboard
- [ ] Subscription tiers
