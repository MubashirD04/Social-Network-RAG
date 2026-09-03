from typing import List
from fastembed import TextEmbedding
import numpy as np

class LLMService:
    """
    Provides local embedding generation for the Retrieval Layer.
    Uses fastembed (ONNX Runtime, no PyTorch) to encode text into semantic vectors.
    """

    def __init__(self):
        print("Loading fastembed model...")
        self.embedder = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self._dimension = len(next(iter(self.embedder.embed(["dimension probe"]))))
        print(f"Embeddings model loaded successfully (dimension: {self._dimension})")

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts using local model.
        Returns a numpy array of embeddings.
        """
        if not texts:
            return np.array([])

        embeddings = list(self.embedder.embed(texts))
        return np.array(embeddings)

    def get_embeddings_dimension(self) -> int:
        return self._dimension

    def get_top_k_similar(self, query: str, embeddings: np.ndarray, k: int = 5) -> List[tuple[int, float]]:
        """
        Compute cosine similarity between the query and stored embeddings.
        Returns indices of top K results along with their similarity scores.
        """
        if embeddings.shape[0] == 0:
            return []

        query_embedding = self.generate_embeddings([query])[0]

        # Calculate cosine similarity using numpy dot product
        # normalise vectors to unit length first
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return []
        query_embedding = query_embedding / query_norm

        norms = np.linalg.norm(embeddings, axis=1)
        # Avoid division by zero
        valid_indices = norms > 0

        similarities = np.zeros(embeddings.shape[0])
        safe_embeddings = embeddings[valid_indices] / norms[valid_indices, np.newaxis]

        similarities[valid_indices] = np.dot(safe_embeddings, query_embedding)

        # Get top K indices
        # argsort sorts in ascending order, so we reverse it
        top_indices = np.argsort(similarities)[::-1][:k]

        return [(int(idx), float(similarities[idx])) for idx in top_indices if similarities[idx] > 0]

    async def extract_topics(self, messages: List[str], top_n: int = 5) -> List[str]:
        """
        Extract main topics from a list of messages using YAKE.
        """
        try:
            import yake

            # Combine messages into a single text for topic extraction
            text = " ".join(messages)
            if not text.strip():
                return []

            kw_extractor = yake.KeywordExtractor(lan="en", n=2, top=top_n)
            keywords = kw_extractor.extract_keywords(text)
            return [kw[0] for kw in keywords[:top_n]]
        except Exception as e:
            print(f"Topic extraction error: {e}")
            return []

# Global singleton instance
retrieval_service = LLMService()
