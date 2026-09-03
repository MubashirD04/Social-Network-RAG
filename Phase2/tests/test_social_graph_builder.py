import asyncio
from datetime import datetime, timedelta

from src.social_graph_builder import SocialGraphBuilder
from src.social_models import Message

BASE_TIME = datetime(2024, 1, 1, 10, 0, 0)


def run(coro):
    return asyncio.run(coro)


def test_person_and_message_nodes_created():
    messages = [
        Message(id="1", sender="Alice", content="Hey everyone", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="Hi Alice", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    builder = SocialGraphBuilder()
    stats = run(builder.process_chat_data(messages, chat_name="test_chat"))

    assert stats["total_people"] == 2
    assert stats["total_messages"] == 2
    assert builder.graph.has_node("p_Alice")
    assert builder.graph.has_node("p_Bob")
    assert builder.graph.has_node("m_1")
    assert builder.graph.has_node("m_2")
    assert builder.graph.get_edge_data("p_Alice", "m_1")["relationship"] == "SENT"


def test_inferred_mention_reply_does_not_create_orphan_node():
    """
    Regression test: a message that opens with "@name" and has no explicit
    reply_to used to be wired up with the raw, unprefixed message id
    (msg.id) instead of the graph's actual node id (m_{msg.id}), silently
    creating a second, attribute-less node per inferred reply.
    """
    messages = [
        Message(id="1", sender="Alice", content="Hey team", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="@Alice sounds good", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    # The raw, unprefixed message id must never appear as its own node.
    assert not builder.graph.has_node("2")

    # The inferred reply edge should connect the real message nodes.
    assert builder.graph.has_edge("m_2", "m_1")
    assert builder.graph.get_edge_data("m_2", "m_1")["relationship"] == "REPLIED_TO"


def test_isolated_participant_has_consistent_no_community_value():
    """
    Regression test: a participant who never mentions/replies/reacts never
    appears in the internal interaction graph, so community detection never
    visits them. They must still get an explicit, consistent "no community"
    sentinel (-1) rather than being left unset.
    """
    messages = [
        Message(id="1", sender="Bob", content="Morning", timestamp=BASE_TIME),
        Message(id="2", sender="Alice", content="Morning Bob", timestamp=BASE_TIME + timedelta(minutes=1), reply_to="1"),
        Message(id="3", sender="Charlie", content="Just checking in, no replies here", timestamp=BASE_TIME + timedelta(minutes=2)),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    assert builder.graph.nodes["p_Charlie"]["community"] == -1

    report = {entry["name"]: entry for entry in builder.get_influence_report()}
    assert report["p_Charlie"]["community"] == -1


def test_explicit_reply_updates_interaction_metrics():
    messages = [
        Message(id="1", sender="Bob", content="Morning", timestamp=BASE_TIME),
        Message(id="2", sender="Alice", content="Morning Bob", timestamp=BASE_TIME + timedelta(minutes=1), reply_to="1"),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    report = {entry["name"]: entry for entry in builder.get_influence_report()}
    assert report["p_Bob"]["replies_received"] == 1
    assert builder.graph.get_edge_data("p_Alice", "p_Bob")["relationship"] == "INTERACTS_WITH"


def test_get_topics_returns_real_topic_details():
    """
    Regression test: GET /graph/{id}/topics used to return a placeholder
    ("topics currently mixed into stats block") instead of real topic data.
    SocialGraphBuilder.get_topics() is what the fixed route now calls.
    """
    messages = [
        Message(id="1", sender="Alice", content="Let's talk about database design today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="I agree, database design is important", timestamp=BASE_TIME + timedelta(minutes=1)),
        Message(id="3", sender="Charlie", content="Unrelated message regarding lunch", timestamp=BASE_TIME + timedelta(minutes=2)),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    topics = builder.get_topics()
    assert isinstance(topics, list)
    assert all({"topic", "message_count", "message_ids"} <= entry.keys() for entry in topics)

    database_topic = next(t for t in topics if t["topic"] == "database")
    assert database_topic["message_count"] == 2
    assert set(database_topic["message_ids"]) == {"m_1", "m_2"}
    # Sorted by message_count descending, so the most-discussed topic leads.
    assert topics[0]["topic"] == "database"
