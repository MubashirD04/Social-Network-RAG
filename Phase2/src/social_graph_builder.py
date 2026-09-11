import networkx as nx
import numpy as np
from pyvis.network import Network
from src.social_models import Message
from src.llm_service import LLMService
from typing import List, Dict, Any
import asyncio
from datetime import datetime, timedelta
import re
from networkx.algorithms import community

class SocialGraphBuilder:
    DEFAULT_TOPIC_COUNT = 5

    # Tuning for _infer_lexical_continuity: how far back (in messages and in
    # time) an unthreaded message is allowed to look for something it
    # plausibly continues. Slack channel chatter is bursty but slower-paced
    # than a WhatsApp thread, hence the wider window than the WhatsApp
    # parser's own 5-minute implicit-reply heuristic.
    CONTINUITY_LOOKBACK_MESSAGES = 6
    CONTINUITY_LOOKBACK_WINDOW = timedelta(minutes=15)

    # Common words long enough to clear the 4-char "distinctive" bar but too
    # generic to mean two messages are actually about the same thing — left
    # deliberately small (a handful of frequent connectives/fillers) rather
    # than a full stopword corpus, since false negatives here just cost a
    # missed connection while false positives create a wrong one.
    _CONTINUITY_STOPWORDS = frozenset({
        "this", "that", "these", "those", "have", "haven", "having", "been",
        "with", "from", "they", "them", "their", "were", "will", "would",
        "wouldn", "could", "couldn", "should", "shouldn", "also", "just",
        "really", "think", "about", "after", "before", "today", "tomorrow",
        "yesterday", "week", "weeks", "team", "work", "works", "working",
        "time", "times", "great", "nice", "good", "much", "many", "need",
        "needs", "make", "made", "going", "doing", "done", "lets", "thanks",
        "thank", "everyone", "people", "things", "thing", "still", "already",
        "again", "around", "because", "doesn", "didn", "isn", "aren", "wasn",
        "cannot", "yeah", "okay", "sure", "sounds", "sound", "looks",
        "looking", "look", "actually", "probably", "maybe", "kind", "sort",
        "here", "there", "than", "then", "over", "into", "onto", "some",
        "when", "what", "which", "your", "youre", "next", "more", "most",
        "well", "very", "even", "back", "know", "want", "wants", "wanted",
        "come", "coming", "give", "take", "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday",
    })

    def __init__(self):
        self.graph = nx.DiGraph() # Directed graph for detailed interactions
        self.llm = LLMService()
        self.messages: List[Message] = []
        self.chat_name: str = ""

    async def process_chat_data(self, messages: List[Message], chat_name: str):
        print(f"\n{'='*80}")
        print(f"Processing Chat: {chat_name}")
        print(f"{'='*80}")

        # 1. Add Chat Node
        self.graph.add_node(
            chat_name,
            type="chat",
            label=chat_name,
            color="#FF6B6B", # Red
            size=30,
            shape="box"
        )

        # 2. Add Person and Message Nodes
        people = set()
        person_to_last_msg = {}
        # `@mention` text almost never spells out a sender's full display
        # name (a Slack real_name like "Alice Nguyen" gets mentioned as
        # "@Alice") — `\w+` mention matches stop at the first space anyway.
        # Without resolving through this lookup, every such mention forged a
        # second, disconnected person node ("p_Alice" alongside the real
        # "p_Alice Nguyen"), fragmenting that person's stats across two
        # nodes. Keyed by first-name lower-case; ambiguous when two senders
        # share a first name, same as the mention text itself is ambiguous.
        sender_by_first_token: Dict[str, str] = {}
        print("\nBuilding social network...")

        for msg in messages:
            p_id = f"p_{msg.sender}"
            m_id = f"m_{msg.id}"

            # Person Node
            if msg.sender not in people:
                people.add(msg.sender)
                sender_by_first_token[msg.sender.split()[0].lower()] = msg.sender
                self.graph.add_node(
                    p_id,
                    type="person",
                    label=msg.sender,
                    title=msg.sender,
                    color="#4ECDC4",
                    size=20,
                    shape="dot"
                )

            # Message Node
            msg_label = f"{msg.content[:20]}..."
            self.graph.add_node(
                m_id,
                type="message",
                label=msg_label,
                title=f"{msg.sender}: {msg.content}\n{msg.timestamp}",
                text=msg.content,
                sender=msg.sender,
                timestamp=msg.timestamp.isoformat(),
                color="#A0D2EB",
                size=10,
                shape="ellipse"
            )

            # EDGE: SENT (Person -> Message)
            self.graph.add_edge(p_id, m_id, relationship="SENT", color="#CCCCCC", width=1)

            # EDGE: PART_OF (Message -> Chat)
            self.graph.add_edge(m_id, chat_name, relationship="PART_OF", color="#EEEEEE", width=0.5)

            # OPTIMIZATION: Explicit Mention Parsing using Regex
            mentions = re.findall(r'@(\w+)', msg.content)

            # INFERENCE: If message starts with @name and has no reply_to, infer REPLIED_TO
            if not msg.reply_to and msg.content.startswith('@'):
                first_mention_match = re.search(r'^@(\w+)', msg.content)
                if first_mention_match:
                    raw_mention = first_mention_match.group(1)
                    mentioned_name = sender_by_first_token.get(raw_mention.lower(), raw_mention)
                    if mentioned_name in person_to_last_msg:
                        self.graph.add_edge(
                            m_id, person_to_last_msg[mentioned_name],
                            relationship="REPLIED_TO",
                            color="#FFD93D",
                            width=1.5,
                            title=f"Inferred Reply to {mentioned_name}"
                        )

            # MENTION PARSING
            for raw_mention in mentions:
                mentioned_person = sender_by_first_token.get(raw_mention.lower(), raw_mention)
                mp_id = f"p_{mentioned_person}"
                # Add node if not exists (though usually they are senders, sometimes they might not be)
                if mentioned_person not in people:
                    people.add(mentioned_person)
                    self.graph.add_node(
                        mp_id,
                        type="person",
                        label=mentioned_person,
                        title=mentioned_person,
                        color="#4ECDC4",
                        size=20,
                        shape="dot"
                    )

                # Create explicit MENTIONED edge
                self.graph.add_edge(
                    m_id,
                    mp_id,
                    relationship="MENTIONED",
                    color="#A58DFF", # Purple for mentions
                    width=1.5,
                    dashes=True
                )

                # Also infer interaction for metrics (Person -> Person)
                if mentioned_person != msg.sender:
                    if self.graph.has_edge(p_id, mp_id):
                        self.graph[p_id][mp_id]['weight'] = self.graph[p_id][mp_id].get('weight', 0) + 1
                    else:
                        self.graph.add_edge(
                            p_id,
                            mp_id,
                            relationship="INTERACTS_WITH",
                            weight=1,
                            color="rgba(255, 255, 255, 0.2)",
                            hidden=True
                        )

            # EDGE: REPLIED_TO (Message -> Message)
            if msg.reply_to:
                rep_id = f"m_{msg.reply_to}"
                if self.graph.has_node(rep_id):
                    self.graph.add_edge(
                        m_id,
                        rep_id,
                        relationship="REPLIED_TO",
                        color="#FFD93D", # Yellow arrows for flow
                        width=2,
                        title="Replying to"
                    )

                    # EDGE: INTERACTS_WITH (Person -> Person inferred from reply)
                    try:
                        original_sender_edge = next(u for u, v, d in self.graph.in_edges(rep_id, data=True) if d['relationship'] == 'SENT')
                        if original_sender_edge != p_id:
                            if self.graph.has_edge(p_id, original_sender_edge):
                                self.graph[p_id][original_sender_edge]['weight'] += 1
                            else:
                                self.graph.add_edge(
                                    p_id,
                                    original_sender_edge,
                                    relationship="INTERACTS_WITH",
                                    weight=1,
                                    color="rgba(255, 255, 255, 0.2)",
                                    hidden=True # Hidden in visual, used for calculation
                                )
                    except StopIteration:
                        pass

            # Handle Reactions (Person -> Message)
            for reactor in msg.reactions:
                r_id = f"p_{reactor}"
                if reactor not in people:
                    people.add(reactor)
                    self.graph.add_node(r_id, type="person", label=reactor, title=reactor, color="#4ECDC4", shape="dot")

                self.graph.add_edge(
                    r_id,
                    m_id,
                    relationship="REACTED_TO",
                    color="#FF8E00", # Orange
                    width=1,
                    dashes=True
                )

            # Update last message for this person
            person_to_last_msg[msg.sender] = m_id

        print(f"   Added {len(people)} participants and {len(messages)} messages")

        # 2b. Most real chat is never formally threaded — people just reply
        # in the channel. Without this, a message only connects to another
        # message via an explicit reply/mention, so an entire unthreaded
        # back-and-forth (e.g. "is the coffee machine broken again?" / "yeah,
        # facilities is on it") renders as disconnected dots even though any
        # human reading it immediately sees it's one conversation.
        self._infer_lexical_continuity(messages)

        # 2c. Map nested reply threads so the frontend can render depth
        # instead of just flat reply edges.
        self._compute_reply_threads()

        # Stashed so regenerate_topics() can re-run extraction at a
        # different top_n later without needing the original messages
        # passed back in (the frontend lets viewers pick a topic count of
        # 5-10 after the graph is already built).
        self.messages = messages
        self.chat_name = chat_name

        # 3. Topic Extraction (Async)
        await self._apply_topics(messages, chat_name, top_n=self.DEFAULT_TOPIC_COUNT)

        # 4. Calculate Social Stats & Communities
        return self._calculate_stats()

    async def _apply_topics(self, messages: List[Message], chat_name: str, top_n: int):
        """
        (Re)runs topic extraction and rewires the topic layer of the graph:
        drops any existing topic nodes (and, since networkx removes incident
        edges with them, their DISCUSSED/MENTIONS_TOPIC edges too), then adds
        fresh ones for the new topic set. Person/message nodes and all social
        stats are untouched, so this is cheap enough to call every time a
        viewer changes the topic count slider.
        """
        print("\nExtracting topics...")
        for node, data in list(self.graph.nodes(data=True)):
            if data.get('type') == 'topic':
                self.graph.remove_node(node)

        # Extract from message content alone — including "sender: " prefixes
        # here made participant names the most repeated, highest-signal
        # n-grams in the corpus, so YAKE surfaced people's names as "topics"
        # instead of what was actually discussed. Participant names are also
        # excluded explicitly in case someone's name appears in-line in the
        # text itself (e.g. "hey John, ...").
        msg_texts = [m.content for m in messages]
        participant_names = {m.sender for m in messages}
        topics = await self.llm.extract_topics(msg_texts, top_n=top_n, exclude_terms=participant_names)

        for topic in topics:
            self.graph.add_node(
                topic,
                type="topic",
                label=topic,
                color="#FFD93D", # Yellow
                shape="diamond",
                size=25
            )

            # Connect chat to topic
            self.graph.add_edge(chat_name, topic, relationship="DISCUSSED", width=1)

            # Connect relevant messages to topic (Fuzzy Match)
            # A multi-word topic (e.g. a YAKE bigram like "database design")
            # no longer needs to appear as one exact phrase. Instead every
            # constituent word must appear somewhere in the message, and each
            # word matches as a prefix (\w*) so morphological variants like
            # "designing"/"designed" still count as a match for "design".
            topic_words = [w for w in re.split(r'\s+', topic) if w]
            word_patterns = [re.compile(r'\b' + re.escape(w) + r'\w*', re.IGNORECASE) for w in topic_words]
            for msg in messages:
                if word_patterns and all(p.search(msg.content) for p in word_patterns):
                     self.graph.add_edge(f"m_{msg.id}", topic, relationship="MENTIONS_TOPIC", color="rgba(255, 217, 61, 0.3)", dashes=True)

        print(f"   Identified topics: {topics}")

    async def regenerate_topics(self, top_n: int):
        """Re-extracts topics at a new top_n against the same messages this
        chat was originally built from. Used by the topic-count control in
        the frontend so changing it doesn't require re-uploading the file."""
        await self._apply_topics(self.messages, self.chat_name, top_n=top_n)
        return self.get_topics()

    def _infer_lexical_continuity(self, messages: List[Message]):
        """
        Connects a message that has no explicit or mention-inferred reply to
        the nearest still-recent message in the same channel that it shares
        a distinctive word with — e.g. two messages that both say "coffee
        machine" a few turns apart, with nothing to formally thread them
        together. Reuses the REPLIED_TO relationship (tagged `inferred`,
        colored differently) so thread-depth rendering picks these up for
        free, rather than inventing a parallel edge type the frontend would
        need to special-case.

        Scoped per-channel and to a short lookback window so it can only
        ever link messages a person skimming the export would plausibly
        read as the same conversation — never two unrelated messages that
        happen to land close together across different channels or days.

        Never feeds influence/broker/community scores: every edge this
        creates is tagged 'inferred' (message-level) or given weight=0 with
        the increment recorded in 'inferred_weight' instead (person-level),
        and _calculate_stats only reads 'weight' for its metrics.
        """
        # Reused as a stoplist so two messages don't get linked just for
        # both mentioning the same participant by name.
        participant_tokens = set()
        for m in messages:
            participant_tokens.update(m.sender.lower().split())

        def tokenize(text: str) -> set:
            words = re.findall(r"[a-zA-Z]{4,}", text.lower())
            return {
                w for w in words
                if w not in self._CONTINUITY_STOPWORDS and w not in participant_tokens
            }

        by_channel: Dict[Any, List[Message]] = {}
        for m in messages:
            by_channel.setdefault(m.channel, []).append(m)

        for channel_messages in by_channel.values():
            for i, msg in enumerate(channel_messages):
                m_id = f"m_{msg.id}"

                already_connected = any(
                    d.get('relationship') == 'REPLIED_TO'
                    for _, _, d in self.graph.out_edges(m_id, data=True)
                )
                if already_connected:
                    continue

                msg_tokens = tokenize(msg.content)
                if not msg_tokens:
                    continue

                window_start = max(0, i - self.CONTINUITY_LOOKBACK_MESSAGES)
                for prior in reversed(channel_messages[window_start:i]):
                    if msg.timestamp - prior.timestamp > self.CONTINUITY_LOOKBACK_WINDOW:
                        break
                    if prior.sender == msg.sender:
                        continue

                    shared = msg_tokens & tokenize(prior.content)
                    if not shared:
                        continue

                    prior_id = f"m_{prior.id}"
                    if not self.graph.has_node(prior_id):
                        continue

                    self.graph.add_edge(
                        m_id, prior_id,
                        relationship="REPLIED_TO",
                        inferred=True,
                        color="rgba(160, 180, 200, 0.5)",  # muted blue-gray, distinct from the solid yellow of a confirmed reply
                        width=1,
                        dashes=True,
                        title=f"Inferred connection (shared: {', '.join(sorted(shared))})"
                    )

                    # Tracked separately from 'weight' (and never marked
                    # 'inferred' on top of a real edge): _calculate_stats
                    # only sums 'weight' into the interaction graph that
                    # feeds PageRank/betweenness/community detection, so a
                    # guessed connection can never inflate or dilute another
                    # person's influence score. It still renders on the
                    # frontend (dashed, toggleable) via the 'inferred' flag.
                    if self.graph.has_edge(f"p_{msg.sender}", f"p_{prior.sender}"):
                        edge_data = self.graph[f"p_{msg.sender}"][f"p_{prior.sender}"]
                        edge_data['inferred_weight'] = edge_data.get('inferred_weight', 0) + 1
                    else:
                        self.graph.add_edge(
                            f"p_{msg.sender}", f"p_{prior.sender}",
                            relationship="INTERACTS_WITH",
                            weight=0,
                            inferred_weight=1,
                            inferred=True,
                            color="rgba(255, 255, 255, 0.2)",
                            hidden=True
                        )
                    break

    def _compute_reply_threads(self):
        """
        Walks REPLIED_TO chains to give every message node a reply_depth
        (0 = root of its thread), a thread_root (the id of that root
        message), and a thread_size (total messages in that thread). The
        frontend uses these to render nested threads distinctly instead of
        just drawing flat, same-looking reply edges.
        """
        message_nodes = [n for n, d in self.graph.nodes(data=True) if d.get('type') == 'message']

        parent_of = {}
        for m_id in message_nodes:
            parent_of[m_id] = next(
                (v for _, v, d in self.graph.out_edges(m_id, data=True)
                 if d.get('relationship') == 'REPLIED_TO'),
                None
            )

        depth: Dict[str, int] = {}
        root: Dict[str, str] = {}

        for m_id in message_nodes:
            if m_id in depth:
                continue

            # Walk up the chain, collecting nodes until we hit one that's
            # already resolved, the top of the chain, or a cycle (bad data).
            chain = []
            node = m_id
            while node is not None and node not in depth and node not in chain:
                chain.append(node)
                node = parent_of.get(node)

            if node is not None and node in depth:
                base_depth, base_root = depth[node], root[node]
            else:
                base_depth, base_root = -1, chain[-1]

            for n in reversed(chain):
                base_depth += 1
                depth[n] = base_depth
                root[n] = base_root

        thread_sizes: Dict[str, int] = {}
        for m_id in message_nodes:
            thread_sizes[root[m_id]] = thread_sizes.get(root[m_id], 0) + 1

        for m_id in message_nodes:
            self.graph.nodes[m_id]['reply_depth'] = depth[m_id]
            self.graph.nodes[m_id]['thread_root'] = root[m_id]
            self.graph.nodes[m_id]['thread_size'] = thread_sizes[root[m_id]]

    def _calculate_stats(self):
        print("\nCalculating social metrics...")

        # Create a simplified person-to-person interaction graph for metrics.
        # Only 'weight' (real replies/@mentions) counts here — an edge that
        # exists purely from _infer_lexical_continuity's guesswork carries
        # weight=0 (its contribution lives in 'inferred_weight' instead), so
        # it's excluded from PageRank/betweenness/community detection
        # entirely rather than watering down scores built on real activity.
        interaction_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            if data.get('relationship') == 'INTERACTS_WITH' and data.get('weight', 0) > 0:
                if interaction_graph.has_edge(u, v):
                    interaction_graph[u][v]['weight'] += data['weight']
                else:
                    interaction_graph.add_edge(u, v, weight=data['weight'])

        people_nodes = [n for n, d in self.graph.nodes(data=True) if d.get('type') == 'person']

        # 1. PageRank (Influence)
        try:
            pagerank = nx.pagerank(interaction_graph, weight='weight')
        except Exception:
            pagerank = {p: 0 for p in people_nodes} # Fallback if empty

        # 2. Betweenness Centrality (Info Brokers)
        try:
            betweenness = nx.betweenness_centrality(interaction_graph, weight='weight')
        except Exception:
            betweenness = {p: 0 for p in people_nodes}

        # 3. Activity (Message Count and Replies Received)
        activity = {}
        replies_received = {p: 0 for p in people_nodes}

        # Pre-map messages to senders for efficiency
        msg_to_sender = {}
        for p in people_nodes:
            # Find all messages sent by this person
            sent_msgs = [v for u, v, d in self.graph.out_edges(p, data=True) if d.get('relationship') == 'SENT']
            for m_id in sent_msgs:
                msg_to_sender[m_id] = p
            activity[p] = len(sent_msgs)

        # Count replies received — confirmed replies only (explicit reply_to
        # or a leading @mention), same reasoning as the interaction graph
        # above: a lexically-guessed connection shouldn't move this score.
        for u, v, d in self.graph.edges(data=True):
            if d.get('relationship') == 'REPLIED_TO' and not d.get('inferred'):
                # u is the reply message, v is the original message
                original_msg = v
                recipient = msg_to_sender.get(original_msg)
                if recipient:
                    replies_received[recipient] += 1

        # Badge thresholds are computed relative to this chat's own score
        # distribution (top quartile) instead of fixed constants, so badges
        # stay meaningful whether the network has 5 people or 500. When
        # scores are all tied (e.g. a tiny or perfectly symmetric network),
        # the threshold equals the scores themselves and nobody clears it —
        # there's no real standout to badge.
        pr_values = [pagerank.get(p, 0) for p in people_nodes]
        bc_values = [betweenness.get(p, 0) for p in people_nodes]
        pr_threshold = float(np.percentile(pr_values, 75)) if pr_values else 0.0
        bc_threshold = float(np.percentile(bc_values, 75)) if bc_values else 0.0

        # Update Graph Node Attributes
        for person in people_nodes:
            # Default to -1 ("no community") up front, so isolated people who
            # never appear in the interaction graph still get an explicit value
            # instead of being left unset.
            self.graph.nodes[person]['community'] = -1
            self.graph.nodes[person]['group'] = -1

            pr_score = pagerank.get(person, 0)
            bc_score = betweenness.get(person, 0)
            msg_count = activity.get(person, 0)
            recv_count = replies_received.get(person, 0)

            self.graph.nodes[person]['pagerank'] = pr_score
            self.graph.nodes[person]['betweenness'] = bc_score
            self.graph.nodes[person]['message_count'] = msg_count
            self.graph.nodes[person]['replies_received'] = recv_count

            # Badges: dynamic, percentile-based thresholds (see above)
            badges = []
            if pr_score > pr_threshold:
                badges.append("INFLUENCER")
                self.graph.nodes[person]['is_influencer'] = True
                self.graph.nodes[person]['size'] = 35 + (msg_count * 0.5)
                self.graph.nodes[person]['borderWidth'] = 3
            else:
                 self.graph.nodes[person]['is_influencer'] = False
                 self.graph.nodes[person]['size'] = 20 + (msg_count * 0.5)

            if bc_score > bc_threshold:
                badges.append("INFO_BROKER")
                self.graph.nodes[person]['is_info_broker'] = True
            else:
                self.graph.nodes[person]['is_info_broker'] = False

            self.graph.nodes[person]['title'] = f"<b>{person}</b><br/>"
            self.graph.nodes[person]['title'] += f"Messages: {msg_count}<br/>"
            self.graph.nodes[person]['title'] += f"Replies Received: {recv_count}<br/>"
            self.graph.nodes[person]['title'] += f"Influence: {pr_score:.2f}<br/>"
            self.graph.nodes[person]['title'] += f"Badges: {', '.join(badges)}<br/>"
            self.graph.nodes[person]['title'] += f"Community: {self.graph.nodes[person].get('community', 'N/A')}"

        # OPTIMIZATION: Community Detection
        self._detect_communities(interaction_graph, people_nodes)

        # Prepare summary stats
        influencers = sorted([{'name': k, 'score': v} for k, v in pagerank.items()], key=lambda x: x['score'], reverse=True)[:3]
        brokers = sorted([{'name': k, 'score': v} for k, v in betweenness.items()], key=lambda x: x['score'], reverse=True)[:3]
        most_active = sorted([{'name': k, 'messages': v} for k, v in activity.items()], key=lambda x: x['messages'], reverse=True)[:3]

        return {
            "total_people": len(people_nodes),
            "total_messages": len([n for n, d in self.graph.nodes(data=True) if d.get('type') == 'message']),
            "total_topics": len([n for n, d in self.graph.nodes(data=True) if d.get('type') == 'topic']),
            "influencers": influencers,
            "info_brokers": brokers,
            "most_active": most_active
        }

    def _detect_communities(self, graph, nodes):
        if not nodes or graph.number_of_nodes() == 0:
            return

        print("\nDetecting social communities...")
        try:
            # Undirected for community detection
            undirected_graph = graph.to_undirected()
            communities_list = community.greedy_modularity_communities(undirected_graph)

            # Distinct colors for communities. Yellow is deliberately excluded
            # — it's reserved for topic nodes (see chat_name -> topic node
            # color below), so a community swatch never gets mistaken for one.
            colors = ["#4ECDC4", "#FF6B6B", "#F4A261", "#A58DFF", "#6BCB77", "#4D96FF", "#F47174"]

            # Map back to graph
            for i, comm_nodes in enumerate(communities_list):
                comm_color = colors[i % len(colors)]
                for node in comm_nodes:
                    if self.graph.has_node(node):
                        self.graph.nodes[node]['community'] = i
                        self.graph.nodes[node]['group'] = i
                        # Change color to specify community if it's a person
                        if self.graph.nodes[node].get('type') == 'person':
                             self.graph.nodes[node]['color'] = comm_color

            print(f"   Found {len(communities_list)} communities")

        except Exception as e:
            print(f"   Community detection error: {e}")

    def get_influence_report(self):
        report = []
        for node, data in self.graph.nodes(data=True):
            if data.get('type') == 'person':
                report.append({
                    "name": node,
                    # "name" is the internal graph node id (p_-prefixed);
                    # "label" is the human-readable sender name for callers
                    # that want to match/display a person by their real name.
                    "label": data.get('label', node),
                    "message_count": data.get('message_count', 0),
                    "replies_received": data.get('replies_received', 0),
                    "pagerank": data.get('pagerank', 0),
                    "betweenness": data.get('betweenness', 0),
                    "is_influencer": data.get('is_influencer', False),
                    "is_info_broker": data.get('is_info_broker', False),
                    "community": data.get('community', -1)
                })
        return sorted(report, key=lambda x: x['pagerank'], reverse=True)

    def get_topics(self):
        """Extracted topics with the messages that mention each one."""
        report = []
        for node, data in self.graph.nodes(data=True):
            if data.get('type') != 'topic':
                continue

            related_messages = [
                u for u, v, d in self.graph.in_edges(node, data=True)
                if d.get('relationship') == 'MENTIONS_TOPIC'
            ]
            report.append({
                "topic": node,
                "message_count": len(related_messages),
                "message_ids": related_messages
            })
        return sorted(report, key=lambda x: x['message_count'], reverse=True)

    def visualize(self, output_file: str = "social_network.html"):
        # pyvis's own Network.__init__ declares font_color=False with no type
        # annotation, so Pylance infers a bool param and flags this string —
        # pyvis accepts and uses a color string here fine at runtime.
        net = Network(height="900px", width="100%", bgcolor="#1E1E1E", font_color="#FFFFFF", cdn_resources="remote")  # type: ignore[arg-type]

        # Physics options for good clustering
        net.set_options("""
        {
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -50,
              "centralGravity": 0.01,
              "springLength": 100,
              "springConstant": 0.08
            },
            "maxVelocity": 50,
            "solver": "forceAtlas2Based",
            "timestep": 0.35,
            "stabilization": { "iterations": 150 }
          },
          "interaction": {
             "hover": true,
             "navigationButtons": true
          }
        }
        """)

        # Load From Graph
        net.from_nx(self.graph)

        # Post-process nodes for PyVis specific overrides if needed
        # (Already set attributes in graph construction, so usually fine)

        net.save_graph(output_file)

        # Inject Sidebar (Reusing logic from original builder or creating new)
        self._inject_social_sidebar(output_file)

        return output_file

    def _inject_social_sidebar(self, filepath: str):
        # Improved sidebar with persistent controls and better visibility
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()

        sidebar_content = """
        <style>
            #social-sidebar {
                position: fixed; top: 0; right: -400px; width: 350px; height: 100%;
                background: rgba(30, 30, 30, 0.95); color: #fff; padding: 20px; transition: 0.3s;
                border-left: 2px solid #4ECDC4; z-index: 10000; overflow-y: auto;
                box-shadow: -5px 0 15px rgba(0,0,0,0.5); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            #social-sidebar.open { right: 0; }

            #sidebar-toggle {
                position: fixed; top: 20px; right: 20px; z-index: 9999;
                background: #4ECDC4; color: #1e1e1e; border: none; padding: 10px 20px;
                border-radius: 5px; cursor: pointer; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            }

            .close-btn {
                position: absolute; top: 10px; right: 10px; background: none; border: none;
                color: #ff6b6b; font-size: 24px; cursor: pointer;
            }

            .badge { display: inline-block; padding: 4px 8px; margin: 2px; border-radius: 4px; font-size: 0.8em; font-weight: bold;}
            .badge-influencer { background: #FFD700; color: #000; }
            .badge-broker { background: #00BFFF; color: #000; }

            #legend-box, #filter-box {
                margin-top: 20px; padding: 15px; background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px;
            }

            .legend-item, .filter-item { margin-bottom: 10px; font-size: 0.9em; }
            .legend-icon { display: inline-block; width: 12px; height: 12px; margin-right: 8px; border-radius: 50%; }

            h3 { color: #4ECDC4; border-bottom: 1px solid rgba(78, 205, 196, 0.3); padding-bottom: 5px; margin-top: 0; }
            h4 { color: #ddd; margin: 15px 0 5px; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }

            input[type="checkbox"] { cursor: pointer; margin-right: 8px; }
            label { cursor: pointer; }
            label:hover { color: #4ECDC4; }
        </style>

        <button id="sidebar-toggle" onclick="toggleSidebar()">Open Controls</button>

        <div id="social-sidebar">
            <button class="close-btn" onclick="toggleSidebar()">&times;</button>
            <h2 id="sb-name">Selection Details</h2>
            <div id="sb-badges"></div>
            <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 15px 0;"/>
            <div id="sb-stats">Click a node to see detailed metrics.</div>

            <div id="filter-box">
                <h3>Filters</h3>

                <h4>Communities</h4>
                <div id="community-filters"></div>

                <h4>Edge Types</h4>
                <div id="edge-filters">
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('SENT', this)"> Sent</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('REPLIED_TO', this)"> Replied To</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('MENTIONED', this)"> Mentioned</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('REACTED_TO', this)"> Reacted To</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('DISCUSSED', this)"> Discussed Topic</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('MENTIONS_TOPIC', this)"> Mentions Topic</label></div>
                    <div class="filter-item"><label><input type="checkbox" checked onchange="handleEdgeToggle('PART_OF', this)"> Chat Structure</label></div>
                </div>
            </div>

            <div id="legend-box">
                <h3>Key / Legend</h3>
                <div class="legend-item"><span class="badge badge-influencer">INFLUENCER</span><br><small>High score. Key decision makers.</small></div>
                <div class="legend-item"><span class="badge badge-broker">BROKER</span><br><small>Bridge nodes connecting groups.</small></div>
                <div class="legend-item"><span class="legend-icon" style="background:#4ECDC4"></span> <strong>Person</strong></div>
                <div class="legend-item"><span class="legend-icon" style="background:#FFD93D; transform: rotate(45deg);"></span> <strong>Topic</strong></div>
                <div class="legend-item"><span style="color:#FFD93D">Yellow Arrow</span><small> Reply chain</small></div>
            </div>
        </div>

        <script>
            function toggleSidebar() {
                const sidebar = document.getElementById('social-sidebar');
                const btn = document.getElementById('sidebar-toggle');
                sidebar.classList.toggle('open');
                btn.innerText = sidebar.classList.contains('open') ? 'Close Controls' : 'Open Controls';
            }

            // Ensure network is ready
            function initSocialControls() {
                if (typeof network === 'undefined' || typeof nodes === 'undefined') {
                    console.log("Waiting for network to initialize...");
                    setTimeout(initSocialControls, 100);
                    return;
                }

                network.on("click", function(params) {
                    const sidebar = document.getElementById('social-sidebar');
                    const nameEl = document.getElementById('sb-name');
                    const badgeEl = document.getElementById('sb-badges');
                    const statsEl = document.getElementById('sb-stats');

                    if (params.nodes.length > 0) {
                        const nodeId = params.nodes[0];
                        const node = nodes.get(nodeId);
                        nameEl.innerText = node.label || nodeId;

                        if (node.type === 'person') {
                            let badgesHtml = "";
                            if (node.is_influencer) badgesHtml += '<span class="badge badge-influencer">INFLUENCER</span>';
                            if (node.is_info_broker) badgesHtml += '<span class="badge badge-broker">BROKER</span>';
                            badgeEl.innerHTML = badgesHtml;

                            statsEl.innerHTML = `
                                <p><strong>Messages Sent:</strong> ${node.message_count || 0}</p>
                                <p><strong>Replies Received:</strong> ${node.replies_received || 0}</p>
                                <p><strong>Influence Score:</strong> ${node.pagerank ? node.pagerank.toFixed(3) : 0}</p>
                                <p><strong>Brokerage Score:</strong> ${node.betweenness ? node.betweenness.toFixed(3) : 0}</p>
                                <p><strong>Community:</strong> Group ${node.community !== undefined ? node.community : 'N/A'}</p>
                            `;
                        } else if (node.type === 'message') {
                            badgeEl.innerHTML = '<span class="badge" style="background:#A0D2EB;color:#000">MESSAGE</span>';
                            statsEl.innerHTML = `<p>${node.text || 'Message content not available'}</p><p><small>${node.timestamp || ''}</small></p>`;
                        } else if (node.type === 'topic') {
                            badgeEl.innerHTML = '<span class="badge" style="background:#FFD93D;color:#000">TOPIC</span>';
                            statsEl.innerHTML = `<p>Conversations related to this theme.</p>`;
                        }

                        if (!sidebar.classList.contains('open')) toggleSidebar();
                    }
                });

                // Generate Community Toggles
                const allNodes = nodes.get();
                const communities = [...new Set(allNodes.filter(n => n.community !== undefined).map(n => n.community))].sort((a,b) => a-b);
                const commContainer = document.getElementById('community-filters');

                communities.forEach(c => {
                    const div = document.createElement('div');
                    div.className = 'filter-item';
                    div.innerHTML = `<label><input type="checkbox" checked onchange="handleCommunityToggle(${c}, this)"> Group ${c}</label>`;
                    commContainer.appendChild(div);
                });
            }

            function handleCommunityToggle(commId, checkbox) {
                const isChecked = checkbox.checked;
                const updates = nodes.get().filter(n => n.community === commId).map(n => ({id: n.id, hidden: !isChecked}));
                nodes.update(updates);
            }

            function handleEdgeToggle(type, checkbox) {
                const isChecked = checkbox.checked;
                const updates = edges.get().filter(e => e.relationship === type).map(e => ({id: e.id, hidden: !isChecked}));
                edges.update(updates);
            }

            // Start init
            initSocialControls();
        </script>
        """

        updated_html = html.replace('</body>', sidebar_content + '</body>')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated_html)

    def save_graph(self, filepath: str):
         nx.write_graphml(self.graph, filepath)
