from llm_service import LLMService

import asyncio

async def main():
    # Initialize service
    print("Initializing LLM Service...")
    llm_service = LLMService(None)
    print("Service initialized successfully!\n")
    
    # Test text
    test_text = """
        Gregory J. Hayes[3] (born 1960/61) is an American businessman. He was the chairman and CEO of United Technologies from September 2016 until April 2020, when United Technologies merged with Raytheon, at which point he became the CEO of the merged company, RTX Corporation. Hayes has announced his retirement from that position, to become effective on May 2, 2024.[4] 
        Hayes grew up in Williamsville, New York, and was a 1978 graduate of Williamsville South High School.[citation needed] Hayes played football at Cornell University, while studying pre-law for a year,[3] then transferred to the Krannert School of Management[3] at Purdue University, where he earned a bachelor's degree in economics[1] in 1982. He later became a CPA.[3]
        After graduating, Hayes joined Sundstrand Corporation, which was acquired by United Technologies (UTC) in 1999. He rose through management, becoming CEO of UTC in November 2014, succeeding Louis R. Chênevert.[5] Hayes was elected chairman in September 2016.[1]

        In April 2020, Raytheon Company completed their merger with UTC to form Raytheon Technologies. Hayes was named CEO of the combined company, and Raytheon chairman and CEO Thomas A. Kennedy was named executive chairman.[6]

        In September 2022, Foreign Ministry of China spokesperson Mao Ning announced at a press briefing that China has imposed sanctions on Hayes and Boeing Defense, Space & Security CEO Theodore Colbert III, in response to the U.S. arms sale to Taiwan. It is not immediately known what the Chinese sanctions against Hayes and Colbert would entail, and it is often mainly symbolic in nature.[7] 

        """
    
    print("=" * 80)
    print("Testing Entity Extraction")
    print("=" * 80)
    entities = await llm_service.extract_entities(test_text)
    print(f"Found {len(entities)} entities:\n")
    for entity in entities:
        print(f"  • {entity.name} ({entity.type})")
        print(f"    {entity.description}")
        print(f"    Importance: {entity.importance}\n")
    
    print("=" * 80)
    print("Testing Relationship Extraction")
    print("=" * 80)
    if len(entities) >= 2:
        relationships = await llm_service.extract_relationships(entities, test_text)
        print(f"Found {len(relationships)} relationships:\n")
        for rel in relationships:
            print(f"  • {rel.source} --[{rel.relationship_type}]--> {rel.target}")
            print(f"    {rel.description}")
            print(f"    Confidence: {rel.confidence}\n")
    
    print("=" * 80)
    print("Testing Embeddings")
    print("=" * 80)
    chunks = llm_service.chunk_text(test_text, chunk_size=50)
    embeddings = llm_service.generate_embeddings(chunks)
    print(f"Generated {len(embeddings)} embeddings")
    print(f"Embedding dimension: {len(embeddings[0])}")
    print(f"Sample embedding (first 5 values): {embeddings[0][:5]}\n")
    
    print("\n" + "=" * 80)
    print("All tests completed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())