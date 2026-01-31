import networkx as nx
from pyvis.network import Network
from src.social_models import Message
from src.llm_service import LLMService
from typing import List, Dict, Any
import asyncio
from datetime import datetime
import re
from networkx.algorithms import community

class SocialGraphBuilder:
    def __init__(self):
        self.graph = nx.DiGraph() # Directed graph for detailed interactions
        self.llm = LLMService(None)
        
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
        person_to_last_msg = {} # Track last message per person for reply inference
        print("\n👥 Building social network...")
        
        for msg in messages:
            # Person Node
            if msg.sender not in people:
                people.add(msg.sender)
                self.graph.add_node(
                    msg.sender,
                    type="person",
                    label=msg.sender,
                    title=msg.sender, # Initialize title
                    color="#4ECDC4", # Teal
                    size=20, # Will update later based on activity
                    shape="dot"
                )
            
            # Message Node
            msg_label = f"{msg.content[:20]}..."
            self.graph.add_node(
                msg.id,
                type="message",
                label=msg_label,
                title=f"{msg.sender}: {msg.content}\n{msg.timestamp}",
                text=msg.content,
                timestamp=msg.timestamp.isoformat(),
                color="#A0D2EB", # Light Blue
                size=10,
                shape="ellipse"
            )
            
            # EDGE: SENT (Person -> Message)
            self.graph.add_edge(msg.sender, msg.id, relationship="SENT", color="#CCCCCC", width=1)
            
            # EDGE: PART_OF (Message -> Chat)
            self.graph.add_edge(msg.id, chat_name, relationship="PART_OF", color="#EEEEEE", width=0.5)
            
            # OPTIMIZATION: Explicit Mention Parsing using Regex
            mentions = re.findall(r'@(\w+)', msg.content)
            
            # INFERENCE: If message starts with @name and has no reply_to, infer REPLIED_TO
            if not msg.reply_to and msg.content.startswith('@'):
                first_mention_match = re.search(r'^@(\w+)', msg.content)
                if first_mention_match:
                    mentioned_name = first_mention_match.group(1)
                    if mentioned_name in person_to_last_msg:
                        self.graph.add_edge(
                            msg.id, person_to_last_msg[mentioned_name], 
                            relationship="REPLIED_TO", 
                            color="#FFD93D", 
                            width=1.5,
                            title=f"Inferred Reply to {mentioned_name}"
                        )

            # MENTION PARSING
            for mentioned_person in mentions:
                # Add node if not exists (though usually they are senders, sometimes they might not be)
                if mentioned_person not in people:
                    people.add(mentioned_person)
                    self.graph.add_node(
                        mentioned_person, 
                        type="person", 
                        label=mentioned_person, 
                        title=mentioned_person, 
                        color="#4ECDC4", 
                        size=20, 
                        shape="dot"
                    )
                
                # Create explicit MENTIONED edge
                self.graph.add_edge(
                    msg.id, 
                    mentioned_person, 
                    relationship="MENTIONED", 
                    color="#A58DFF", # Purple for mentions
                    width=1.5,
                    dashes=True
                )
                
                # Also infer interaction for metrics (Person -> Person)
                if mentioned_person != msg.sender:
                    if self.graph.has_edge(msg.sender, mentioned_person):
                        self.graph[msg.sender][mentioned_person]['weight'] = self.graph[msg.sender][mentioned_person].get('weight', 0) + 1
                    else:
                        self.graph.add_edge(
                            msg.sender, 
                            mentioned_person, 
                            relationship="INTERACTS_WITH", 
                            weight=1,
                            color="rgba(255, 255, 255, 0.2)",
                            hidden=True 
                        )

            # EDGE: REPLIED_TO (Message -> Message)
            if msg.reply_to and self.graph.has_node(msg.reply_to):
                self.graph.add_edge(
                    msg.id, 
                    msg.reply_to, 
                    relationship="REPLIED_TO", 
                    color="#FFD93D", # Yellow arrows for flow
                    width=2,
                    title="Replying to"
                )
                
                # EDGE: INTERACTS_WITH (Person -> Person inferred from reply)
                # Find original sender
                try: 
                    original_sender = next(u for u, v, d in self.graph.in_edges(msg.reply_to, data=True) if d['relationship'] == 'SENT')
                    if original_sender != msg.sender:
                        if self.graph.has_edge(msg.sender, original_sender):
                            self.graph[msg.sender][original_sender]['weight'] += 1
                        else:
                            self.graph.add_edge(
                                msg.sender, 
                                original_sender, 
                                relationship="INTERACTS_WITH", 
                                weight=1,
                                color="rgba(255, 255, 255, 0.2)",
                                hidden=True # Hidden in visual, used for calculation
                            )
                except StopIteration:
                    pass
            
            # Handle Reactions (Person -> Message)
            for reactor in msg.reactions:
                if reactor not in people:
                    people.add(reactor)
                    self.graph.add_node(reactor, type="person", label=reactor, title=reactor, color="#4ECDC4", shape="dot")
                
                self.graph.add_edge(
                    reactor, 
                    msg.id, 
                    relationship="REACTED_TO",
                    color="#FF8E00", # Orange
                    width=1,
                    dashes=True
                )
            
            # Update last message for this person
            person_to_last_msg[msg.sender] = msg.id

        print(f"   Added {len(people)} participants and {len(messages)} messages")

        # 3. Topic Extraction (Async)
        print("\n🧠 Extracting topics...")
        msg_texts = [f"{m.sender}: {m.content}" for m in messages]
        topics = await self.llm.extract_topics(msg_texts)
        
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
            
            # Connect relevant messages to topic (Robust Regex Match)
            # Use word boundaries \b to avoid partial matches
            for msg in messages:
                if re.search(r'\b' + re.escape(topic) + r'\b', msg.content, re.IGNORECASE):
                     self.graph.add_edge(msg.id, topic, relationship="MENTIONS_TOPIC", color="rgba(255, 217, 61, 0.3)", dashes=True)

        print(f"   Identified topics: {topics}")

        # 4. Calculate Social Stats & Communities
        return self._calculate_stats()
    
    def _calculate_stats(self):
        print("\n📊 Calculating social metrics...")
        
        # Create a simplified person-to-person interaction graph for metrics
        interaction_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            if data.get('relationship') == 'INTERACTS_WITH':
                if interaction_graph.has_edge(u, v):
                    interaction_graph[u][v]['weight'] += data['weight']
                else:
                    interaction_graph.add_edge(u, v, weight=data['weight'])
            
        people_nodes = [n for n, d in self.graph.nodes(data=True) if d.get('type') == 'person']
        
        # 1. PageRank (Influence)
        try:
            pagerank = nx.pagerank(interaction_graph, weight='weight')
        except:
            pagerank = {p: 0 for p in people_nodes} # Fallback if empty
            
        # 2. Betweenness Centrality (Info Brokers)
        try:
            betweenness = nx.betweenness_centrality(interaction_graph, weight='weight')
        except:
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

        # Count replies received
        for u, v, d in self.graph.edges(data=True):
            if d.get('relationship') == 'REPLIED_TO':
                # u is the reply message, v is the original message
                original_msg = v
                recipient = msg_to_sender.get(original_msg)
                if recipient:
                    replies_received[recipient] += 1
            
        # Update Graph Node Attributes
        for person in people_nodes:
            pr_score = pagerank.get(person, 0)
            bc_score = betweenness.get(person, 0)
            msg_count = activity.get(person, 0)
            recv_count = replies_received.get(person, 0)
            
            self.graph.nodes[person]['pagerank'] = pr_score
            self.graph.nodes[person]['betweenness'] = bc_score
            self.graph.nodes[person]['message_count'] = msg_count
            self.graph.nodes[person]['replies_received'] = recv_count
            
            # Badges (Refined thresholds or dynamic)
            badges = []
            # Use top scores for more selective badges in large networks
            if pr_score > 0.12: 
                badges.append("INFLUENCER")
                self.graph.nodes[person]['is_influencer'] = True
                self.graph.nodes[person]['size'] = 35 + (msg_count * 0.5)
                self.graph.nodes[person]['borderWidth'] = 3 
            else:
                 self.graph.nodes[person]['is_influencer'] = False
                 self.graph.nodes[person]['size'] = 20 + (msg_count * 0.5)

            if bc_score > 0.15: # Increased threshold
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

        print("\n🏘️ Detecting social communities...")
        try:
            # Undirected for community detection
            undirected_graph = graph.to_undirected()
            communities_list = community.greedy_modularity_communities(undirected_graph)
            
            # Distinct colors for communities
            colors = ["#4ECDC4", "#FF6B6B", "#FFD93D", "#A58DFF", "#6BCB77", "#4D96FF", "#F47174"]
            
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
                    "message_count": data.get('message_count', 0),
                    "replies_received": data.get('replies_received', 0),
                    "pagerank": data.get('pagerank', 0),
                    "betweenness": data.get('betweenness', 0),
                    "is_influencer": data.get('is_influencer', False),
                    "is_info_broker": data.get('is_info_broker', False),
                    "community": data.get('community', -1)
                })
        return sorted(report, key=lambda x: x['pagerank'], reverse=True)

    def visualize(self, output_file: str = "social_network.html"):
        net = Network(height="900px", width="100%", bgcolor="#1E1E1E", font_color="#FFFFFF", cdn_resources="remote")
        
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

        <button id="sidebar-toggle" onclick="toggleSidebar()">📊 Open Controls</button>

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
                <div class="legend-item"><span class="badge badge-influencer">🌟 INFLUENCER</span><br><small>High score. Key decision makers.</small></div>
                <div class="legend-item"><span class="badge badge-broker">🔗 BROKER</span><br><small>Bridge nodes connecting groups.</small></div>
                <div class="legend-item"><span class="legend-icon" style="background:#4ECDC4"></span> <strong>Person</strong></div>
                <div class="legend-item"><span class="legend-icon" style="background:#FFD93D; transform: rotate(45deg);"></span> <strong>Topic</strong></div>
                <div class="legend-item"><span style="color:#FFD93D">➡ Yellow Arrow</span><small> Reply chain</small></div>
            </div>
        </div>

        <script>
            function toggleSidebar() {
                const sidebar = document.getElementById('social-sidebar');
                const btn = document.getElementById('sidebar-toggle');
                sidebar.classList.toggle('open');
                btn.innerText = sidebar.classList.contains('open') ? '❌ Close Controls' : '📊 Open Controls';
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
                            if (node.is_influencer) badgesHtml += '<span class="badge badge-influencer">🌟 INFLUENCER</span>';
                            if (node.is_info_broker) badgesHtml += '<span class="badge badge-broker">🔗 BROKER</span>';
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
