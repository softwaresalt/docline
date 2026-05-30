# **Document Ingestion and Schema Validation Pipeline**

## **1\. Executive Summary**

This document outlines the architecture and implementation plan for a dual-interface MCP (Model Context Protocol) server and CLI pipeline. It is designed to ingest heterogeneous, unstructured documents (PDF, DOCX, VTT transcripts, recursive HTML websites, raw text), convert them into highly structured Markdown, and enforce strict semantic and AST (Abstract Syntax Tree) schemas.

By outputting predictable, lint-validated Markdown accompanied by a global ingestion manifest, this tool acts as a consumer-agnostic data normalization layer. It is the crucial precursor step for preparing content for advanced RAG (Retrieval-Augmented Generation) systems, agentic memory servers (like graphtor-docs), and graph databases (like Cozo or Neo4j).

**The Core Philosophy:**

Modern RAG and Graph systems fundamentally fail when fed unpredictable, noisy data. Traditional chunking strategies destroy semantic context. LLM hallucinations are highly correlated with poorly formatted input context. This pipeline guarantees that any downstream consumer receives a strictly typed, uniform dataset, regardless of whether the original source was a polished PDF whitepaper, a messy Zoom transcript, or a heavily stylized HTML documentation site. By moving validation to the ingestion phase, we drastically reduce the computational overhead and error rates during the retrieval and generation phases.

## **2\. Core Architecture & Tech Stack**

This solution operates simultaneously as a standalone CLI tool for local CI/CD pipelines and a persistent MCP server. This dual nature requires 100% parity between CLI commands and MCP exposed tools.

* **Multi-Modal Ingestion Router:** A custom Python orchestration module that inspects input signatures (MIME types, file extensions, URL patterns) and dynamically routes them to the appropriate extraction engine.  
* **Extraction Engines (The "Readers"):** \* *docling (IBM):* For physical layout analysis of PDFs/DOCX, extracting bounding boxes and tables.  
  * *yt-dlp / webvtt-py:* For scraping media metadata and parsing transcript files.  
  * *Trafilatura \+ Turndown (Python ports):* For asynchronous HTML crawling and extraction.  
* **Schema Definition & Enforcement:** Pydantic (Python)  
  * Provides strict runtime typing, validation, and automated JSON Schema generation for frontmatter and AST rules.  
* **AST Generation & Linting:** markdown-it-py  
  * Tokenizes the Markdown into an Abstract Syntax Tree (AST), allowing programmatic traversal to verify heading hierarchies and required sections.  
* **Agentic Orchestration & Extraction:** Fast, Context-Heavy LLMs (e.g., Gemini 2.5 Flash / Claude 3.5 Haiku)  
  * Acts as the internal routing engine, metadata extractor, and surgical structural corrector during the AST validation loop.

## **3\. The CLI/MCP Parity & Discovery Mechanism**

To ensure high resilience, the agent harness must not be completely crippled if the MCP server fails to initialize or the JSON-RPC transport layer drops. The CLI acts as the ultimate fallback.

### **The \--manifest Command**

The CLI exposes a graphtor-ingest \--manifest command. When executed, it does not run any ingestion logic. Instead, it dynamically introspects the internal Pydantic models defining the CLI arguments and outputs a complete **JSON Schema Tool Definition**.

* *Format:* The output strictly mirrors the JSON Schema array expected by LLM function-calling APIs (e.g., OpenAI's tools array or MCP's tools/list response).  
* *Utility:* If the agent harness loses MCP connectivity, it can execute the \--manifest command via standard shell execution, parse the JSON Schema, understand the required arguments for commands like crawl or extract, and fallback to executing the CLI directly via subprocess or exec.

*Example Manifest Output:*

{  
  "tools": \[  
    {  
      "name": "crawl\_website",  
      "description": "Asynchronously crawls a website and extracts main content to a local staging cache.",  
      "parameters": {  
        "type": "object",  
        "properties": {  
          "url": { "type": "string", "description": "The target URL." },  
          "depth": { "type": "integer", "description": "Recursive crawl depth." }  
        },  
        "required": \["url"\]  
      }  
    }  
  \]  
}

## **4\. The Decoupled Execution Model (Two-Stage Pipeline)**

