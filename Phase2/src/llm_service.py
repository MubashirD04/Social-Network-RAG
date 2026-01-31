import os
import asyncio
from dotenv import load_dotenv
from typing import List
from sentence_transformers import SentenceTransformer
from groq import AsyncGroq
import instructor
from pydantic import BaseModel, Field

load_dotenv()

class Entity(BaseModel):
    # Entity extracted
    name: str = Field(description="The exact name of the entity as it appears in the text")
    type: str = Field(description="Entity type: PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, PRODUCT, or OTHER")
    description: str = Field(description="Brief one-sentence description of the entity")
    importance: str = Field(description="Importance level: LOW, MEDIUM, or HIGH")
    
class EntityList(BaseModel):
    # List of entities extracted from text
    entities: List[Entity] = Field(
        default_factory=list,
        description="List of all entities found in text"
    )
    
class Relationship(BaseModel):
    # Relationship between entities
    source: str = Field(description="Source entity name (must match an entity exactly)")
    target: str = Field(description="Target entity name (must match an entity exactly)")
    relationship_type: str = Field(
        description="Type of relationship: WORKS_AT, AFFILIATED_WITH, LOCATED_IN, CREATES, USES, LEADS, MENTIONS, PART_OF, RELATED_TO, DEVELOPS, ANNOUNCES, FEATURES, COLLABORATES_WITH, OWNS, PARTICIPATED_IN, FRIENDS_WITH"
    )
    description: str = Field(description="Brief description of the relationship")
    confidence: str = Field(description="Confidence level: LOW, MEDIUM, or HIGH")

class RelationshipList(BaseModel):
    Relationships: List[Relationship] = Field(
        default_factory=list,
        description="List of all relationships found between entities"
    )
    
class QueryIntent(BaseModel):
    # User query intent
    intent: str = Field(
        description="User's intent: FIND_ENTITY, FIND_RELATIONSHIP, EXPLAIN_CONCEPT, COMPARE, SUMMARIZE, LIST, or OTHER"
    )
    key_entities: List[str] = Field(
        default_factory=list,
        description="Specific entity names mentioned or implied in the query"
    )
    key_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts, topics, or themes mentioned in the query"
    )
    relationship_hints: List[str] = Field(
        default_factory=list,
        description="Relationship types mentioned or implied in the query"
    )
    
class DocumentSummary(BaseModel):
    # Summary of a doc
    summary: str = Field(description="2-3 sentence summary of the document")
    main_topics: List[str] = Field(
        default_factory=list,
        description="List of main topics covered"
    )
    key_entities: List[str] = Field(
        default_factory=list,
        description="Most important entities mentioned"
    )
    
class Answer(BaseModel):
    # Generated answer to user query
    answer: str = Field(description="The answer to the user's question")
    confidence: str = Field(description="Confidence level: LOW, MEDIUM, or HIGH")
    sources_used: List[str] = Field(
        default_factory=list,
        description="List of entities or sources used to generate the answer"
    )
    
