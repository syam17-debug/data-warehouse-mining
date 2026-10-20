"""
Main FastAPI Application Entrypoint.
Initializes REST API and mounts the Light-Themed Executive Dashboard.
"""

import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.api.routes import api_router
from backend.services.pipeline_orchestrator import pipeline_orchestrator
from backend.database.sqlite_manager import db_manager
from backend.config import HOST, PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("dwh.main")

app = FastAPI(
    title="University Data Warehouse Consolidation & Graph Entity Resolution",
    description="Schema Evolution and Slowly Changing Dimensions via Graph-based Entity Resolution and Deduplication",
    version="1.0.0"
)

# Enable CORS for localhost development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API
app.include_router(api_router)

# Frontend Path
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.on_event("startup")
def startup_event():
    """Initializes and runs the pipeline on first start if database is empty."""
    logger.info("Initializing University Data Warehouse Consolidation Engine...")
    try:
        # Check if tables exist
        if not db_manager.table_exists("dim_student_scd2"):
            logger.info("Database empty. Auto-initializing baseline and running initial pipeline...")
            pipeline_orchestrator.initialize_warehouse(force_reset=True)
            pipeline_orchestrator.run_full_consolidation_pipeline(enable_groq_llm=True)
            logger.info("Pipeline auto-initialization complete.")
    except Exception as e:
        logger.error(f"Error during startup initialization: {e}")

# Mount static frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Frontend not found at " + str(index_file)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