To support batched pre-loading and prevent agent timeouts during long-running I/O operations (like deep web crawling), the pipeline's state machine is explicitly decoupled into two distinct phases that can be run independently via the CLI. This design fundamentally acknowledges that fetching distributed data across the internet operates on a fundamentally different timeline—and with a completely different risk profile—than locally executing deterministic structural validation and high-speed LLM inference.

If an agent attempts to synchronously command an entire documentation site crawl via a single RPC call, the connection will invariably sever. By decoupling these stages, we empower both autonomous agents and CI/CD pipelines to manage state, retry failures, and optimize concurrency without risking total pipeline collapse.

### **Stage 1: The I/O Bound Fetch Phase (graphtor-ingest fetch)**

This phase is purely responsible for acquiring raw data, performing the initial gross-level sanitization, and caching it locally. Crucially, no LLMs or complex validation logic are invoked in this stage. It is optimized purely for network throughput, robust error handling, and parallel execution.

* *Target Execution:* A massive documentation site (e.g., executing graphtor-ingest fetch \--url docs.example.com \--depth=5), or a directory containing hundreds of heavy PDF manuals.  
* *Process:*  
  * The Async Crawler navigates the site map, respecting robots.txt and applying exponential backoff to avoid rate limits.  
  * As pages are retrieved, it performs Main Content Extraction (MCE) to violently strip away all DOM noise—navbars, footers, ad injections, and interactive scripts.  
  * It then translates the remaining semantic HTML into raw, unvalidated Markdown, utilizing Header Normalization to prevent CSS-abused HTML tags from generating malformed AST trees later.  
  * For file-based ingestion (PDFs/DOCX), docling is invoked across multiple CPU cores to analyze bounding boxes and convert the visual layouts into text.  
* *Output:* The raw Markdown files and their accompanying source metadata (origin URL, fetch timestamp, HTTP status codes) are serialized and written to a transient .cache/staging/ directory on the local disk.  
* *Agent & Human Benefit:* The primary advantage of this decoupling is architectural resilience. An agent can trigger a massive web crawl in the background, detach from the process entirely, and execute other reasoning tasks. It can periodically poll the .cache/staging/ directory to monitor progress, returning hours later to process the data without ever holding open an expensive synchronous connection. Furthermore, data engineers can run this fetch phase overnight to build a corpus, ensuring the data is locally available for rapid iteration when tuning the Stage 2 processing models.

### **Stage 2: The Compute-Bound Processing Phase (graphtor-ingest process)**

This phase represents the core intellectual labor of the pipeline. It reads sequentially from the .cache/staging/ directory and applies the expensive AI metadata extraction and strict AST validation logic. Because the data is already local, this phase is entirely compute-bound and can be parallelized effectively across available GPU/CPU resources.