class LLMService:
    # Uses Groq with Instructor for structured output and 
    # local sentence transformers for embeddings
    
    def __init__(self, groq_api_key=None):
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY must be provided or set in environment")
        
        # Instructor wraps client to enable structured outputs
        self.client = instructor.from_groq(
            AsyncGroq(api_key=self.api_key),
            mode=instructor.Mode.JSON
        )
        
        # Model selection
        # llama-3.1-8b-instant: Fast, good for extraction
        # llama-3.3-70b-versatile: Better quality, slower (use for complex tasks)
        self.extraction_model = "llama-3.3-70b-versatile"
        self.answer_model = "llama-3.3-70b-versatile"
        
        print("Loading sentence-transformers model...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        print(f"Embeddings model loaded successfully (dimension: {self.embedder.get_sentence_embedding_dimension()})")
        
    def chunk_text(self, text:str, chunk_size: int=500, overlap: int=50):
        # Chunk text with overlap for better context preservation
        words = text.split()
        chunks = []
        
        step_size = max(1, chunk_size-overlap)
        
        for i in range(0, len(words), step_size):
            chunk = ' '.join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        
        return chunks
    
    async def extract_entities(self, text: str):
        # Extract entities from text
        try:
            response = await self.client.chat.completions.create(
                model = self.extraction_model,
                response_model=EntityList,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Extract all important entities from the following text.
                            
                            For each entity, identify:
                            - Name: The exact name as it appears in the text
                            - Type: PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, PRODUCT, TECHNOLOGY, SERVICE, PLATFORM, or OTHER
                            - Description: A brief one-sentence description
                            - Importance: LOW, MEDIUM, or HIGH

                            IMPORTANT RULES:
                            - DO NOT extract dates, months, years, or time periods as entities (e.g. January, 2020)
                            - Avoid extracting duplicate entities with slight variations in format (e.g. COMPANY, COMPANY TECHNOLOGIES, etc.)
                            
                            Text:
                            {text}"""
                    }
                ],
                max_retries=2, # will automatically retry if validation fails
            )
            
            return response.entities
        
        except Exception as e:
            print(f"Entity extraction error: {e}")
            return []
        
    async def extract_relationships(self, entities: List[Entity], text:str):
        # Extract relationships between entities
        if len(entities) < 2:
            return []
        
        # create entity name list for prompt
        entity_names = [e.name for e in entities]
        entity_info = [{"name": e.name, "type": e.type} for e in entities]
        
        try: 
            response = await self.client.chat.completions.create(
                model=self.extraction_model,
                response_model=RelationshipList,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Find all meaningful relationships between these entities in the text.
                            Entities:
                            {entity_info}

                            Text:
                            {text}

                            Relationship types to use:
                            - FAMILY: Explicit family roles (e.g., "mother", "son").
                            - BORN_IN: Place of birth.
                            - BASED_IN: Headquarters or main location.
                            - AFFILIATED_WITH: General connections (political, social, etc.).
                            - WORKED_AT: Past employment.
                            - WORKS_AT: Current employment.
                            - FRIENDS_WITH: Personal friendships.
                            - ACQUINTED_WITH: Brief/professional relationships.
                            - INTEREST_IN: Subject/Thing interest.
                            - LOCATED_IN: Physical containment (city in country, person in room).
                            - PART_OF: Part-to-whole relationships (subsidiaries, departments).
                            - LEADS: Leadership roles (CEO, Founder, Leader).
                            - STUDIED_AT: Academic institutions or subjects.
                            - ASSOCIATED_WITH: Any general association not checking other boxes.
                            - DISCUSSED: When an entity discusses a topic or person.
                            - IMPACTED: When an event or entity impacts another.
                            - PARTICIPATED_IN: Attendance at events.
                            - OWNS: Ownership of objects or companies.
                            - CREATES: Authorship or creation of products/works.
                            
                            IMPORTANT RULES:
                            1. **INFER relationships**: If two entities engage in an action together, are mentioned in the same context, or if one implies the other, extract it. Acknowledge uncertainty with "MEDIUM" or "LOW" confidence.
                            2. **Contextual linking**: If "The CEO announced...", link "CEO" (if named earlier) to the announcement/company.
                            3. **Broad extraction**: Capture "soft" relationships like "discussed", "criticized", "supported".
                            4. **Directionality**: 
                               - "Microsoft acquired Activision" -> Microsoft ACQUIRED Activision
                               - "Activision was acquired by Microsoft" -> Microsoft ACQUIRED Activision
                            
                            Provide a brief description and assign confidence: LOW, MEDIUM, or HIGH
                        """
                    }
                ],
                max_retries=2,
            )
            
            return response.Relationships
        
        except Exception as e:
            print(f"Relationship extraction error: {e}")
            return []
        
    def generate_embeddings(self, texts: List[str]):
        # Generate embeddings using local sentence-transformers
        embeddings = self.embedder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings.tolist()
    
    def get_embeddings_dimension(self):
        return self.embedder.get_sentence_embedding_dimension()
    
    async def summarise_document(self, text:str):
        # Generate a structured summary of a document
        text_to_summarise = text[:4000] if len(text) > 4000 else text

        try:
            response = await self.client.chat.completions.create(
                model=self.answer_model,
                response_model=DocumentSummary,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Provide a comprehensive summary of this document.
                            Include:
                            - A 2-3 sentence summary
                            - Main topics covered (list)
                            - Key entities mentioned (list)

                            Text:
                            {text_to_summarise}
                        """
                    }
                ],
                max_retries=2
            )
            
            return response
        
        except Exception as e:
            print(f"Summary generation error: {e}")
            # Fallback summary
            words = text.split()[:50]
            return DocumentSummary(
                summary=' '.join(words) + "...",
                main_topics=[],
                key_entities=[]
            )
            
    async def understand_query(self, query: str):
        # Understand user query intent for graph search
        try:
            response = await self.client.chat.completions.create(
                model=self.answer_model,
                response_model=QueryIntent,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Analyze this query for knowledge graph search.
                            Query: {query}

                            Extract:
                            - Intent: What is the user trying to do? (FIND_ENTITY, FIND_RELATIONSHIP, EXPLAIN_CONCEPT, COMPARE, SUMMARIZE, LIST, or OTHER)
                            - Key entities: Specific entity names mentioned or implied
                            - Key concepts: Concepts, topics, or themes mentioned
                            - Relationship hints: Any relationship types mentioned or implied
                        """
                    }
                ],
                max_retries=2
            )
            
            return response
        
        except Exception as e:
            print(f"Query understanding error: {e}")
            return QueryIntent(
                intent="OTHER",
                key_entities=[],
                key_concepts=[],
                relationship_hints=[]
            )
            
    async def generate_answer(self, query:str, context:str, include_sources: bool=True):
        # Generate a structured answer to query using retrieved context
        try:
            response = await self.client.chat.completions.create(
                model=self.answer_model,
                response_model=Answer,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Answer this question using ONLY the provided context from the knowledge graph.
                            Question: {query}

                            Context from Knowledge Graph:
                            {context}

                            Provide:
                            - A clear, concise answer
                            - Confidence level (LOW, MEDIUM, or HIGH) based on context quality
                            {"- List of sources/entities used from the context" if include_sources else ""}

                            If the context is insufficient, acknowledge this in your answer and set confidence to LOW.
                        """
                    }
                ],
                max_retries=2,
            )
            
            return response
        
        except Exception as e:
            print(f"Answer generation error: {e}")
            return Answer(
                answer="I apologize, but I encountered an error generating the answer. Please try again.",
                confidence="LOW",
                sources_used=[]
            )
            
    async def batch_extract_entities(self, texts: List[str]):
        # Extract entities from multiple texts concurrently
        print(f"Starting batch extraction for {len(texts)} texts...")
        
        # Create tasks for all texts
        tasks = [self.extract_entities(text) for text in texts]
        
        # execution (gather results)
        results = await asyncio.gather(*tasks)
        
        return results
    
    def batch_generate_embeddings(self, texts: List[str], batch_size: int=32):
        # Generate embeddings for multiple texts efficiently
        # Note: SentenceTransformers is separate from AsyncGroq, 
        # but we can run it in a thread executor if needed to avoid blocking loop
        # For now, keeping it sync as it is CPU bound, but can be optimized later
        
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i+batch_size]
            embeddings = self.generate_embeddings(batch)
            all_embeddings.extend(embeddings)
        
        return all_embeddings

    async def extract_topics(self, messages: List[str]):
        # Extract main topics from a conversation
        
        # Join last N messages to get context
        context = "\n".join(messages[-20:]) if len(messages) > 20 else "\n".join(messages)
        
        class TopicList(BaseModel):
            topics: List[str] = Field(description="List of main topics discussed")
            
        try:
            response = await self.client.chat.completions.create(
                model=self.extraction_model,
                response_model=TopicList,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Extract the main topics discussed in this conversation.
                            Focus on high-level themes (e.g., "Artificial Intelligence", "Project Planning", "Database Architecture").
                            Return at most 5 topics.
                            
                            Conversation:
                            {context}
                        """
                    }
                ],
                max_retries=2
            )
            return response.topics
        except Exception as e:
            print(f"Topic extraction error: {e}")
            return []