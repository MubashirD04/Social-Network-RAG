import networkx as nx
from pyvis.network import Network
from typing import List, Dict, Tuple
from pathlib import Path
from llm_service import LLMService, Entity, Relationship
import numpy as np
import json
from networkx.algorithms import community
import asyncio

class KnowledgeGraphBuilder:
    # Build and visualize knowledge graphs from text
    
    def __init__(self):
        # Initialise graph builder
        
        self.llm = LLMService(None)
        self.graph = nx.Graph()
        
    async def process_text(self, text:str, source_name: str = "document"):
        # Process text and build graph
        
        print(f"\n{'='*80}")
        print(f"Processing: {source_name}")
        print(f"{'='*80}")
        
        # Chunk Text
        print("\n📄 Chunking Text...")
        chunks = self.llm.chunk_text(text)
        print(f"   Created {len(chunks)} chunks")
        
        # Generate summary
        print("\n📝 Generating document summary...")
        summary = await self.llm.summarise_document(text)
        print(f"    Summary: {summary.summary}")
        
        # Add document node
        doc_node_id = f"doc_{source_name}"
        self.graph.add_node(
            doc_node_id,
            type="document",
            label=source_name,
            title=f"Document: {source_name}",
            summary=summary.summary,
            main_topics=summary.main_topics,
            color="#FF6B6B", # Red
            size=30,
            shape="box"
        )
        
        # Process each chunk and collect all entities first
        all_entities = []
        all_relationships = []
        chunk_nodes = []
        chunk_entity_mentions = []  # Track which entities are in which chunks
        
        # --- PARALLEL PROCESSING ---
        async def process_single_chunk(i, chunk):
            # Extract entities
            entities = await self.llm.extract_entities(chunk)
            
            # Extract relationships (only if we have enough entities)
            relationships = []
            if len(entities) >= 2:
                relationships = await self.llm.extract_relationships(entities, chunk)
                
            # Embeddings (Sync for now)
            embedding = self.llm.generate_embeddings([chunk])[0]
            
            return i, chunk, entities, relationships, embedding

        print(f"\n🚀 Processing {len(chunks)} chunks in parallel...")
        tasks = [process_single_chunk(i, chunk) for i, chunk in enumerate(chunks)]
        chunk_results = await asyncio.gather(*tasks)
        print(f"   Processed {len(chunk_results)} chunks")
        
        # Reconstruct results
        for i, chunk, entities, relationships, embedding in chunk_results:
            print(f"   Chunk {i+1}: Found {len(entities)} entities, {len(relationships)} relationships")
            all_entities.extend(entities)
            all_relationships.extend(relationships)
            
            # Add chunk node
            chunk_node_id = f"chunk_{source_name}_{i}" 
            chunk_nodes.append(chunk_node_id)
            chunk_entity_mentions.append((chunk_node_id, [e.name for e in entities]))
            
            display_text = chunk[:200] + "..." if len(chunk) > 200 else chunk
            
            self.graph.add_node(
                chunk_node_id,
                type="chunk",
                label=f"Chunk {i+1}",
                title=f"Chunk {i+1}: {display_text}",
                text=chunk,
                embedding=embedding,
                position=i,
                color="#4ECDC4", 
                size=15,
                shape="ellipse"
            )
            
            # Connect chunk to document
            self.graph.add_edge(
                doc_node_id,
                chunk_node_id,
                relationship="CONTAINS",
                weight=1.5,
                color="rgba(100, 100, 100, 0.3)",
                width=1,
                show_label=False
            )
                    
        # Add unique entities to graph FIRST (Optimized)
        print(f"\n👥 Adding entities to graph...")
        unique_entities = {}
        entity_name_mapping = {}  # Map variations to canonical names
        
        for entity in all_entities:
            canonical_name = entity.name.strip()
            match_key = canonical_name.lower()
            
            if match_key not in unique_entities:
                unique_entities[match_key] = entity
                entity_name_mapping[match_key] = canonical_name
            else:
                existing = unique_entities[match_key]
                importance_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                if importance_order.get(entity.importance, 0) > importance_order.get(existing.importance, 0):
                    unique_entities[match_key] = entity
                    entity_name_mapping[match_key] = canonical_name
                    
        # Entity colours by type (Dark Theme Optimized)
        entity_colors = {
            "PERSON": "#00E0B8",       # Bright Teal
            "ORGANIZATION": "#FF6B6B", # Coral Red
            "LOCATION": "#A58DFF",     # Soft Purple
            "CONCEPT": "#FFD93D",      # Vivid Yellow
            "EVENT": "#4D96FF",        # Sky Blue
            "PRODUCT": "#FF8E00",      # Orange
            "TECHNOLOGY": "#00FFC6",   # Bright Mint
            "SERVICE": "#008CFF",      # Azure Blue
            "PLATFORM": "#FF00FF",     # Magenta
            "OTHER": "#B2C8DF"         # Silver Blue
        }
        
        for match_key, entity in unique_entities.items():
            display_name = entity_name_mapping[match_key]
            size_map = {"HIGH": 25, "MEDIUM": 20, "LOW": 15}
            
            self.graph.add_node(
                display_name,
                type="entity", entity_type=entity.type, label=display_name,
                title=f"{display_name} ({entity.type})\n{entity.description}",
                description=entity.description, importance=entity.importance,
                color=entity_colors.get(entity.type.upper(), entity_colors["OTHER"]),
                size=size_map.get(entity.importance, 20), shape="dot"
            )
        
        print(f"   Added {len(unique_entities)} unique entities")
        
        # NOW connect chunks to entities
        print(f"\n🔗 Connecting chunks to entities...")
        chunk_entity_connections = 0
        for chunk_node_id, entity_names in chunk_entity_mentions:
            for entity_name in entity_names:
                match_key = entity_name.strip().lower()
                if match_key in entity_name_mapping:
                    canonical_name = entity_name_mapping[match_key]
                    if self.graph.has_node(canonical_name):
                        self.graph.add_edge(
                            chunk_node_id, canonical_name, relationship="MENTIONS",
                            weight=0.4, color="rgba(150, 150, 150, 0.25)", width=0.5, show_label=False
                        )
                        chunk_entity_connections += 1
        
        print(f"   Added {chunk_entity_connections} chunk-entity connections")
        
        # Connect document to key entities from summary
        print(f"\n🌟 Connecting document to key entities...")
        doc_entity_connections = 0
        for key_entity in summary.key_entities:
            key_entity_lower = key_entity.lower().strip()
            target_node = None
            
            if key_entity_lower in entity_name_mapping:
                target_node = entity_name_mapping[key_entity_lower]
            else:
                for match_key in entity_name_mapping.keys():
                    if key_entity_lower in match_key or match_key in key_entity_lower:
                        target_node = entity_name_mapping[match_key]
                        break
            
            if target_node and self.graph.has_node(target_node):
                if self.graph.degree(target_node) == 0:
                    self.graph.add_edge(
                        doc_node_id, target_node, relationship="MENTIONED_IN",
                        weight=0.8, color="rgba(200, 200, 200, 0.3)", width=1, show_label=False
                    )
                    doc_entity_connections += 1
        
        print(f"   Added {doc_entity_connections} document-entity fallback connections")
        
        # Add relationships with fuzzy matching
        print(f"\n🔗 Adding relationships...")
        added_relationships = 0
        
        def find_entity_match(name: str):
            name_lower = name.lower().strip()
            if name_lower in entity_name_mapping:
                return entity_name_mapping[name_lower]
            for match_key, canonical in entity_name_mapping.items():
                if name_lower in match_key or match_key in name_lower:
                    return canonical
            return None
        
        for rel in all_relationships:
            source_match = find_entity_match(rel.source)
            target_match = find_entity_match(rel.target)
            
            if source_match and target_match and self.graph.has_node(source_match) and self.graph.has_node(target_match):
                weight_map = {"HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.2}
                color_map = {
                    "HIGH": "rgba(78, 205, 196, 1.0)", "MEDIUM": "rgba(78, 205, 196, 0.8)",
                    "LOW": "rgba(78, 205, 196, 0.5)"
                }
                width_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1.5}
                
                self.graph.add_edge(
                    source_match, target_match, relationship=rel.relationship_type,
                    description=rel.description, confidence=rel.confidence,
                    weight=weight_map.get(rel.confidence, 1.5),
                    title=f"{rel.relationship_type}: {rel.description}",
                    color=color_map.get(rel.confidence, "rgba(78, 205, 196, 0.7)"),
                    width=width_map.get(rel.confidence, 2), show_label=True
                )
                added_relationships += 1
        
        print(f"   Added {added_relationships} entity relationships")
        
        # Connect entities that appear in the same chunks (co-occurrence)
        print(f"\n🤝 Adding co-occurrence edges...")
        cooccurrence_edges = 0
        for chunk_node_id, entity_names in chunk_entity_mentions:
            unique_chunk_entities = set()
            for e in entity_names:
                match_key = e.strip().lower()
                if match_key in entity_name_mapping:
                    unique_chunk_entities.add(entity_name_mapping[match_key])
            
            chunk_entities_list = list(unique_chunk_entities)
            for i, entity1 in enumerate(chunk_entities_list):
                for entity2 in chunk_entities_list[i+1:]:
                    if not self.graph.has_edge(entity1, entity2):
                        self.graph.add_edge(
                            entity1, entity2, relationship="CO_OCCURS", weight=0.2,
                            title="Mentioned together", color="rgba(200, 200, 200, 0.2)",
                            width=0.5, show_label=False
                        )
                        cooccurrence_edges += 1
        
        print(f"   Added {cooccurrence_edges} co-occurrence edges")
        
        # Calculate stats
        stats = {
            "source": source_name,
            "chunks": len(chunks),
            "entities": len(unique_entities),
            "relationships": added_relationships,
            "chunk_entity_connections": chunk_entity_connections,
            "doc_entity_connections": doc_entity_connections,
            "cooccurrence_edges": cooccurrence_edges,
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "summary": summary.summary
        }
        
        print(f"\n✅ Processing complete!")
        print(f"   Total nodes: {stats['total_nodes']}")
        print(f"   Total edges: {stats['total_edges']}")
        print(f"   Isolated nodes: {len(list(nx.isolates(self.graph)))}")
        
        return stats
    
    def add_similarity_edges(self, similarity_threshold: float=0.7):
        # Add edges between similar chunks based on embedding similarity (Optimized)
        print(f"\n🔍 Computing chunk similarities...")
        
        chunk_nodes = [
            (node, data)
            for node, data in self.graph.nodes(data=True)
            if data.get('type') == 'chunk' and 'embedding' in data
        ]
        
        if not chunk_nodes:
            print("   No chunks to compare")
            return

        # Vectorized implementation
        node_ids = [n for n, d in chunk_nodes]
        embeddings = np.array([d['embedding'] for n, d in chunk_nodes])
        
        # Normalize embeddings (if not already)
        norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / (norm + 1e-10) # Avoid div by zero
        
        # Matrix multiplication for cosine similarity (N x N)
        similarity_matrix = np.dot(embeddings, embeddings.T)
        
        # Find pairs greater than threshold
        # We only care about upper triangle (exclusive of diagonal)
        rows, cols = np.where(np.triu(similarity_matrix, k=1) >= similarity_threshold)
        
        similarities_added = 0
        for r, c in zip(rows, cols):
            node1 = node_ids[r]
            node2 = node_ids[c]
            similarity = float(similarity_matrix[r, c])
            
            self.graph.add_edge(
                node1,
                node2,
                relationship="SIMILAR_TO",
                similarity=similarity,
                weight=similarity * 0.5,  # Lower weight
                title=f"Similarity: {similarity:.2f}",
                color="rgba(220, 220, 220, 0.3)",  # Very transparent gray
                dashes=True,
                width=1,
                show_label=False  # Don't show label
            )
            similarities_added += 1
            
        print(f"    Added {similarities_added} similarity edges")
    
    def detect_communities(self, algorithm: str = "louvain", resolution: float = 1.0):
        """
        Detect communities in the graph using various algorithms
        
        Args:
            algorithm: Algorithm to use - 'louvain', 'greedy_modularity', 'label_propagation', or 'girvan_newman'
            resolution: Resolution parameter for Louvain (higher = more communities)
        
        Returns:
            Dictionary mapping node to community ID
        """
        print(f"\n🏘️ Detecting communities using {algorithm}...")
        
        if self.graph.number_of_nodes() == 0:
            print("   Warning: Graph is empty, no communities to detect")
            return {}
        
        # Need to work with the largest connected component for some algorithms
        if not nx.is_connected(self.graph):
            print(f"   Graph has {nx.number_connected_components(self.graph)} connected components")
            largest_cc = max(nx.connected_components(self.graph), key=len)
            working_graph = self.graph.subgraph(largest_cc).copy()
        else:
            working_graph = self.graph
        
        community_mapping = {}
        
        try:
            if algorithm == "louvain":
                # Louvain method - fast and commonly used
                communities_dict = community.louvain_communities(
                    working_graph, 
                    weight='weight',
                    resolution=resolution,
                    seed=42
                )
                # Convert from list of sets to dict mapping
                for comm_id, nodes in enumerate(communities_dict):
                    for node in nodes:
                        community_mapping[node] = comm_id
                        
            elif algorithm == "greedy_modularity":
                # Greedy modularity optimization
                communities_generator = community.greedy_modularity_communities(
                    working_graph,
                    weight='weight'
                )
                for comm_id, nodes in enumerate(communities_generator):
                    for node in nodes:
                        community_mapping[node] = comm_id
                        
            elif algorithm == "label_propagation":
                # Label propagation - fast, semi-random
                communities_generator = community.label_propagation_communities(working_graph)
                for comm_id, nodes in enumerate(communities_generator):
                    for node in nodes:
                        community_mapping[node] = comm_id
                        
            elif algorithm == "girvan_newman":
                # Girvan-Newman - hierarchical, slow but good quality
                # Get first level of communities (most broad)
                communities_generator = community.girvan_newman(working_graph)
                first_level = next(communities_generator)
                for comm_id, nodes in enumerate(first_level):
                    for node in nodes:
                        community_mapping[node] = comm_id
            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")
            
            # Assign community -1 to nodes not in largest component
            for node in self.graph.nodes():
                if node not in community_mapping:
                    community_mapping[node] = -1
            
            # Add community info to graph nodes
            for node, comm_id in community_mapping.items():
                if self.graph.has_node(node):
                    self.graph.nodes[node]['community'] = comm_id
            
            num_communities = len(set(community_mapping.values()))
            print(f"   Found {num_communities} communities")
            
            # Print community statistics
            community_sizes = {}
            for node, comm_id in community_mapping.items():
                community_sizes[comm_id] = community_sizes.get(comm_id, 0) + 1
            
            print(f"   Community sizes: {dict(sorted(community_sizes.items()))}")
            
            # Calculate modularity
            if len(community_mapping) > 0:
                communities_list = {}
                for node, comm_id in community_mapping.items():
                    if comm_id not in communities_list:
                        communities_list[comm_id] = set()
                    communities_list[comm_id].add(node)
                
                mod = community.modularity(working_graph, communities_list.values(), weight='weight')
                print(f"   Modularity: {mod:.4f} (higher is better, max ~0.3-0.7)")
            
            return community_mapping
            
        except Exception as e:
            print(f"   Error detecting communities: {e}")
            return {}
    
    def assign_community_colors(self):
        """
        Assign distinct colors to each community for visualization
        """
        # Get all unique communities
        communities = set()
        for node, data in self.graph.nodes(data=True):
            if 'community' in data:
                communities.add(data['community'])
        
        if not communities:
            print("   No communities found to color")
            return
        
        # Generate distinct colors for each community (Dark Theme Optimized)
        # Using a bright color palette that pops on dark gray
        color_palette = [
            "#FF3B3B", "#00FFC6", "#008CFF", "#FFEE00", "#FF00FF",
            "#FF8800", "#B200FF", "#00FF00", "#FF0077", "#00E5FF",
            "#F06292", "#AED581", "#FFD54F", "#4DB6AC", "#FF8A65",
            "#9575CD", "#4FC3F7", "#81C784", "#FFB74D", "#E57373",
        ]
        
        # Map community IDs to colors
        community_list = sorted(list(communities))
        community_colors = {}
        
        for i, comm_id in enumerate(community_list):
            if comm_id == -1:  # Disconnected nodes
                community_colors[comm_id] = "#CCCCCC"  # Gray
            else:
                community_colors[comm_id] = color_palette[i % len(color_palette)]
        
        # Assign colors to nodes (but preserve document/chunk/entity type colors for size/shape)
        nodes_colored = 0
        for node, data in self.graph.nodes(data=True):
            # Only apply community colors to entities
            # Keep documents and chunks as their original structural colors
            if data.get('type') == 'entity' and 'community' in data:
                comm_id = data['community']
                # Store original color
                if 'original_color' not in data:
                    data['original_color'] = data.get('color', '#97C2FC')
                # Apply community color
                data['color'] = community_colors.get(comm_id, '#97C2FC')
                nodes_colored += 1
        
        print(f"   Assigned colors to {nodes_colored} nodes across {len(community_list)} communities")
        
    def get_community_summary(self, community_id: int, max_nodes: int = 10):
        """
        Get a summary of what's in a specific community
        
        Args:
            community_id: The community ID to summarize
            max_nodes: Maximum number of nodes to include in summary
        
        Returns:
            Dictionary with community statistics and key members
        """
        # Get all nodes in this community
        community_nodes = [
            (node, data) 
            for node, data in self.graph.nodes(data=True)
            if data.get('community') == community_id
        ]
        
        if not community_nodes:
            return {"error": f"No nodes found in community {community_id}"}
        
        # Categorize nodes
        summary = {
            "community_id": community_id,
            "total_nodes": len(community_nodes),
            "node_types": {},
            "entity_types": {},
            "key_nodes": [],
            "internal_edges": 0,
            "external_edges": 0,
        }
        
        community_node_set = {node for node, _ in community_nodes}
        
        for node, data in community_nodes:
            node_type = data.get('type', 'unknown')
            summary["node_types"][node_type] = summary["node_types"].get(node_type, 0) + 1
            
            if node_type == "entity":
                entity_type = data.get('entity_type', 'unknown')
                summary["entity_types"][entity_type] = summary["entity_types"].get(entity_type, 0) + 1
        
        # Count internal vs external edges
        for node in community_node_set:
            for neighbor in self.graph.neighbors(node):
                if neighbor in community_node_set:
                    summary["internal_edges"] += 1
                else:
                    summary["external_edges"] += 1
        
        summary["internal_edges"] //= 2  # Each edge counted twice
        
        # Get most important/central nodes
        subgraph = self.graph.subgraph(community_node_set)
        if len(subgraph.nodes()) > 0:
            # Use degree centrality to find key nodes
            centrality = nx.degree_centrality(subgraph)
            top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:max_nodes]
            
            for node, centrality_score in top_nodes:
                data = self.graph.nodes[node]
                summary["key_nodes"].append({
                    "name": node,
                    "label": data.get('label', node),
                    "type": data.get('type', 'unknown'),
                    "centrality": round(centrality_score, 3)
                })
        
        return summary
        
    def get_graph_stats(self):
        """Get comprehensive graph statistics"""
        stats = {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": {},
            "entity_types": {},
            "relationship_types": {},
            "density": nx.density(self.graph),
            "is_connected": nx.is_connected(self.graph),
            "isolated_nodes": len(list(nx.isolates(self.graph))),
            "communities": {},
        }
        
        # Count node types
        for node, data in self.graph.nodes(data=True):
            node_type = data.get('type', 'unknown')
            stats["node_types"][node_type] = stats["node_types"].get(node_type, 0) + 1
            
            # Count entity types
            if node_type == "entity":
                entity_type = data.get('entity_type', 'unknown')
                stats["entity_types"][entity_type] = stats["entity_types"].get(entity_type, 0) + 1
        
        # Count relationship types
        for u, v, data in self.graph.edges(data=True):
            rel_type = data.get('relationship', 'unknown')
            stats["relationship_types"][rel_type] = stats["relationship_types"].get(rel_type, 0) + 1
        
        # Calculate connected components
        if not nx.is_connected(self.graph):
            stats["connected_components"] = nx.number_connected_components(self.graph)
        
        # Community statistics
        community_counts = {}
        for node, data in self.graph.nodes(data=True):
            if 'community' in data:
                comm_id = data['community']
                community_counts[comm_id] = community_counts.get(comm_id, 0) + 1
        
        if community_counts:
            stats["communities"] = {
                "num_communities": len(community_counts),
                "sizes": community_counts
            }
        
        return stats    
        
    def visualise(self, output_file: str="knowledge_graph.html", height: str="900px", width: str="100%", notebook: bool=False):
        # Create pyvis visuals (Dark Theme & Interactive Sidebar)
        print(f"\n🎨 Creating visualisation...")
        
        # Dark Grey Background
        net = Network(
            height=height,
            width=width,
            bgcolor="#1E1E1E", # Dark Grey
            font_color="#FFFFFF",
            notebook=notebook,
            select_menu=True,
            filter_menu=True,
            cdn_resources="remote"
        )
        
        # Pre-calculate layout positions for a static, non-moving graph
        print(f"   Calculating static layout...")
        k_val = 1.5 / np.sqrt(len(self.graph.nodes()) or 1)
        pos = nx.spring_layout(self.graph, k=k_val, iterations=100, seed=42)
        
        # Configure options for a STILL graph (physics disabled)
        net.set_options("""
        {
          "physics": {
            "enabled": false
          },
          "nodes": {
            "font": {
              "size": 18,
              "face": "Bahnschrift, Arial",
              "strokeWidth": 0,
              "color": "#FFFFFF"
            },
            "borderWidth": 1.5,
            "shadow": {
              "enabled": true,
              "color": "rgba(0,0,0,0.4)",
              "size": 6,
              "x": 2,
              "y": 2
            },
            "color": {
                "highlight": {
                    "border": "#2B7CE9",
                    "background": "#333333"
                }
            }
          },
          "edges": {
            "color": {
              "inherit": false,
              "highlight": "#00FFC6",
              "opacity": 0.4
            },
            "font": {
              "size": 9,
              "face": "Bahnschrift, Arial",
              "align": "middle",
              "strokeWidth": 0,
              "color": "#DDDDDD",
              "background": "rgba(30, 30, 30, 0.7)"
            },
            "smooth": {
              "enabled": true,
              "type": "continuous",
              "roundness": 0.3
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.4
                }
            }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 200,
            "navigationButtons": true,
            "keyboard": true,
            "zoomView": true,
            "selectConnectedEdges": true,
            "dragNodes": true,
            "dragView": true
          }
        }
        """)
        
        # Add nodes with pre-calculated positions and extra data for sidebar
        for node, data in self.graph.nodes(data=True):
            border_color = "#666666" 
            if data.get('importance') == 'HIGH' or data.get('type') == 'document':
                 border_color = "#FFFFFF"
            
            x, y = pos[node] * 1200
            
            # Additional metadata for JS listener
            node_props = {
                "n_id": node,
                "x": x, "y": y,
                "label": data.get('label', node),
                "title": data.get('title', node),
                "color": {
                    "background": data.get('color', '#97C2FC'), 
                    "border": border_color,
                    "highlight": {"background": "#444444", "border": "#00FFC6"}
                },
                "size": data.get('size', 20),
                "shape": data.get('shape', 'dot'),
                "borderWidth": 2 if data.get('importance') == 'HIGH' else 1
            }
            
            # Inject all original attributes so JS can see them
            node_props.update({k: v for k, v in data.items() if k not in ["embedding"]})
            
            net.add_node(**node_props)
        
        # Add edges
        for u, v, data in self.graph.edges(data=True):
            relationship_type = data.get('relationship', '')
            
            edge_config = {
                'title': f"{relationship_type}: {data.get('description', '')}" if data.get('description') else relationship_type,
                'value': data.get('weight', 1.0),
                'color': {
                    'color': data.get('color', '#555555'),
                    'highlight': '#00FFC6',
                    'opacity': 0.6
                }
            }
            
            if relationship_type in ["CONTAINS", "MENTIONS", "SIMILAR_TO", "CO_OCCURS", "MENTIONED_IN"]:
                edge_config['dashes'] = True
                edge_config['width'] = 0.3
                edge_config['color']['color'] = "rgba(100, 100, 100, 0.4)" 
                edge_config['arrows'] = {'to': {'enabled': False}}
            else:
                edge_config['width'] = data.get('width', 1.2)
                edge_config['label'] = relationship_type 
                edge_config['font'] = {'size': 8, 'color': '#FFFFFF'}
                edge_config['arrows'] = {'to': {'enabled': True, 'scaleFactor': 0.6}}
            
            net.add_edge(u, v, **edge_config)
            
        # Write to file
        net.save_graph(output_file)
        
        # Post-Process HTML to inject SideBar and Custom JS
        self._inject_sidebar(output_file)
        
        print(f"   Visualization saved to: {output_file}")
        return output_file

    def _inject_sidebar(self, filepath: str):
        # Inject sidebar HTML and JS into the generated PyVis file
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                html = f.read()

            sidebar_html = """
<style>
    #side-bar {
        position: fixed;
        right: -450px;
        top: 0;
        width: 400px;
        height: 100%;
        background: #252525;
        color: #e0e0e0;
        padding: 25px;
        transition: 0.3s ease-in-out;
        z-index: 9999;
        box-shadow: -10px 0 30px rgba(0,0,0,0.7);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        overflow-y: auto;
        border-left: 2px solid #333;
    }
    #side-bar.open { right: 0; }
    .sb-close {
        position: absolute; top: 20px; right: 20px;
        background: none; border: none; color: #888;
        cursor: pointer; font-size: 24px;
    }
    .sb-close:hover { color: #fff; }
    .sb-type-tag {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 4px;
        background: #444;
        font-size: 0.8em;
        margin-bottom: 15px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .sb-content-box {
        background: #1a1a1a;
        padding: 15px;
        border-radius: 8px;
        line-height: 1.6;
        white-space: pre-wrap;
    }
    h2 { color: #00FFC6; margin-top: 0; }
</style>

<div id="side-bar">
    <button class="sb-close" onclick="document.getElementById('side-bar').classList.remove('open')">×</button>
    <div id="sb-type-tag" class="sb-type-tag">Node</div>
    <h2 id="sb-title">Node Details</h2>
    <div id="sb-content">Click a node to see details</div>
</div>

<script>
    function setupSidebar() {
        if (typeof network === 'undefined') {
            setTimeout(setupSidebar, 100);
            return;
        }

        network.on("click", function(params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                const nodeData = nodes.get(nodeId);
                
                const sb = document.getElementById('side-bar');
                const title = document.getElementById('sb-title');
                const content = document.getElementById('sb-content');
                const tag = document.getElementById('sb-type-tag');
                
                tag.innerText = nodeData.type || "node";
                title.innerText = nodeData.label || nodeId;
                
                let html = "";
                if (nodeData.type === 'chunk') {
                    html = `<div class="sb-content-box">${nodeData.text || "No text available"}</div>`;
                    tag.style.background = "#4ECDC4";
                    tag.style.color = "#000";
                } else if (nodeData.type === 'entity') {
                    html = `
                        <p><strong>Type:</strong> ${nodeData.entity_type || "N/A"}</p>
                        <p><strong>Importance:</strong> ${nodeData.importance || "N/A"}</p>
                        <hr style="border-color:#333; margin:15px 0;">
                        <p>${nodeData.description || "No description available"}</p>
                    `;
                    tag.style.background = typeof nodeData.color === 'object' ? nodeData.color.background : nodeData.color;
                    tag.style.color = "#000";
                } else if (nodeData.type === 'document') {
                    html = `<p><strong>Summary:</strong></p><div class="sb-content-box">${nodeData.summary || "N/A"}</div>`;
                    tag.style.background = "#FF6B6B";
                }
                
                content.innerHTML = html;
                sb.classList.add('open');
            }
        });
        
        // Close on background click
        network.on("click", function(params) {
            if (params.nodes.length === 0) {
                document.getElementById('side-bar').classList.remove('open');
            }
        });
    }
    
    window.addEventListener('load', setupSidebar);
</script>
"""
            updated_html = html.replace('</body>', sidebar_html + '</body>')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(updated_html)
        except Exception as e:
            print(f"Error injecting sidebar: {e}")

    
    def save_graph(self, filepath: str):
        # Save graph to file
        graph_copy = self.graph.copy()
        for node, data in graph_copy.nodes(data=True):
            if 'embedding' in data:
                data['embedding'] = json.dumps(data['embedding'])
            
            for key, value in data.items():
                if isinstance(value, list):
                    data[key] = json.dumps(value)
        
        nx.write_graphml(graph_copy, filepath)
        print(f"Graph saved to: {filepath}")
        
    def load_graph(self, filepath: str):
        self.graph = nx.read_graphml(filepath)
        
        # Load graph from file
        for node, data in self.graph.nodes(data=True):
            if 'embedding' in data:
                data['embedding'] = json.loads(data['embedding'])
                
            for key, value in data.items():
                if isinstance(value, str) and value.startswith('['):
                    try:
                        data[key] = json.loads(value)
                    except:
                        pass
        
        print(f"Graph loaded from: {filepath}")
        
    async def query_graph(self, query: str, top_k: int = 3):
        # Query the knowledge graph using RAG (Async)

        print(f"\n❓ Query: {query}")
        
        # Understand the query
        intent = await self.llm.understand_query(query)
        print(f"   Intent: {intent.intent}")
        print(f"   Looking for: {intent.key_entities}")
        
        # Generate query embedding
        query_embedding = self.llm.generate_embeddings([query])[0]
        
        # Find similar chunks
        chunk_nodes = [
            (node, data) 
            for node, data in self.graph.nodes(data=True) 
            if data.get('type') == 'chunk' and 'embedding' in data
        ]
        
        if not chunk_nodes:
            return {
                "answer": "No content available in the knowledge graph.",
                "confidence": "LOW",
                "sources": []
            }
        
        # Vectorized similarity search
        texts = [data['text'] for _, data in chunk_nodes]
        node_ids = [node for node, _ in chunk_nodes]
        embeddings = np.array([data['embedding'] for _, data in chunk_nodes])
        
        query_emb = np.array(query_embedding)
        norm_query = np.linalg.norm(query_emb)
        norm_embeddings = np.linalg.norm(embeddings, axis=1)
        
        # Initial cosine similarity
        similarities = np.dot(embeddings, query_emb) / (norm_embeddings * norm_query + 1e-10)
        
        # Sort indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        top_chunks = []
        for idx in top_indices:
            top_chunks.append((node_ids[idx], float(similarities[idx]), texts[idx]))
            
        print(f"   Retrieved {len(top_chunks)} relevant chunks")
        
        # Construct context
        context_parts = []
        sources = []
        for i, (node, similarity, text) in enumerate(top_chunks, 1):
            context_parts.append(f"Source {i} (similarity: {similarity:.2f}):\n{text}")
            sources.append(node)
        
        context = "\n\n".join(context_parts)
        
        # Generate answer
        answer_obj = await self.llm.generate_answer(query, context)
        
        result = {
            "query": query,
            "answer": answer_obj.answer,
            "confidence": answer_obj.confidence,
            "sources": sources,
            "source_similarities": [s for _, s, _ in top_chunks],
            "intent": intent.intent
        }
        
        print(f"\n💡 Answer: {answer_obj.answer}")
        print(f"   Confidence: {answer_obj.confidence}")
        
        return result