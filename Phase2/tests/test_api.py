import pytest
from fastapi.testclient import TestClient
import io

from api.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_analyse_and_get():
    # Mock a WhatsApp txt file upload
    file_content = b"01/01/2023, 10:00 - Alice: Hey\n01/01/2023, 10:01 - Bob: Hi"
    files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    
    response = client.post("/analyse", files=files)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "stats" in data
    analysis_id = data["id"]
    
    # Test getting metadata
    res = client.get(f"/graph/{analysis_id}")
    assert res.status_code == 200
    assert res.json()["id"] == analysis_id
    
    # Test getting people
    res = client.get(f"/graph/{analysis_id}/people")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    
    # Test getting communities
    res = client.get(f"/graph/{analysis_id}/communities")
    assert res.status_code == 200
    assert "communities" in res.json()

    # Test semantic query
    res = client.post(f"/graph/{analysis_id}/query", json={"query": "Alice says hey", "top_k": 2})
    assert res.status_code == 200
    query_data = res.json()
    assert "results" in query_data
    assert len(query_data["results"]) > 0
    assert "score" in query_data["results"][0]
    assert "message_id" in query_data["results"][0]

    # Test delete
    res = client.delete(f"/graph/{analysis_id}")
    assert res.status_code == 200
    
    # Verify deletion
    res = client.get(f"/graph/{analysis_id}")
    assert res.status_code == 404
