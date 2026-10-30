import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from src.chat_parser import ChatParser
from src.analysis import run_analysis
from src.llm_service import retrieval_service
from src.coref_resolver import get_embedding_texts
from api.store import analysis_store

router = APIRouter()

class AnalyseResponse(BaseModel):
    id: str
    stats: Dict[str, Any]

@router.post("/analyse", response_model=AnalyseResponse)
async def analyse_chat(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Save the uploaded file temporarily to parse
    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            messages = ChatParser.parse_file(tmp_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing file: {str(e)}")
        finally:
            os.unlink(tmp_path)
        
        chat_name = os.path.splitext(file.filename)[0]

        # Phase 3: Execute Retrieval Embeddings Generation
        # (1:1 mapping message.content -> Vector). get_embedding_texts only
        # substitutes coreference-resolved text when
        # CONVERSATION_LINKING_COREF_ENABLED is set (off by default — see
        # src/coref_resolver.py); message.content itself is untouched either
        # way, so nothing else here changes.
        texts = get_embedding_texts(messages)
        embeddings_matrix = retrieval_service.generate_embeddings(texts)

        analysis = await run_analysis(messages, embeddings_matrix, chat_name)

        # Save to store
        analysis_id = analysis_store.save(
            analysis["builder"],
            analysis["stats"],
            messages=messages,
            embeddings=embeddings_matrix,
            inferred_links=analysis["inferred_links"]
        )

        return AnalyseResponse(id=analysis_id, stats=analysis["stats"])
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
