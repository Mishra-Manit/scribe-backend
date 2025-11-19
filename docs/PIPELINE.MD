
### 4-Step Email Generation Pipeline

#### Architecture Pattern
- **Stateless Design:** `PipelineData` lives in-memory during execution
- **Sequential Execution:** Steps run in order (no parallelization)
- **Progress Callbacks:** Real-time Celery task state updates
- **Observability:** Every step traced in Logfire with timings

#### Step 1: Template Parser (~1.2s)

**Responsibilities:**
- Extract search terms from template + recipient info
- Classify template type (RESEARCH/BOOK/GENERAL)
- Identify placeholders ({{name}}, {{research}}, etc.)

**Model:** Claude Haiku 4.5 (fast, structured output)
**Temperature:** 0.1 (consistent classification)

**Input:**
```python
email_template = "Hi {{name}}, I saw your work on {{research}}..."
recipient_name = "Dr. Jane Smith"
recipient_interest = "machine learning for healthcare"
```

**Output (Pydantic Model):**
```python
{
  "search_terms": ["Dr. Jane Smith machine learning healthcare"],
  "template_type": "RESEARCH",
  "placeholders": ["name", "research"],
  "confidence": 0.95
}
```

**Updates PipelineData:**
- `search_terms: List[str]`
- `template_type: TemplateType`
- `template_analysis: Dict[str, Any]`

#### Step 2: Web Scraper (~5.3s)

**Responsibilities:**
- Google Custom Search API (2 results per query)
- Playwright scraping (headless Chromium)
- Content cleaning and deduplication
- Two-tier summarization with anti-hallucination logic

**Models Used:**
- **Batch Summarization:** Claude Haiku 4.5 (per-page extraction)
- **Final Synthesis:** Claude Haiku 4.5 (COT reasoning, fact verification)

**Configuration:**
```python
max_concurrent_scrapes = 1  # Memory constrained (512MB RAM)
scrape_timeout = 10.0  # seconds
max_pages_to_scrape = 5
final_max_output_chars = 3000
```

**Anti-Hallucination Features:**
- Multi-source verification
- Uncertainty markers: `[UNCERTAIN]`, `[SINGLE SOURCE]`
- Zero temperature for factual extraction
- Chain-of-thought reasoning in prompts

**Workflow:**
1. Google Search → Get URLs
2. Playwright → Scrape HTML (sequential for memory)
3. BeautifulSoup → Clean and extract text
4. Claude Haiku → Summarize each page (batch)
5. Claude Haiku → Synthesize final summary with COT

**Updates PipelineData:**
- `scraped_content: str` (max 3000 chars)
- `scraped_urls: List[str]`
- `scraped_page_contents: Dict[str, str]`
- `scraping_metadata: Dict[str, Any]`

#### Step 3: ArXiv Helper (~0.8s)

**Responsibilities:**
- **Conditional Execution:** Only runs if `template_type == RESEARCH`
- Fetch academic papers by recipient name
- Extract: title, authors, abstract, published_date, arxiv_url

**Configuration:**
```python
max_papers = 5  # Most relevant papers
non_fatal = True  # Pipeline continues on error
```

**Workflow:**
1. Query ArXiv API with recipient name
2. Parse XML response
3. Extract paper metadata
4. Filter for relevance and recency

**Updates PipelineData:**
- `arxiv_papers: List[Dict[str, Any]]`
- `enrichment_metadata: Dict[str, Any]`

**Example Output:**
```json
[
  {
    "title": "Neural Networks for Medical Diagnosis",
    "authors": ["Jane Smith", "John Doe"],
    "arxiv_url": "https://arxiv.org/abs/2401.12345",
    "published_date": "2024-01-15",
    "abstract": "We propose a novel approach to medical diagnosis..."
  }
]
```

#### Step 4: Email Composer (~3.1s)

**Responsibilities:**
- Generate final email using Claude Sonnet
- Validate email quality
- Write to PostgreSQL database
- Increment user generation count

**Model:** Claude Sonnet 4.5 (high-quality creative writing)
**Temperature:** 0.7 (creative but controlled)
**Max Retries:** 2 attempts

**Input Context:**
```python
{
  "template": "Hi {{name}}...",
  "recipient_name": "Dr. Jane Smith",
  "recipient_interest": "machine learning for healthcare",
  "scraped_content": "Dr. Smith is a professor at...",
  "arxiv_papers": [...]
}
```

**Prompt Strategy:**
- Fill template placeholders with personalized content
- Maintain professional tone
- Reference specific work or papers
- Keep email concise (200-300 words)

**Database Write (Atomic Transaction):**
```python
email = Email(
    user_id=user_id,
    recipient_name=recipient_name,
    recipient_interest=recipient_interest,
    email_message=final_email,
    template_type=template_type,
    metadata={
        "search_terms": search_terms,
        "scraped_urls": scraped_urls,
        "arxiv_papers": arxiv_papers,
        "step_timings": step_timings,
        "generation_metadata": {...}
    }
)
db.add(email)
user.generation_count += 1
db.commit()
```

**Updates PipelineData:**
- `final_email: str`
- `composition_metadata: Dict[str, Any]`
- `metadata["email_id"]: UUID` (CRITICAL for pipeline tracking)



### Celery Task Processing

#### Worker Configuration

**File:** `/pythonserver/celery_config.py`

```python
# Memory-constrained settings for 512MB Render instance
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 100
worker_concurrency = 1  # Only 1 worker
task_acks_late = True
task_reject_on_worker_lost = True

# Queues
task_queues = [
    Queue('email_default', routing_key='email.default'),
    Queue('email_high', routing_key='email.high'),  # Reserved for premium
    Queue('celery', routing_key='celery.default'),  # Health checks
]
```

#### Redis Configuration

```python
broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/1'  # Separate DB
result_serializer = 'json'
task_serializer = 'json'
accept_content = ['json', 'pickle']  # pickle for exceptions
result_expires = 3600  # 1 hour TTL
```

#### Task Definition

**File:** `/pythonserver/tasks/email_tasks.py`

```python
@celery_app.task(bind=True, name='tasks.generate_email')
def generate_email_task(
    self,
    user_id: str,
    email_template: str,
    recipient_name: str,
    recipient_interest: str,
    template_type: str,
    public_task_id: str
):
    # Update task state with progress
    self.update_state(
        state='STARTED',
        meta={
            'current_step': 'template_parser',
            'step_status': 'started',
            'step_timings': {}
        }
    )

    # Execute pipeline
    pipeline = create_email_pipeline()
    result = pipeline.run(PipelineData(...))

    return {
        'email_id': result.metadata['email_id'],
        'step_timings': result.metadata['step_timings']
    }
```
