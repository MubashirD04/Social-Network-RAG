import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes.analyse import router as analyse_router
from api.routes.graph import router as graph_router

app = FastAPI(title="Social Network RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # No auth/cookies exist in this API. allow_credentials=True combined with
    # a wildcard origin lets browsers echo back any Origin for credentialed
    # requests, so keep it False unless real auth is added later.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyse_router, tags=["Analyse"])
app.include_router(graph_router, prefix="/graph", tags=["Graph"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Mount frontend static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"Warning: Frontend build directory not found at {static_dir}. Run 'npm run build' in Phase2/frontend.")
