from src.social_graph_builder import SocialGraphBuilder, Message
from datetime import datetime, timedelta
import asyncio

async def main():
    """Demo: Analyze a group chat to find influencers and communities"""
    
    print("="*80)
    print("🔍 Social Network Analysis Demo")
    print("="*80)
    
    # Sample group chat data
    base_time = datetime.now() - timedelta(days=1)
    
    sample_messages = [
        Message(id="1", sender="Alice", content="Hey everyone! What do you think about the new AI project?", timestamp=base_time),
        Message(id="2", sender="Bob", content="@Alice I think it's really promising! We should dive deeper into LLMs.", timestamp=base_time + timedelta(minutes=5)),
        Message(id="3", sender="Charlie", content="Agreed! The RAG approach seems solid.", timestamp=base_time + timedelta(minutes=7), reply_to="2", reactions=["Alice", "Bob"]),
        Message(id="4", sender="Alice", content="@Bob Great point! Let's schedule a meeting to discuss implementation.", timestamp=base_time + timedelta(minutes=10), reactions=["Bob", "Charlie", "Diana"]),
        Message(id="5", sender="Diana", content="I can help with the data pipeline. When should we meet?", timestamp=base_time + timedelta(minutes=12), reply_to="4"),
        Message(id="6", sender="Eve", content="Has anyone tested the embeddings model yet?", timestamp=base_time + timedelta(minutes=15)),
        Message(id="7", sender="Bob", content="@Eve Yes! I tested sentence-transformers. Works well for our use case.", timestamp=base_time + timedelta(minutes=18), reactions=["Alice", "Eve"]),
        Message(id="8", sender="Charlie", content="We should also consider the graph database architecture.", timestamp=base_time + timedelta(minutes=20)),
        Message(id="9", sender="Alice", content="@Charlie Absolutely! Neo4j would be perfect for this.", timestamp=base_time + timedelta(minutes=22), reply_to="8"),
        Message(id="10", sender="Diana", content="I've worked with Neo4j before. Happy to share best practices.", timestamp=base_time + timedelta(minutes=25), reactions=["Alice", "Charlie", "Bob"]),
        Message(id="11", sender="Frank", content="What's the timeline for this project?", timestamp=base_time + timedelta(minutes=30)),
        Message(id="12", sender="Alice", content="@Frank We're aiming for 4 weeks. First milestone is the MVP.", timestamp=base_time + timedelta(minutes=32), reply_to="11"),
        Message(id="13", sender="Bob", content="The knowledge graph extraction is the most critical part.", timestamp=base_time + timedelta(minutes=35)),
        Message(id="14", sender="Charlie", content="@Bob Agreed. We need to nail the entity extraction.", timestamp=base_time + timedelta(minutes=37), reply_to="13", reactions=["Alice", "Bob"]),
        Message(id="15", sender="Eve", content="Should we use OpenAI or stick with open source?", timestamp=base_time + timedelta(minutes=40)),
        Message(id="16", sender="Alice", content="@Eve Let's go with Groq for speed. It's been solid so far.", timestamp=base_time + timedelta(minutes=42), reactions=["Bob", "Charlie", "Diana", "Eve"]),
        Message(id="17", sender="Diana", content="Makes sense. Cost efficiency is important too.", timestamp=base_time + timedelta(minutes=45)),
        Message(id="18", sender="Frank", content="When's the next standup?", timestamp=base_time + timedelta(minutes=50)),
        Message(id="19", sender="Alice", content="Tomorrow 10am. I'll send a calendar invite.", timestamp=base_time + timedelta(minutes=52), reply_to="18", reactions=["Frank"]),
        Message(id="20", sender="Bob", content="Looking forward to it! This is going to be great.", timestamp=base_time + timedelta(minutes=55), reactions=["Alice", "Charlie", "Diana"]),
    ]
    
    # Initialize builder
    builder = SocialGraphBuilder()
    
    # Process chat data
    stats = await builder.process_chat_data(sample_messages, chat_name="ai_project_team")
    
    # Print results
    print("\n" + "="*80)
    print("📊 Social Network Statistics")
    print("="*80)
    print(f"\n👥 Total Participants: {stats['total_people']}")
    print(f"💬 Total Messages: {stats['total_messages']}")
    print(f"🏷️  Topics Discussed: {stats['total_topics']}")
    
    print("\n🌟 TOP INFLUENCERS (Decision Makers):")
    for person in stats['influencers']:
        print(f"   • {person['name']} - Influence Score: {person['score']:.3f}")
    
    print("\n🔗 INFO BROKERS (Information Flows Through):")
    for person in stats['info_brokers']:
        print(f"   • {person['name']} - Broker Score: {person['score']:.3f}")
    
    print("\n💪 MOST ACTIVE:")
    for person in stats['most_active']:
        print(f"   • {person['name']} - {person['messages']} messages")
    
    # Get detailed influence report
    print("\n" + "="*80)
    print("📈 Detailed Influence Report")
    print("="*80)
    
    report = builder.get_influence_report()
    for person_data in report:
        print(f"\n👤 {person_data['name']}:")
        print(f"   Messages Sent: {person_data['message_count']}")
        print(f"   Replies Received: {person_data['replies_received']}")
        print(f"   Influence (PageRank): {person_data['pagerank']:.3f}")
        print(f"   Info Broker Score: {person_data['betweenness']:.3f}")
        
        badges = []
        if person_data['is_influencer']:
            badges.append("🌟 INFLUENCER")
        if person_data['is_info_broker']:
            badges.append("🔗 INFO BROKER")
        if badges:
            print(f"   Status: {' | '.join(badges)}")
        print(f"   Community: {person_data['community']}")
    
    # Visualize
    print("\n" + "="*80)
    print("🎨 Creating Visualization")
    print("="*80)
    
    html_file = builder.visualize("output/social_network.html")
    
    # Save graph
    builder.save_graph("output/social_network.graphml")
    
    print("\n" + "="*80)
    print("✅ Analysis Complete!")
    print("="*80)
    print(f"\n🌐 Open '{html_file}' to explore the social network!")
    print(f"💾 Graph data saved to 'output/social_network.graphml'")
    print("\n💡 Key Insights:")
    print("   • Larger nodes = More influential")
    print("   • Yellow arrows = Replies")
    print("   • Teal nodes = People")
    print("   • Yellow diamonds = Topics discussed")

if __name__ == "__main__":
    asyncio.run(main())
