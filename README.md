# PDF-to-Quiz 🎓

AI-powered backend that converts PDF documents into structured multiple-choice quizzes using an LLM.

---

## Architecture

| Component  | Technology                          | Deployment         |
|------------|-------------------------------------|--------------------|
| Frontend   | Next.js                             | Vercel             |
| Backend    | FastAPI + Gunicorn + Uvicorn        | Azure App Service (Docker) |
| Database   | PostgreSQL                          | Supabase           |
| LLM        | Mistral (via LiteLLM)               | Mistral API        |

---

## 1. Local Development (No Docker Required)

### Prerequisites

- Python ≥ 3.11
- Node.js ≥ 18
- A Supabase project
- A Mistral API key

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
# Edit .env with your real API keys and database URL

# 5. Start the development server (auto-reload)
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
# Create frontend/.env.local with:
# NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
# NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
# NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

# Start the development server
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## 2. Frontend Deployment — Vercel

Vercel is the recommended deployment target for the Next.js frontend.

### Steps

1. Push your code to GitHub (already done).
2. Go to [vercel.com](https://vercel.com) → **New Project**.
3. Import the repository and set the **Root Directory** to `frontend`.
4. Set the following **Environment Variables** in Vercel Project Settings:

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Your Azure backend URL, e.g. `https://your-app.azurewebsites.net/api/v1` |
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Your Supabase anon/public key |

5. Click **Deploy**. Vercel will auto-detect Next.js and configure the build.

> **Note:** Every push to `main` will trigger an automatic redeploy on Vercel.

---

## 3. Backend Deployment — Azure App Service (Docker)

### Prerequisites

- An Azure account with an active subscription.
- Azure CLI installed: `az login`
- A container registry (Azure Container Registry or Docker Hub).

### Step 1: Build and Push the Docker Image

#### Option A: Azure Container Registry (ACR) — Recommended

```bash
# Create a Resource Group (skip if you already have one)
az group create --name pdf-quiz-rg --location eastus

# Create an Azure Container Registry
az acr create --resource-group pdf-quiz-rg \
              --name pdfquizregistry \
              --sku Basic \
              --admin-enabled true

# Build directly in ACR (no local Docker required!)
az acr build --registry pdfquizregistry \
             --image pdf-to-quiz-backend:latest \
             .
```

> ✅ `az acr build` uploads your source code to Azure and builds the image in the cloud. **Docker does not need to be installed locally.**

#### Option B: GitHub Actions CI/CD (Fully Automated)

Set up GitHub Actions to build and push on every push to `main`.  
See [Azure documentation](https://docs.microsoft.com/en-us/azure/app-service/deploy-container-github-action).

### Step 2: Create the App Service

```bash
# Create an App Service Plan (Linux, Basic tier)
az appservice plan create \
    --resource-group pdf-quiz-rg \
    --name pdf-quiz-plan \
    --is-linux \
    --sku B2

# Get ACR credentials
ACR_PASSWORD=$(az acr credential show --name pdfquizregistry --query passwords[0].value -o tsv)

# Create the Web App from the container image
az webapp create \
    --resource-group pdf-quiz-rg \
    --plan pdf-quiz-plan \
    --name pdf-to-quiz-api \
    --deployment-container-image-name pdfquizregistry.azurecr.io/pdf-to-quiz-backend:latest \
    --docker-registry-server-user pdfquizregistry \
    --docker-registry-server-password "$ACR_PASSWORD"
```

### Step 3: Configure Environment Variables

```bash
az webapp config appsettings set \
    --resource-group pdf-quiz-rg \
    --name pdf-to-quiz-api \
    --settings \
        LLM_MODEL="mistral/mistral-small-latest" \
        MISTRAL_API_KEY="your-mistral-api-key" \
        DATABASE_URL="your-database-url" \
        SUPABASE_URL="your-supabase-url" \
        SUPABASE_ANON_KEY="your-anon-key" \
        SUPABASE_SERVICE_ROLE_KEY="your-service-role-key" \
        SUPABASE_JWT_SECRET="your-jwt-secret" \
        PREFERRED_CHUNK_SIZE="1000" \
        MIN_CHUNK_SIZE="700" \
        MAX_CHUNK_SIZE="1500" \
        CHUNK_OVERLAP="100" \
        MIN_QUESTIONS_PER_CHUNK="2" \
        MAX_QUESTIONS_PER_CHUNK="5" \
        MAX_PAGES_PER_REQUEST="100" \
        WORKERS="2" \
        TIMEOUT="120" \
        LOG_LEVEL="info" \
        WEBSITES_PORT="8000"
```

> **`WEBSITES_PORT=8000`** tells Azure App Service which port the container listens on.

### Step 4: Enable Continuous Deployment (Optional)

```bash
# Enable automatic redeployment when ACR image is updated
az webapp deployment container config \
    --resource-group pdf-quiz-rg \
    --name pdf-to-quiz-api \
    --enable-cd true
```

Your API will be live at: `https://pdf-to-quiz-api.azurewebsites.net`

---

## 4. Docker Deployment (Future / Other Machines)

> **Note:** Docker is not available on the current development machine.  
> Use this section when deploying on a machine with Docker installed.

### Build Locally

```bash
docker build -t pdf-to-quiz-backend:latest .
```

### Run Locally

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  pdf-to-quiz-backend:latest
```

### With Docker Compose

```bash
# Copy and fill in secrets
cp .env.example .env

# Start the backend
docker compose up --build
```

---

## Environment Variables Reference

See [`.env.example`](.env.example) for the full list with descriptions.

| Variable | Required | Default | Description |
|---|---|---|---|
| `MISTRAL_API_KEY` | ✅ | — | Mistral API key |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string (Supabase) |
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | — | Supabase public/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Supabase service role key |
| `SUPABASE_JWT_SECRET` | ✅ | — | JWT secret for token validation |
| `LLM_MODEL` | ❌ | `mistral/mistral-small-latest` | LiteLLM model string |
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
