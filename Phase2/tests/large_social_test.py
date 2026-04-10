import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.social_graph_builder import SocialGraphBuilder
from src.social_models import Message
from datetime import datetime, timedelta
import asyncio
import random

async def main():
    """Large-scale demo: Analyze a realistic group chat with complex social dynamics"""
    
    print("="*80)
    print("🔍 LARGE-SCALE Social Network Analysis Demo")
    print("="*80)
    
    # Simulate a week-long group chat about a startup project
    base_time = datetime.now() - timedelta(days=7)
    
    # 10 participants with different roles and personalities
    participants = {
        "Sarah": "CEO - visionary, active, makes decisions",
        "Mike": "CTO - technical lead, highly connected",
        "Emma": "Product Manager - coordinates teams",
        "James": "Lead Dev - implements, asks questions",
        "Lisa": "Designer - creative input",
        "David": "Marketing - external focus",
        "Rachel": "Data Scientist - analytical",
        "Tom": "Backend Dev - quiet but crucial",
        "Nina": "Frontend Dev - active contributor",
        "Alex": "Intern - learning, asks lots of questions"
    }
    
    print(f"\n👥 Participants: {len(participants)}")
    for name, role in participants.items():
        print(f"   • {name}: {role}")
    
    # Large realistic message set
    sample_messages = [
        # Monday - Project kickoff
        Message(id="1", sender="Sarah", content="Good morning team! Excited to kick off our new AI-powered analytics platform. Let's make this week count! 🚀", timestamp=base_time),
        Message(id="2", sender="Mike", content="@Sarah Absolutely! I've been reviewing the tech stack. Thinking Python backend with React frontend.", timestamp=base_time + timedelta(minutes=5)),
        Message(id="3", sender="Emma", content="Great! I'll start mapping out the user journey today. @Lisa can you join me for a design sync?", timestamp=base_time + timedelta(minutes=8), reactions=["Lisa", "Sarah"]),
        Message(id="4", sender="Lisa", content="@Emma Yes! Let's do 2pm. I have some mockups ready.", timestamp=base_time + timedelta(minutes=10), reply_to="3"),
        Message(id="5", sender="James", content="@Mike What database are we thinking? Neo4j for the graph stuff?", timestamp=base_time + timedelta(minutes=12)),
        Message(id="6", sender="Mike", content="@James Exactly! Neo4j for the knowledge graph, PostgreSQL for user data. Thinking about using FastAPI.", timestamp=base_time + timedelta(minutes=15), reply_to="5", reactions=["James", "Tom", "Rachel"]),
        Message(id="7", sender="David", content="Hey team! When do we want to start thinking about go-to-market strategy?", timestamp=base_time + timedelta(minutes=20)),
        Message(id="8", sender="Sarah", content="@David Let's focus on MVP first, but start documenting our unique value prop. What makes us different?", timestamp=base_time + timedelta(minutes=22), reply_to="7"),
        Message(id="9", sender="Rachel", content="From a data perspective, the RAG approach is really powerful. Should we use GPT-4 or open source?", timestamp=base_time + timedelta(minutes=30)),
        Message(id="10", sender="Mike", content="@Rachel I'm leaning towards Groq with Llama models. Cost-effective and fast enough for our use case.", timestamp=base_time + timedelta(minutes=32), reactions=["Sarah", "Rachel", "James"]),
        Message(id="11", sender="Alex", content="Quick question - what's RAG? Still learning about all this 😅", timestamp=base_time + timedelta(minutes=35)),
        Message(id="12", sender="Rachel", content="@Alex It's Retrieval-Augmented Generation! Basically we retrieve relevant info from a database before generating responses. Makes AI more accurate.", timestamp=base_time + timedelta(minutes=37), reply_to="11", reactions=["Alex", "Nina"]),
        Message(id="13", sender="Tom", content="I can start working on the backend API structure. @Mike should I create a separate repo or monorepo?", timestamp=base_time + timedelta(minutes=45)),
        Message(id="14", sender="Mike", content="@Tom Let's go monorepo with pnpm workspaces. Easier to manage initially.", timestamp=base_time + timedelta(minutes=47), reply_to="13"),
        Message(id="15", sender="Nina", content="I'll handle the frontend architecture. Thinking Vite + React + TypeScript + Tailwind.", timestamp=base_time + timedelta(minutes=50), reactions=["Mike", "Lisa"]),
        
        # Tuesday - Deep technical discussions
        Message(id="16", sender="James", content="Started implementing the entity extraction pipeline. The LLM is taking ~2 seconds per chunk. Any optimization ideas?", timestamp=base_time + timedelta(days=1, hours=9)),
        Message(id="17", sender="Mike", content="@James Try batching the requests and running them concurrently with asyncio. Should cut time significantly.", timestamp=base_time + timedelta(days=1, hours=9, minutes=5), reply_to="16", reactions=["James", "Rachel"]),
        Message(id="18", sender="Rachel", content="@James Also consider caching embeddings. No need to regenerate for the same text.", timestamp=base_time + timedelta(days=1, hours=9, minutes=8), reactions=["James", "Mike"]),
        Message(id="19", sender="Tom", content="Backend API is up! Deployed at https://dev-api.ourapp.com - still very basic though", timestamp=base_time + timedelta(days=1, hours=10), reactions=["Sarah", "Mike", "Nina", "James"]),
        Message(id="20", sender="Sarah", content="@Tom Amazing progress! 🎉", timestamp=base_time + timedelta(days=1, hours=10, minutes=2), reply_to="19"),
        Message(id="21", sender="Nina", content="@Tom Perfect! I'll start integrating with the frontend.", timestamp=base_time + timedelta(days=1, hours=10, minutes=5)),
        Message(id="22", sender="Lisa", content="Design system is ready! Check out Figma: [link]. @Emma @Nina thoughts?", timestamp=base_time + timedelta(days=1, hours=11), reactions=["Emma", "Nina", "Sarah"]),
        Message(id="23", sender="Emma", content="@Lisa Love it! The color scheme is perfect for our brand.", timestamp=base_time + timedelta(days=1, hours=11, minutes=10), reply_to="22"),
        Message(id="24", sender="Nina", content="@Lisa This is gorgeous! Starting implementation now.", timestamp=base_time + timedelta(days=1, hours=11, minutes=12)),
        Message(id="25", sender="David", content="Working on the landing page copy. Who's our primary target audience again?", timestamp=base_time + timedelta(days=1, hours=14)),
        Message(id="26", sender="Emma", content="@David B2B SaaS companies looking to analyze customer conversations at scale. Think Slack communities, support tickets.", timestamp=base_time + timedelta(days=1, hours=14, minutes=5), reply_to="25", reactions=["David", "Sarah"]),
        Message(id="27", sender="Alex", content="I've been reading about graph databases. This is fascinating! Can I help with testing?", timestamp=base_time + timedelta(days=1, hours=15)),
        Message(id="28", sender="Mike", content="@Alex Absolutely! We need all the help we can get with QA. I'll add you to the testing Notion board.", timestamp=base_time + timedelta(days=1, hours=15, minutes=5), reactions=["Alex", "Emma"]),
        
        # Wednesday - First demo preparation
        Message(id="29", sender="Sarah", content="Team standup in 10 mins! Let's sync on progress.", timestamp=base_time + timedelta(days=2, hours=10)),
        Message(id="30", sender="Emma", content="I'll have the user flow ready to present.", timestamp=base_time + timedelta(days=2, hours=10, minutes=2)),
        Message(id="31", sender="Mike", content="Tech demo is ready. We can show the graph visualization!", timestamp=base_time + timedelta(days=2, hours=10, minutes=3), reactions=["Sarah", "Emma", "James"]),
        Message(id="32", sender="Sarah", content="Standup was great! Love the progress. @Mike that demo was 🔥", timestamp=base_time + timedelta(days=2, hours=11)),
        Message(id="33", sender="Rachel", content="Question about the similarity algorithm - should we use cosine or euclidean distance for embeddings?", timestamp=base_time + timedelta(days=2, hours=14)),
        Message(id="34", sender="Mike", content="@Rachel Cosine similarity is standard for embeddings. It's scale-invariant which is what we want.", timestamp=base_time + timedelta(days=2, hours=14, minutes=5), reply_to="33"),
        Message(id="35", sender="James", content="@Rachel I can implement both and we can A/B test?", timestamp=base_time + timedelta(days=2, hours=14, minutes=8)),
        Message(id="36", sender="Rachel", content="@James Good idea! Let's compare results.", timestamp=base_time + timedelta(days=2, hours=14, minutes=10), reactions=["Mike", "James"]),
        Message(id="37", sender="Lisa", content="Updated the dashboard mockups based on feedback. Much cleaner now!", timestamp=base_time + timedelta(days=2, hours=15), reactions=["Emma", "Nina", "Sarah"]),
        Message(id="38", sender="Nina", content="Frontend is coming together nicely. The graph visualization is smooth!", timestamp=base_time + timedelta(days=2, hours=16), reactions=["Mike", "Lisa", "Tom"]),
        
        # Thursday - Challenges arise
        Message(id="39", sender="Tom", content="Running into a scaling issue. Graph queries are slow with 1000+ nodes. 😰", timestamp=base_time + timedelta(days=3, hours=9)),
        Message(id="40", sender="Mike", content="@Tom This is expected. We need to add indexes on Neo4j. Let me help you optimize the Cypher queries.", timestamp=base_time + timedelta(days=3, hours=9, minutes=5), reply_to="39", reactions=["Tom", "Sarah"]),
        Message(id="41", sender="Rachel", content="@Tom Also consider pagination. Don't load the entire graph at once.", timestamp=base_time + timedelta(days=3, hours=9, minutes=8)),
        Message(id="42", sender="James", content="I can help! I've dealt with this before. We should use vector indexes for the embedding similarity search.", timestamp=base_time + timedelta(days=3, hours=9, minutes=12), reactions=["Mike", "Tom", "Rachel"]),
        Message(id="43", sender="Tom", content="Thanks everyone! Let's pair on this. @Mike @James free after lunch?", timestamp=base_time + timedelta(days=3, hours=9, minutes=20)),
        Message(id="44", sender="Mike", content="@Tom Yep! 2pm work?", timestamp=base_time + timedelta(days=3, hours=9, minutes=22)),
        Message(id="45", sender="James", content="@Tom I'm in!", timestamp=base_time + timedelta(days=3, hours=9, minutes=23)),
        Message(id="46", sender="Emma", content="Quick update: talked to 3 potential customers today. They're very interested in the community detection feature!", timestamp=base_time + timedelta(days=3, hours=14), reactions=["Sarah", "David", "Mike"]),
        Message(id="47", sender="Sarah", content="@Emma That's fantastic news! What specific use cases are they mentioning?", timestamp=base_time + timedelta(days=3, hours=14, minutes=5)),
        Message(id="48", sender="David", content="@Emma Can you share those insights? Would be great for the marketing messaging.", timestamp=base_time + timedelta(days=3, hours=14, minutes=7)),
        Message(id="49", sender="Emma", content="@Sarah @David They want to identify influencers in their Slack communities and understand information flow. Exactly what we're building! 🎯", timestamp=base_time + timedelta(days=3, hours=14, minutes=15), reactions=["Sarah", "David", "Mike", "Rachel"]),
        Message(id="50", sender="Alex", content="Tested the latest build - found a bug in the search feature. Creating a ticket now.", timestamp=base_time + timedelta(days=3, hours=16)),
        Message(id="51", sender="Nina", content="@Alex Thanks! Can you assign it to me? I'll fix it tonight.", timestamp=base_time + timedelta(days=3, hours=16, minutes=5), reactions=["Alex"]),
        
        # Friday - Week wrap-up
        Message(id="52", sender="Sarah", content="Friday standup! Let's celebrate our wins this week 🎉", timestamp=base_time + timedelta(days=4, hours=10)),
        Message(id="53", sender="Mike", content="Performance issues are solved! Graph queries are now under 500ms even with 2000 nodes.", timestamp=base_time + timedelta(days=4, hours=10, minutes=2), reactions=["Tom", "Sarah", "James", "Rachel"]),
        Message(id="54", sender="Tom", content="@Mike Couldn't have done it without your help. Learning so much!", timestamp=base_time + timedelta(days=4, hours=10, minutes=5)),
        Message(id="55", sender="Nina", content="Frontend is looking amazing! The animations are smooth as butter.", timestamp=base_time + timedelta(days=4, hours=10, minutes=8), reactions=["Lisa", "Emma"]),
        Message(id="56", sender="Lisa", content="@Nina The design implementation is perfect! Exactly what I envisioned.", timestamp=base_time + timedelta(days=4, hours=10, minutes=10)),
        Message(id="57", sender="Rachel", content="ML pipeline is solid. Entity extraction accuracy is at 92%!", timestamp=base_time + timedelta(days=4, hours=10, minutes=15), reactions=["Mike", "Sarah", "James"]),
        Message(id="58", sender="Emma", content="@Rachel That's impressive! How did you measure it?", timestamp=base_time + timedelta(days=4, hours=10, minutes=18)),
        Message(id="59", sender="Rachel", content="@Emma Manual validation on 100 sample conversations. Created a benchmark dataset.", timestamp=base_time + timedelta(days=4, hours=10, minutes=22), reactions=["Emma", "Mike"]),
        Message(id="60", sender="David", content="Marketing site is live! Check it out: www.ourapp.com", timestamp=base_time + timedelta(days=4, hours=14), reactions=["Sarah", "Emma", "Lisa", "Mike", "Nina"]),
        Message(id="61", sender="Sarah", content="@David This looks fantastic! Great work everyone this week. Team dinner tonight? 🍕", timestamp=base_time + timedelta(days=4, hours=14, minutes=5), reactions=["Mike", "Emma", "James", "Lisa", "David", "Rachel", "Tom", "Nina", "Alex"]),
        Message(id="62", sender="Alex", content="This has been the best week! Learning so much from everyone.", timestamp=base_time + timedelta(days=4, hours=14, minutes=10), reactions=["Sarah", "Mike"]),
        Message(id="63", sender="Mike", content="@Alex You're doing great! Keep asking questions.", timestamp=base_time + timedelta(days=4, hours=14, minutes=12)),
        
        # Weekend - Some async work
        Message(id="64", sender="James", content="Couldn't help myself... added that feature we discussed. PR is up! 😄", timestamp=base_time + timedelta(days=5, hours=15)),
        Message(id="65", sender="Mike", content="@James You're unstoppable! Will review Monday morning.", timestamp=base_time + timedelta(days=5, hours=16), reactions=["James"]),
        Message(id="66", sender="Nina", content="Also worked on some UI polish. The graph now has a dark mode! 🌙", timestamp=base_time + timedelta(days=5, hours=18), reactions=["Lisa", "Mike", "Tom"]),
        Message(id="67", sender="Lisa", content="@Nina OMG I love it! Dark mode was on my wish list.", timestamp=base_time + timedelta(days=5, hours=18, minutes=10)),
        
        # Monday - New week
        Message(id="68", sender="Sarah", content="New week, new goals! Let's push towards our beta launch. 2 weeks to go! 💪", timestamp=base_time + timedelta(days=7, hours=9)),
        Message(id="69", sender="Emma", content="I have 5 beta testers lined up. When can we give them access?", timestamp=base_time + timedelta(days=7, hours=9, minutes=10)),
        Message(id="70", sender="Mike", content="@Emma Let's aim for Friday. Need to implement auth and do security review first.", timestamp=base_time + timedelta(days=7, hours=9, minutes=15), reactions=["Sarah", "Emma"]),
        Message(id="71", sender="Tom", content="I can handle the auth implementation. OAuth with Google and GitHub?", timestamp=base_time + timedelta(days=7, hours=9, minutes=20)),
        Message(id="72", sender="Mike", content="@Tom Perfect. Yes, let's support both.", timestamp=base_time + timedelta(days=7, hours=9, minutes=22)),
        Message(id="73", sender="Rachel", content="Working on improving the topic extraction. Found a better prompt that increases accuracy.", timestamp=base_time + timedelta(days=7, hours=10)),
        Message(id="74", sender="Sarah", content="@Rachel You're crushing it! Share the details when you can.", timestamp=base_time + timedelta(days=7, hours=10, minutes=5), reactions=["Rachel"]),
        Message(id="75", sender="David", content="Posted our first LinkedIn update. Already getting interest from potential customers! 📈", timestamp=base_time + timedelta(days=7, hours=11), reactions=["Sarah", "Emma", "Mike"]),
    ]
    
    print(f"\n💬 Total Messages: {len(sample_messages)}")
    
    # Initialize builder
    print("\n🚀 Initializing Social Graph Builder...")
    builder = SocialGraphBuilder()
    
    # Process chat data
    print("\n⚙️  Processing chat data (this may take a minute)...")
    stats = await builder.process_chat_data(sample_messages, chat_name="startup_team_chat")
    
    # Print results
    print("\n" + "="*80)
    print("📊 SOCIAL NETWORK STATISTICS")
    print("="*80)
    print(f"\n👥 Total Participants: {stats['total_people']}")
    print(f"💬 Total Messages: {stats['total_messages']}")
    print(f"🏷️  Topics Discussed: {stats['total_topics']}")
    
    print("\n" + "="*80)
    print("🌟 TOP INFLUENCERS (Decision Makers)")
    print("="*80)
    print("\nThese people drive the conversation and make key decisions:")
    for i, person in enumerate(stats['influencers'], 1):
        print(f"\n{i}. {person['name']}")
        print(f"   Influence Score: {person['score']:.3f}")
        print(f"   Role: {participants.get(person['name'], 'Unknown')}")
    
    print("\n" + "="*80)
    print("🔗 INFO BROKERS (Information Flows Through)")
    print("="*80)
    print("\nThese people connect different groups and facilitate information flow:")
    for i, person in enumerate(stats['info_brokers'], 1):
        print(f"\n{i}. {person['name']}")
        print(f"   Broker Score: {person['score']:.3f}")
        print(f"   Role: {participants.get(person['name'], 'Unknown')}")
    
    print("\n" + "="*80)
    print("💪 MOST ACTIVE PARTICIPANTS")
    print("="*80)
    for i, person in enumerate(stats['most_active'], 1):
        print(f"{i}. {person['name']} - {person['messages']} messages ({participants.get(person['name'], 'Unknown')})")
    
    # Get detailed influence report
    print("\n" + "="*80)
    print("📈 DETAILED INFLUENCE REPORT")
    print("="*80)
    
    report = builder.get_influence_report()
    for person_data in report[:8]:  # Show top 8
        print(f"\n{'='*60}")
        print(f"👤 {person_data['name']} - {participants.get(person_data['name'], 'Unknown')}")
        print(f"{'='*60}")
        print(f"Messages Sent:        {person_data['message_count']}")
        print(f"Replies Received:     {person_data['replies_received']}")
        print(f"Influence (PageRank): {person_data['pagerank']:.3f}")
        print(f"Info Broker Score:    {person_data['betweenness']:.3f}")
        
        badges = []
        if person_data['is_influencer']:
            badges.append("🌟 INFLUENCER")
        if person_data['is_info_broker']:
            badges.append("🔗 INFO BROKER")
        if person_data['message_count'] >= 10:
            badges.append("💪 HIGHLY ACTIVE")
        if badges:
            print(f"\nBadges: {' | '.join(badges)}")
        print(f"Community: Group {person_data['community']}")
    
    # Visualize
    print("\n" + "="*80)
    print("🎨 CREATING INTERACTIVE VISUALIZATION")
    print("="*80)
    
    html_file = builder.visualize("output/startup_social_network.html")
    
    # Save graph
    builder.save_graph("output/startup_social_network.graphml")
    
    # Final insights
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE!")
    print("="*80)
    print(f"\n🌐 Open '{html_file}' to explore the interactive social network!")
    print(f"💾 Graph data saved to 'output/startup_social_network.graphml'")
    
    print("\n" + "="*80)
    print("💡 KEY INSIGHTS")
    print("="*80)
    print("""
Visualization Guide:
  • Larger nodes = More influential people
  • Yellow arrows = Reply threads
  • Teal circles = People
  • Yellow diamonds = Topics discussed
  • Node clusters = Communities/subgroups

What to Look For:
  • Central nodes = Key decision makers (usually founders/leads)
  • Bridge nodes = Information brokers (PMs, coordinators)
  • Isolated nodes = People who need more engagement
  • Dense clusters = Tight-knit subteams
  • Topic nodes = What the team discusses most

Social Dynamics:
  • Mike (CTO) appears as a central info broker - expected for tech lead
  • Sarah (CEO) likely shows high influence - drives decisions
  • Emma (PM) probably bridges different groups
  • Check if quiet members like Tom are still connected
    """)
    
    print("\n" + "="*80)
    print("🎯 ACTIONABLE RECOMMENDATIONS")
    print("="*80)
    
    # Generate recommendations based on the data
    print("""
Based on this analysis, you could:

1. Identify Leadership Gaps
   → Check if all teams have clear leaders with high influence scores
   → Look for teams where no one has high betweenness (poor coordination)

2. Improve Communication
   → Find people with low reply counts (might need more engagement)
   → Identify isolated nodes (people not integrated into the team)

3. Optimize Information Flow
   → Ensure info brokers aren't bottlenecks
   → Create backup communication paths

4. Balance Workload
   → Compare message counts with project contributions
   → Spot people who are over/under-communicating

5. Strengthen Teams
   → Look at community detection results
   → Bridge disconnected communities if needed
    """)

if __name__ == "__main__":
    asyncio.run(main())
