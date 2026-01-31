from llm_service import LLMService
from graph_builder import KnowledgeGraphBuilder

import asyncio

async def main():
    # Sample document
    sample_document = """
    Microsoft Corporation, founded by Bill Gates and Paul Allen in 1975, is headquartered 
    in Redmond, Washington. The company is currently led by CEO Satya Nadella, who took 
    over from Steve Ballmer in 2014.
    
    Microsoft has been heavily investing in artificial intelligence and cloud computing. 
    The company's Azure platform competes with Amazon Web Services and Google Cloud. 
    In 2023, Microsoft announced a major partnership with OpenAI, integrating GPT models 
    into their products.
    
    The company develops various products including the Windows operating system, 
    Office productivity suite, Xbox gaming consoles, and Surface devices. Microsoft also 
    owns GitHub, LinkedIn, and has acquired several gaming companies including Activision Blizzard.
    
    In recent years, Microsoft has focused on sustainability, pledging to become carbon 
    negative by 2030. The company invests heavily in renewable energy and has committed 
    to removing its historical carbon emissions.
    """
    
    print("="*80)
    print("Knowledge Graph Builder - Demo with Community Detection")
    print("="*80)
    
    # Initialize
    print("\n🚀 Initializing LLM Service and Graph Builder...")
    builder = KnowledgeGraphBuilder()
    
    # Process document
    stats = await builder.process_text(sample_document, source_name="microsoft_overview")
    
    # Add similarity edges between chunks
    builder.add_similarity_edges(similarity_threshold=0.6)
    
    # Detect communities using different algorithms
    print("\n" + "="*80)
    print("Community Detection")
    print("="*80)
    
    # Try Louvain (default - usually best)
    print("\n1️⃣ Louvain Algorithm (default):")
    community_map = builder.detect_communities(algorithm="louvain", resolution=1.0)
    
    # Assign colors based on communities
    builder.assign_community_colors()
    
    # Get summaries of each community
    if community_map:
        unique_communities = set(community_map.values())
        print(f"\n📋 Community Summaries:")
        for comm_id in sorted(unique_communities):
            if comm_id != -1:  # Skip disconnected nodes
                summary = builder.get_community_summary(comm_id)
                print(f"\n   Community {comm_id}:")
                print(f"      Nodes: {summary['total_nodes']}")
                print(f"      Types: {summary['node_types']}")
                if summary['entity_types']:
                    print(f"      Entity Types: {summary['entity_types']}")
                print(f"      Internal Edges: {summary['internal_edges']}")
                print(f"      External Edges: {summary['external_edges']}")
                print(f"      Key Members:")
                for node_info in summary['key_nodes'][:5]:
                    print(f"         - {node_info['label']} ({node_info['type']}, centrality: {node_info['centrality']})")
    
    # Print statistics with community info
    print(f"\n📊 Graph Statistics:")
    graph_stats = builder.get_graph_stats()
    print(f"   Total Nodes: {graph_stats['total_nodes']}")
    print(f"   Total Edges: {graph_stats['total_edges']}")
    print(f"   Graph Density: {graph_stats['density']:.3f}")
    print(f"   Isolated Nodes: {graph_stats['isolated_nodes']}")
    print(f"   Node Types: {graph_stats['node_types']}")
    print(f"   Entity Types: {graph_stats['entity_types']}")
    print(f"   Relationship Types: {graph_stats['relationship_types']}")
    
    if graph_stats['communities']:
        print(f"\n   Communities Detected: {graph_stats['communities']['num_communities']}")
        print(f"   Community Sizes: {graph_stats['communities']['sizes']}")
    
    # Save graph
    print(f"\n💾 Saving graph...")
    builder.save_graph("microsoft_graph.graphml")
    
    # Create visualization (with community colors)
    html_file = builder.visualise("microsoft_graph.html")
    
    # Query the graph
    print("\n" + "="*80)
    print("Testing RAG Query System")
    print("="*80)
    
    queries = [
        "Who is the CEO of Microsoft?",
        "What is Microsoft's approach to sustainability?",
        "What products does Microsoft make?",
    ]
    
    for query in queries:
        result = await builder.query_graph(query, top_k=2)
        print()
    
    print("\n" + "="*80)
    print("✅ Demo Complete!")
    print("="*80)
    print(f"\n🌐 Open '{html_file}' in your browser to explore the interactive graph!")
    print(f"💾 Graph saved to 'microsoft_graph.graphml'")
    print(f"\n💡 Tip: Nodes are now colored by community - same color = same community!")

if __name__ == "__main__":
    asyncio.run(main())