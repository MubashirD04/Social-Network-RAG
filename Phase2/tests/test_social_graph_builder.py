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


def test_unthreaded_messages_connect_when_they_share_real_content():
    """
    Most real chat is never formally threaded — people just reply in the
    channel. Before _infer_lexical_continuity existed, two messages with no
    explicit reply_to and no shared @mention had zero connection between
    them, even when they were obviously the same back-and-forth (e.g. "is
    the coffee machine broken again?" / "yeah, facilities is on it").
    """
    messages = [
        Message(id="1", sender="Liam", content="Is the coffee machine on 3 broken again?", timestamp=BASE_TIME, channel="watercooler"),
        Message(id="2", sender="Jamal", content="Someone start a petition, we need that coffee machine fixed", timestamp=BASE_TIME + timedelta(minutes=2), channel="watercooler"),
        Message(id="3", sender="Kira", content="The coffee machine on 2 still works fine", timestamp=BASE_TIME + timedelta(minutes=4), channel="watercooler"),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    assert builder.graph.get_edge_data("m_2", "m_1")["relationship"] == "REPLIED_TO"
    assert builder.graph.get_edge_data("m_2", "m_1")["inferred"] is True
    assert builder.graph.get_edge_data("m_3", "m_2")["relationship"] == "REPLIED_TO"


def test_inferred_connections_do_not_affect_influence_scores():
    """
    Regression test: _infer_lexical_continuity used to merge its guessed
    person-to-person connections into the same 'weight' field that feeds
    PageRank/betweenness/community detection, and its guessed REPLIED_TO
    edges counted toward 'replies_received' — so purely inferred chatter
    (no real reply/mention anywhere) diluted influence scores instead of
    leaving them at their true, uniform baseline.
    """
    messages = [
        Message(id="1", sender="Liam", content="Is the coffee machine on 3 broken again?", timestamp=BASE_TIME, channel="watercooler"),
        Message(id="2", sender="Jamal", content="Someone start a petition, we need that coffee machine fixed", timestamp=BASE_TIME + timedelta(minutes=2), channel="watercooler"),
        Message(id="3", sender="Kira", content="The coffee machine on 2 still works fine", timestamp=BASE_TIME + timedelta(minutes=4), channel="watercooler"),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    # Sanity check: these messages really did only get connected via
    # inference, not any real reply/mention.
    assert builder.graph.get_edge_data("m_2", "m_1")["inferred"] is True
    assert builder.graph.get_edge_data("m_3", "m_2")["inferred"] is True

    report = {entry["label"]: entry for entry in builder.get_influence_report()}
    scores = {entry["pagerank"] for entry in report.values()}
    # No real interactions exist, so nobody should be ranked above anyone
    # else and nobody should show a "reply received".
    assert len(scores) == 1
    for entry in report.values():
        assert entry["replies_received"] == 0
        assert entry["community"] == -1
        assert entry["is_influencer"] is False
        assert entry["is_info_broker"] is False


def test_lexical_continuity_does_not_cross_channels_or_stay_stale():
    """
    The inference must be scoped tightly enough to only ever fire on
    messages a person would plausibly read as one conversation: never across
    two different channels that happen to share vocabulary, and never
    across a gap so long the earlier message has scrolled out of view.
    """
    messages = [
        Message(id="1", sender="Alice", content="Kicking off the database migration today", timestamp=BASE_TIME, channel="engineering"),
        # Same words, different channel — must not connect to message 1.
        Message(id="2", sender="Farah", content="Marketing sync: database migration timing affects the launch page", timestamp=BASE_TIME + timedelta(minutes=1), channel="marketing"),
        # Same channel and words, but far outside the lookback window.
        Message(id="3", sender="Bob", content="Revisiting that database migration decision from way earlier", timestamp=BASE_TIME + timedelta(hours=5), channel="engineering"),
    ]
    builder = SocialGraphBuilder()
    run(builder.process_chat_data(messages, chat_name="test_chat"))

    assert not builder.graph.has_edge("m_2", "m_1")
    assert not builder.graph.has_edge("m_3", "m_1")
