# pip install sentence-transformers
from sentence_transformers import SentenceTransformer
import numpy as np

class NeuralVectorStore:
    """
    Replaces TF-IDF with a real transformer-based embedding model.
    This IS deep learning — the model runs locally on your machine.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        # Downloads a 90MB transformer model — runs on CPU
        self.model = SentenceTransformer(model_name)
        self._embeddings: list[np.ndarray] = []
        self._meta: list[dict] = []

    def add(self, text: str, meta: dict) -> None:
        vector = self.model.encode(text, convert_to_numpy=True)
        self._embeddings.append(vector)
        self._meta.append(meta)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._embeddings:
            return []
        q_vec = self.model.encode(query, convert_to_numpy=True)
        # Cosine similarity
        matrix = np.stack(self._embeddings)
        scores = matrix @ q_vec / (
            np.linalg.norm(matrix, axis=1) * np.linalg.norm(q_vec) + 1e-9
        )
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            {**self._meta[i], "score": float(scores[i])}
            for i in top_indices if scores[i] > 0.1
        ]