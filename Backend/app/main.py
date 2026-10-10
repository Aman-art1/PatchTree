import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .models.schemas import Node, Run, RunCreate
from .orchestrator.pipeline import run_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="PatchTree API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

runs: dict[str, Run] = {}
nodes: dict[str, list[Node]] = {}


async def _run_pipeline(run: Run) -> None:
    try:
        updated_run, created_nodes = await run_pipeline(run)
        runs[run.run_id] = updated_run
        nodes[run.run_id] = created_nodes
    except Exception:
        logger.exception("Pipeline failed for run %s", run.run_id)
        run.status = "failed"
        run.completed_at = datetime.now(UTC)


@app.post("/runs", response_model=Run, status_code=status.HTTP_201_CREATED)
async def create_run(request: RunCreate, background_tasks: BackgroundTasks) -> Run:
    run = Run(
        **request.model_dump(),
        run_id=str(uuid4()),
        status="running",
        created_at=datetime.now(UTC),
    )
    runs[run.run_id] = run
    nodes[run.run_id] = []
    background_tasks.add_task(_run_pipeline, run)
    return run


@app.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str) -> Run:
    if run_id not in runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    return runs[run_id]


@app.get("/runs/{run_id}/tree", response_model=list[Node])
async def get_tree(run_id: str) -> list[Node]:
    await get_run(run_id)
    return nodes[run_id]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
