from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.analyse import router as analyse_router
from api.routes.graph import router as graph_router

app = FastAPI(title="Social Network RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyse_router, tags=["Analyse"])
app.include_router(graph_router, prefix="/graph", tags=["Graph"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
