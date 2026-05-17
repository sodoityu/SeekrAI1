# Ask SRE - Semantic Search for OpenShift SRE Documentation

Intelligent semantic search over OpenShift ops-sop SRE documentation using AI-powered embeddings. Integrates with Claude, Gemini, and other AI assistants through the Model Context Protocol (MCP).

## 🎯 Overview

Ask SRE indexes the entire OpenShift ops-sop documentation repository (776+ markdown files, 8,487 searchable chunks) and provides intelligent semantic search through vector embeddings. This allows AI assistants to find relevant SRE documentation, alerts, troubleshooting guides, and best practices using natural language queries.

### Key Features

- **Semantic Search**: Find relevant documentation using natural language queries
- **Comprehensive Coverage**: Indexes 8,487+ document chunks across all ops-sop categories
- **ROSA KCS Integration**: Search official Red Hat Customer Portal KCS solutions
- **Managed OpenShift Docs**: Search official ROSA/OSD/HCP documentation from GitHub
- **Rich Metadata**: Results include file paths, categories, severity, service names, code blocks, and more
- **MCP Compatible**: Works with Claude Desktop, Gemini CLI, and other MCP clients
- **Fast & Local**: All processing happens locally with no external API calls required

### Documentation Sources

Ask SRE provides a **unified search** across multiple documentation sources through the `search_sre_docs` tool. Results from all sources are combined and ranked by semantic similarity:

1. **Local ops-sop Documentation**
   - Internal SRE runbooks, alerts, and troubleshooting guides
   - 8,487+ document chunks from 776+ markdown files
   - Hypershift, v4, security, best practices, and more
   - Source identifier: `local_ops_sop`

2. **ROSA KCS Solutions** (optional)
   - Official Red Hat Knowledge Centered Service (KCS) solutions
   - Verified solutions from Red Hat support engineers
   - Installation, security, troubleshooting, and configuration guides
   - Source identifier: `redhat_customer_portal`
   - See [REDHAT_API_EMBEDDINGS.md](REDHAT_API_EMBEDDINGS.md) for setup

3. **Managed OpenShift Documentation** (optional)
   - Official ROSA (Red Hat OpenShift Service on AWS) documentation
   - OSD (OpenShift Dedicated) documentation
   - HCP (Hosted Control Planes) documentation
   - Architecture guides, cluster administration, installation guides
   - Sourced from https://github.com/openshift/openshift-docs
   - Source identifier: `managed_openshift_docs`

All results include a `source` field to identify their origin, allowing AI assistants to distinguish between internal ops-sop, official ROSA KCS, and managed OpenShift documentation.


## 📚 Documentation

**New to Ask SRE?** Check out the comprehensive documentation:

👉 **[Getting Started Guide](docs/GETTING_STARTED.md)** - Complete setup and testing guide (~30 minutes)

### Additional Documentation

- **[Embeddings Setup](docs/EMBEDDINGS_SETUP.md)** - Detailed embeddings database setup
- **[Metadata Reference](docs/METADATA_REFERENCE.md)** - Metadata schema and structure
- **[Evaluation System](docs/EVALUATION_SYSTEM.md)** - Complete RAG evaluation architecture
- **[CI Setup](docs/CI_SETUP.md)** - Continuous integration configuration
- **[Documentation Index](docs/README.md)** - Complete documentation index

## 📋 Prerequisites

- Python 3.13 or higher
- Poetry (Python package manager)
- Git
- ~1GB disk space for models and database

## Evaluation and testing

The `ask-sre` command includes the capability to evaluate the RAG system quality using **Claude Agent SDK** (response generator) and **OpenAI GPT-4** (LLM judge). 

**Architecture**: The evaluation uses a two-phase approach:
1. **Phase 1** - Claude Agent SDK queries each question, calls `search_sre_docs` MCP tool, and generates answers
2. **Phase 2** - OpenAI evaluates responses using three metrics via the Ragas framework:
   - [Answer Accuracy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/#answer-accuracy) - How well the response matches the reference
   - [Context Relevance](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/#context-relevance) - How relevant retrieved docs are
   - [Response Groundedness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/#response-groundedness) - Whether the response is supported by docs

📖 **See [Evaluation System Documentation](docs/EVALUATION_SYSTEM.md) for complete architecture and usage guide**

You can run the evaluation suite using the included Golden Dataset with the following command:

```bash
ask-sre evaluate --golden-dataset data/golden.jsonl --output out/result.json
```

## Compare Embedding Model Performance
| Model |Vector Size |Index Time | NaiveRAG || **MiniRAG** | |
|-------|----------|----------|----------|----------|----------|----------|
| | | | acc↑ | context↑ |  acc↑ | context↑ |
| all-MiniLM-L6-v2 | 384 | 7min | 0.7188 |0.6423 |to-do |to-do |
| all-mpnet-base-v2 | 768 | 16min | 0.7432 | 0.7011 | to-do | to-do |
| sentence-t5-base |768 | 24min | 0.7969 | 0.8125 | to-do | to-do |
| Qwen3-Embedding-0.6B |1024 |  |  |  | to-do | to-do |
| Qwen3-Embedding-4B |2560 |  |  |  | to-do | to-do |

Answer Accuracy Metrics : https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/#answer-accuracy 
```
0 → The response is inaccurate or does not address the same question as the reference.
2 → The response partially align with the reference.
4 → The response exactly aligns with the reference.
```

Context Relevance Metrics https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/nvidia_metrics/#context-relevance
```
0 → The retrieved contexts are not relevant to the user's query at all.
1 → The contexts are partially relevant.
2 → The contexts are completely relevant.
```
# Trigger Konflux build
# Test with fixed secret
# Test after PaC config merge
# Pipeline configured
