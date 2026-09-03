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


def _upload_chat_with_topics_and_isolated_person():
    """
    Alice/Bob both discuss "database" (a real shared topic), while Charlie
    sends an unrelated message with no mentions/replies/reactions to/from
    anyone, making Charlie an isolated participant. Charlie's message is
    placed well outside ChatParser's implicit-reply window (see
    IMPLICIT_REPLY_WINDOW in src/chat_parser.py) so the sequential-adjacency
    fallback used for WhatsApp-format uploads doesn't link it to Bob's.
    """
    file_content = (
        b"01/01/2023, 10:00 - Alice: Lets talk about database design today\n"
        b"01/01/2023, 10:01 - Bob: I agree database design is important\n"
        b"01/01/2023, 10:30 - Charlie: Unrelated message about lunch\n"
    )
    files = {"file": ("topics_test.txt", io.BytesIO(file_content), "text/plain")}
    response = client.post("/analyse", files=files)
    assert response.status_code == 200
    return response.json()["id"]


def test_topics_endpoint_returns_real_topics():
    """
    Regression test: this endpoint used to return a placeholder
    ({"details": "Topics currently mixed into stats block."}) instead of the
    actual extracted topics.
    """
    analysis_id = _upload_chat_with_topics_and_isolated_person()

    res = client.get(f"/graph/{analysis_id}/topics")
    assert res.status_code == 200
    data = res.json()
    assert "topics" in data
    assert isinstance(data["topics"], list)

    database_topic = next(t for t in data["topics"] if t["topic"] == "database")
    assert database_topic["message_count"] == 2


def test_communities_sentinel_matches_people_endpoint():
    """
    Regression test: an isolated participant (never mentions/replies/reacts)
    used to show up as community -1 via /people but community 0 via
    /communities — two different endpoints disagreeing about what "no
    community" means for the same person.
    """
    analysis_id = _upload_chat_with_topics_and_isolated_person()

    people_res = client.get(f"/graph/{analysis_id}/people")
    assert people_res.status_code == 200
    people = {p["name"]: p for p in people_res.json()}
    assert people["p_Charlie"]["community"] == -1

    communities_res = client.get(f"/graph/{analysis_id}/communities")
    assert communities_res.status_code == 200
    communities = communities_res.json()["communities"]
    assert "p_Charlie" in communities.get("-1", [])


def test_graph_data_endpoint():
    analysis_id = _upload_chat_with_topics_and_isolated_person()

    res = client.get(f"/graph/{analysis_id}/data")
    assert res.status_code == 200
    data = res.json()
    assert len(data["nodes"]) > 0
    assert any(n["id"] == "p_Alice" for n in data["nodes"])
    assert len(data["edges"]) > 0
    assert all("source" in e and "target" in e for e in data["edges"])