* *Process:*  
  * The Orchestrator routes the cached files to the appropriate extract\_metadata LLM skill. The LLM reads the raw Markdown and generates the mandatory JSON Schema matching the document's type, which is then converted into YAML frontmatter.  
  * The YAML and Markdown are stitched together in memory.  
  * markdown-it-py is invoked to tokenize the assembled file into an AST.  
  * The custom AST Linter traverses this tree, checking for absolute conformity to the structural rules defined in the Pydantic schema (e.g., verifying header hierarchies, asserting the existence of required sections).  
  * If the linter flags a violation, the Agentic Correction Loop is triggered. The LLM is fed the precise error report and the AST map, and is instructed to surgically inject or modify the structural markers (like adding a missing \#\# Dependencies header) without altering the core semantic text.  
* *Output:* Files that successfully pass all validation layers (or are successfully salvaged by the Agentic Correction Loop) are moved to the final, consumer-agnostic output directory (e.g., ./validated\_workspace/). The global manifest.json is atomically updated with the new ingestion records. Files that repeatedly fail validation are moved to a \_quarantine/ directory for manual human review, ensuring that bad data is strictly walled off from downstream graph databases.

## **5\. The "Schema Contract" Concept**

A valid document in this ecosystem is a strictly enforced data structure that must pass two distinct validation layers before it is allowed into the graph.

### **Layer 1: Frontmatter Validation (The Graph Edges)**

The YAML header must perfectly deserialize into a predefined Pydantic model.

* *Example Pydantic Models:* BaseDocument, ArchitectureDecisionRecord, WebArticle.

### **Layer 2: Structural Validation (The AST Rules)**

The Markdown body must conform to structural rules translated directly from the Pydantic schema.

* *Rule Examples:* "The document must begin with exactly one h1 heading." "No headers may be deeper than h4." "All tables must have a header row."

## **6\. Detailed Pipeline Workflow (End-to-End)**

### **Step 1: Input Routing & Header Normalization (Stage 1\)**

* **HTML Jettison & Translation:** During the fetch phase, tools like Turndown completely strip raw HTML tags (e.g., \<div\>, \<span\>).  
* **Header Normalization:** The converter interprets semantic HTML tags (\<h1\>-\<h6\>). *Critically, the parser maps the highest detected HTML header in the extracted block to an H1 and cascades the rest proportionately.* (e.g., If the extracted HTML block starts with an \<h3\>, it is converted to a \# rather than \#\#\# to prevent invalid AST trees).

### **Step 2: Transcript Specialized Handling (Non-Linear Data)**

* The raw transcript is passed to an LLM skill to diarize speakers, segment semantic topics via injected headers, and generate an executive summary.

### **Step 3: Metadata Extraction & YAML Generation (Stage 2\)**

* The parsed, normalized Markdown content is passed to the extract\_metadata LLM skill. The LLM maps the unstructured content into the exact JSON Schema required by the document's identified type.

### **Step 4: Markdown Assembly**

* The validated YAML frontmatter is prepended to the top of the file, followed immediately by the body content.

### **Step 5: AST Structural Linting & Agentic Correction (Stage 2\)**

* markdown-it-py parses the assembled Markdown file into a tokenized AST.  
* **The Surgical Correction Loop:** If validation fails, the AST linter generates a precise error report. The correct\_structure LLM skill is invoked via MCP to append or modify structural elements without altering the core text content. The document is re-linted or quarantined.

### **Step 6: Output & Manifest Generation**

* Valid .md files are written to a dedicated output directory.  
* **Manifest Generation:** A manifest.json file is atomically generated at the root of the output directory, acting as a "Bill of Materials" and a sequential ingestion index.

## **7\. Built-in Schema Library (Examples)**

1. **Standard\_Wiki**: Requires \# H1, followed by \#\# Overview.  
2. **Architecture\_Decision\_Record**: Requires \# Context, \#\# Proposed Solution, and strict unordered list formatting under \#\# Dependencies.  
3. **Transcript\_Meeting**: Requires \# Meeting Context, \#\# Executive Summary, and chronological dialogue under \#\#\# subheaders.  
4. **Web\_Documentation**: Requires source\_url in frontmatter and enforces a strict header hierarchy, guaranteeing that the Header Normalization step successfully resolved fragmented HTML tags into a valid tree.

## **8\. Critical Considerations for Architecture Integrity**

* **Single Source of Truth (SSOT):** The output manifest.json must **never** contain relationship data. All relationship logic must reside exclusively within the YAML frontmatter.  
* **Idempotency & Deduplication:** Every document must generate a deterministic UUID (e.g., UUIDv5 utilizing a namespace and the canonical URL). Downstream consumers must use this UUID for UPSERT operations.  
* **Crawler Traps & Timeouts:** Web crawling must be aggressively sandboxed. A strict timeout per page and a hard limit on total pages per job must be enforced.

## **9\. Implementation Plan**

### **Phase 1: Two-Stage Architecture & HTML Ingestion (Weeks 1-2)**

1. Define the base Pydantic models.  
2. Implement the CLI \--manifest JSON Schema generator.  
3. Build Stage 1: The I/O Bound Fetch phase (Async Web Crawler, MCE, and Header Normalization).

### **Phase 2: AST Validation Engine (Weeks 2-3)**

1. Implement markdown-it-py for parsing the generated Markdown into a token stream.  
2. Build Stage 2: The Compute-Bound processing phase (AST Walker converting Pydantic requirements into assertions).

### **Phase 3: MCP Server & Agentic Correction Loop (Weeks 4-5)**

1. Wrap the core Python logic into an MCP-compliant server ensuring 100% parity with the CLI schema.  
2. Implement the strict constraint prompting for the correct\_structure LLM loop.

### **Phase 4: CI/CD Integration & Tooling (Week 6\)**

1. Package the CLI tool for standalone distribution.  
2. Build a lightweight HTML/JS viewer for the \_quarantine/ directory.