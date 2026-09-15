# Health Data Agent

> Natural-language analytics for healthcare and biomedical CSV datasets.

Health Data Agent is a web application that allows users to upload healthcare or biomedical datasets and explore them using natural-language questions.

Instead of asking the language model to calculate answers directly, the application uses AI to **interpret the user's intent and generate a structured query**. The validated query is then executed deterministically with Pandas.

**LLM interprets → Pipeline validates → Pandas executes → Frontend visualizes**

This architecture separates natural-language reasoning from data computation and reduces the risk of generating answers that are not supported by the uploaded data.

## Why this project?

Healthcare datasets are often distributed across multiple CSV files and require technical knowledge to explore, filter and combine.

Health Data Agent was developed as an experiment in making structured health data easier to explore while preserving an important principle:

> The AI should interpret the question, but the answer should come from the data.

The system therefore does not act as a diagnostic model and does not rely on built-in medical knowledge to answer dataset questions.

## Features

- Upload individual CSV files or ZIP packages containing multiple CSVs
- Automatic CSV validation and normalization
- Encoding and separator handling
- Dataset metadata and data dictionary generation
- Natural-language queries
- Structured filters and multiple-filter queries
- Counts and distinct counts
- Aggregations (`sum`, `avg`, `count`, `min`, `max`)
- Grouping and sorting
- Cross-dataset joins
- Tabular query results
- Automatic bar charts for compatible aggregations
- Gemini as primary AI provider with Groq fallback
- Provider timeout, rate-limit and cooldown handling
- FastAPI REST API
- React web interface
- One-click synthetic healthcare demo
- Single-service deployment with the React frontend served by FastAPI

## Architecture

```text
                 ┌─────────────────────┐
                 │   CSV / ZIP Upload  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Validation &        │
                 │ Normalization       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ DataManager         │
                 │ + Metadata          │
                 └──────────┬──────────┘
                            │
          Natural-language question
                            │
                            ▼
                 ┌─────────────────────┐
                 │ LLM Planner         │
                 │ Gemini / Groq       │
                 └──────────┬──────────┘
                            │
                     Structured query
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Validation Layer    │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Pandas Execution    │
                 │ filters / joins /   │
                 │ aggregations        │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ React UI            │
                 │ answer + table +    │
                 │ visualization       │
                 └─────────────────────┘
```

The LLM does not directly calculate statistics from the dataset. It produces a structured `DataQuery`, which is validated before the data-processing layer executes it.

## Example

The application was tested with a multi-file synthetic healthcare dataset containing patients, conditions, encounters, medications, observations and procedures.

Example questions include:

```text
How many patients are in the dataset?

What are the 5 most frequent conditions?

How many female patients have diabetes?
```

A grouped query such as:

```text
What are the 5 most frequent conditions?
```

can produce both a deterministic table and an automatic visualization.

The project is dataset-driven: answers are generated only when the required information is available in the uploaded files.

## Tech Stack

### Backend

- Python
- FastAPI
- Pandas
- NumPy
- Pydantic
- LangChain
- Google Gemini
- Groq

### Frontend

- React 19
- Vite
- Recharts
- Oxlint

### Testing

- Pytest
- HTTPX

## Project Structure

```text
health-data-agent/
├── agents/          # LLM configuration and planner prompts
├── api/             # FastAPI routes and schemas
├── frontend/        # React/Vite interface
├── pipeline/        # Loading, validation and data preparation
├── services/        # Query orchestration and provider handling
├── tests/           # Automated tests
├── tools/           # Structured data-query tools
├── app.py           # Backend entry point
└── requirements.txt
```

## Getting Started

### Requirements

- Python 3.10+
- Node.js 20+
- Gemini and/or Groq API key

Clone the repository:

```bash
git clone https://github.com/jhenifferg/health-data-agent.git
cd health-data-agent
```

### Backend

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Windows:

```powershell
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root.

Example using Gemini:

```env
AI_PROVIDER=gemini
GOOGLE_API_KEY=your_api_key
GEMINI_MODEL=gemini-flash-latest
```

Optional Groq fallback:

```env
GROQ_API_KEY=your_api_key
GROQ_MODEL=openai/gpt-oss-20b
```

Never commit API keys or the `.env` file.

Start the API:

```bash
python app.py
```

The backend runs locally on port `8000`. Interactive API documentation is available through FastAPI at `/docs`.

### Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The development interface runs locally on port `5173`.

### Integrated production build

Build the frontend and start the full application from a single server:

```bash
cd frontend
npm ci
npm run build
cd ..
python app.py
```

Open `http://localhost:8000`. FastAPI serves both the API and the compiled React interface on the same domain.

The repository also includes a `Dockerfile` and `render.yaml` for a single-service deployment. Configure `GOOGLE_API_KEY` as a secret in the hosting environment before deploying.

The built-in demo uses synthetic records from `demo_data/`; no external dataset is required to evaluate the main workflow.

## API

Main endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | API health check |
| `POST` | `/api/datasets` | Upload CSV/ZIP |
| `GET` | `/api/datasets/{dataset_id}` | Dataset metadata |
| `POST` | `/api/datasets/{dataset_id}/query` | Query a dataset |
| `POST` | `/api/workspaces` | Create a workspace |
| `GET` | `/api/workspaces/{workspace_id}` | Workspace metadata |
| `POST` | `/api/workspaces/{workspace_id}/query` | Query a workspace |

## Tests

Backend:

```bash
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Current automated backend test suite covers deterministic healthcare queries including filtering and distinct-patient counting.

## Data & Privacy

Uploaded files are processed locally by the application and runtime files are excluded from version control.

The project is designed for **data exploration and educational purposes**. It is not a medical device and should not be used for diagnosis, treatment decisions or other clinical decision-making.

Do not upload identifiable or sensitive patient information unless the deployment environment has been appropriately designed to handle it.

## Current Status

Functional MVP.

Implemented flow:

```text
Upload → metadata → natural-language question → structured query
→ deterministic execution → answer → table / visualization
```

Future improvements may include broader automated test coverage, persistent dataset sessions, richer relationship discovery and additional visualization types.
