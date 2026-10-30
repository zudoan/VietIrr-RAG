# Local Environment Setup and Execution Guide

## Prerequisites

### 1. System Requirements
- **Operating System**: Windows 10/11 (64-bit) or Linux (Ubuntu 22.04+ recommended)
- **Memory**: Minimum 16 GB RAM (32 GB recommended for dense vector models)
- **Accelerator**: NVIDIA GPU with 8 GB+ VRAM recommended for local BGE-M3 embedding and Qwen2.5 inference (CPU execution is supported but significantly slower)
- **Disk Space**: At least 15 GB free space for corpus indices, embedding caches, and model checkpoints

### 2. Runtime Dependencies
- **Python**: Version 3.10 or 3.11
- **Node.js**: Version 20.x or higher (with `npm` 10.x+)
- **Ollama**: Required for local LLM inference (or compatible OpenAI-compatible serving endpoint)

---

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/zudoan/VietIrr-RAG.git
cd VietIrr-RAG
```

### Step 2: Set Up Python Environment

Create and activate an isolated virtual environment:

```bash
# On Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# On Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install backend package dependencies:

```bash
pip install --upgrade pip
pip install -e .
```

Verify the installation by running the test suite:

```bash
pytest tests/ -q
```

### Step 3: Install and Configure Ollama (Local LLM)

1. Download and install Ollama from [https://ollama.com](https://ollama.com).
2. Pull the designated local model checkpoint:

```bash
ollama pull qwen2.5:7b
```

3. Ensure the Ollama daemon is active and listening on `http://127.0.0.1:11434`:

```bash
# Verify model availability
curl http://127.0.0.1:11434/api/tags
```

### Step 4: Configure Environment Variables

Copy the template configuration:

```bash
# On Windows PowerShell
Copy-Item .env.example .env

# On Linux / macOS
cp .env.example .env
```

Key environment options in `.env`:
- `VIETIRR_ENV`: `development` or `production`
- `DATABASE_URL`: `sqlite+pysqlite:///./vietirr.db` (or PostgreSQL URI for multi-worker production)
- `ALLOWED_ORIGINS`: `http://127.0.0.1:5173,http://localhost:5173`
- `OLLAMA_BASE_URL`: `http://127.0.0.1:11434`
- `VIETIRR_PUBLIC_MODE`: `false` (set to `true` to restrict access to unverified PDF binaries)

### Step 5: Install Frontend Dependencies

Navigate to the frontend directory and install NPM packages:

```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Starting the Application

### 1. Launch FastAPI Backend

Run the backend service on port 8000:

```bash
# From the repository root (with virtual environment activated)
uvicorn viirr_api.app:app --host 127.0.0.1 --port 8000 --reload
```

The API endpoints will be accessible at:
- Service API: `http://127.0.0.1:8000`
- Interactive Swagger Documentation: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/health`
- Readiness Check: `http://127.0.0.1:8000/ready`

### 2. Launch Vite Frontend Development Server

In a separate terminal:

```bash
cd frontend
npm run dev
```

The web application will be accessible at `http://127.0.0.1:5173`.

---

## Verification and Smoke Testing

Verify backend operation using standard HTTP queries:

```bash
# Test health endpoint
curl http://127.0.0.1:8000/health

# Test retrieval search endpoint
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "cao trình đỉnh đập Hồ Thác La", "limit": 5}'

# Test QA generation endpoint
curl -X POST http://127.0.0.1:8000/qa \
  -H "Content-Type: application/json" \
  -d '{"query": "Cao trình đỉnh đập của hồ Thác La là bao nhiêu?"}'
```
