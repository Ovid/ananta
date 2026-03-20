#!/usr/bin/env python3
"""Example FastAPI service wrapping Ananta."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ananta import Ananta
from ananta.exceptions import ProjectExistsError, ProjectNotFoundError

# Global Ananta instance
ananta: Ananta | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage Ananta lifecycle."""
    global ananta
    ananta = Ananta(
        model="claude-sonnet-4-20250514",
        storage_path="./service_data",
    )
    ananta.start()
    yield
    ananta.stop()


app = FastAPI(
    title="Ananta API",
    description="Query documents using Recursive Language Models",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    """Request body for queries."""

    question: str


class QueryResponse(BaseModel):
    """Response from a query."""

    answer: str
    execution_time: float
    total_tokens: int


@app.post("/projects")
def create_project(project_id: str) -> dict[str, str]:
    """Create a new project."""
    if ananta is None:
        raise HTTPException(500, "Ananta not initialized")
    try:
        ananta.create_project(project_id)
        return {"status": "created", "project_id": project_id}
    except ProjectExistsError as e:
        raise HTTPException(400, str(e))


@app.get("/projects")
def list_projects() -> dict[str, list[str]]:
    """List all projects."""
    if ananta is None:
        raise HTTPException(500, "Ananta not initialized")
    return {"projects": ananta.list_projects()}


@app.post("/projects/{project_id}/query")
def query_project(project_id: str, request: QueryRequest) -> QueryResponse:
    """Query a project's documents."""
    if ananta is None:
        raise HTTPException(500, "Ananta not initialized")
    try:
        project = ananta.get_project(project_id)
        result = project.query(request.question)
        return QueryResponse(
            answer=result.answer,
            execution_time=result.execution_time,
            total_tokens=result.token_usage.total_tokens,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    """Delete a project."""
    if ananta is None:
        raise HTTPException(500, "Ananta not initialized")
    ananta.delete_project(project_id)
    return {"status": "deleted", "project_id": project_id}


# Run with: uvicorn examples.fastapi_service:app --reload
