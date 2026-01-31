from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key:str
    roq_extraction_model: str = "llama-3.1-8b-instant" 
    groq_answer_model: str = "llama-3.3-70b-versatile" # llama-3.3-70b-versatile
    
    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    
    # Text processing
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50
    
    class Config:
        env_file = ".env"
        
settings = Settings
    