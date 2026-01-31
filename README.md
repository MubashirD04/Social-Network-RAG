# Social Network RAG

A powerful social network analysis tool that uses Retrieval-Augmented Generation principles to analyze group chat interactions, identify key influencers, and visualize community structures.

## Overview

This project provides a framework for processing chat data into a directed graph of social interactions. It leverages NetworkX for graph algorithms, PyVis for interactive web-based visualizations, and LLM services for semantic topic extraction.

## Key Features

- Social Graph Construction: Automatically builds nodes for participants, messages, and topics from raw chat logs.
- Interaction Analysis: Tracks replies, mentions, and reactions to map the flow of communication.
- Influence Metrics:
  - PageRank: Identifies key decision makers and influential members.
  - Betweenness Centrality: Highlights information brokers who bridge different groups.
  - Activity Tracking: Measures message volume and engagement levels.
- Community Detection: Groups participants into clusters based on their interaction patterns.
- Semantic Topic Extraction: Uses LLMs to identify recurring themes and subjects within the conversation.
- Interactive Visualization: Generates a standalone HTML report with a dynamic sidebar for filtering and detailed node inspection.
- Data Export: Supports GraphML for further analysis in tools like Gephi or Cytoscape.

## Project Structure

- Phase1/: Contains initial prototyping and experimental notebooks.
- Phase2/: The primary application codebase.
  - src/: Core logic including graph building and LLM service integration.
  - social_demo.py/: A demonstration script showing the analysis of sample chat data.
  - output/: Directory for generated visualizations and graph data.
  - tests/: Unit tests for various components.

## Getting Started

### Prerequisites

- Python 3.8+
- An API key for supported LLM services (e.g., Groq) if using topic extraction.

### Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your environment variables in a .env file:
   ```env
   GROQ_API_KEY=your_api_key_here
   ```

### Running the Demo

To see the system in action, run the Phase 2 demo:

```bash
python Phase2/social_demo.py
```

This will process a sample chat, calculate social statistics, and generate a visualization in the `Phase2/output/` directory.

## Usage

The system centers around the `SocialGraphBuilder` class. You can feed it a list of message objects, and it will handle the graph construction and metric calculation.

```python
from src.social_graph_builder import SocialGraphBuilder, Message

builder = SocialGraphBuilder()
await builder.process_chat_data(messages, chat_name="my_chat")
builder.visualize("output/social_network.html")
```

## Visualization Legend

- Teal Nodes: People
- Yellow Diamonds: Topics
- Light Blue Ellipses: Messages
- Yellow Arrows: Reply chains
- Node Size: Larger nodes indicate higher influence (PageRank)
- Colors: Participant colors reflect their detected community
