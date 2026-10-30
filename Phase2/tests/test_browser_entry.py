import asyncio
import json

import numpy as np

from src import browser_entry


def _analyse(tmp_path):
    chat = tmp_path / "team.txt"
    chat.write_text(
        "01/01/2023, 10:00 - Alice: the database migration failed\n"
        "01/01/2023, 10:01 - Bob: rolling back the database migration\n"
        "01/01/2023, 10:02 - Alice: pricing page looks good\n"
    )
    texts = json.loads(browser_entry.parse_file(str(chat)))
    assert len(texts) == 3

    embeddings = np.eye(4, dtype=np.float32)[:3]
    return json.loads(asyncio.run(browser_entry.analyse(embeddings.tobytes(), 4, "team")))


def test_analyse_returns_serialized_graph(tmp_path):
    result = _analyse(tmp_path)

    assert result["id"]
    node_ids = {node["id"] for node in result["graph"]["nodes"]}
    assert {"p_Alice", "p_Bob"} <= node_ids
    assert result["graph"]["edges"]


def test_query_ranks_by_supplied_embedding(tmp_path):
    _analyse(tmp_path)

    query = np.array([0, 0, 1, 0], dtype=np.float32)
    results = json.loads(browser_entry.query(query.tobytes(), 2))["results"]

    assert results[0]["content"] == "pricing page looks good"
    assert results[0]["score"] > 0.99


def test_set_topic_count_returns_graph(tmp_path):
    _analyse(tmp_path)

    graph = json.loads(asyncio.run(browser_entry.set_topic_count(5)))

    assert graph["nodes"]
