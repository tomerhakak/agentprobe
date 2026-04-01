# AgentProbe — AI Agent Testing Framework
## אפיון מוצר מלא | Full Product Specification

---

## 1. חזון המוצר (Product Vision)

### שם: **AgentProbe**
### תיאור בשורה אחת:
> "pytest for AI Agents" — תוכנה לוקאלית שבודקת, מדמה, ומנטרת AI Agents בלי לשלוח שום דאטה החוצה.

### בעיה:
מפתחים בונים AI agents (עם LangChain, CrewAI, AutoGen, Claude SDK, OpenAI SDK ועוד), אבל אין להם דרך אמיתית:
- לבדוק שה-agent עובד נכון לפני deploy
- לזהות regression כשמשנים prompt או מודל
- לדמות tool calls בלי לקרוא ל-APIs אמיתיים (ויקרים)
- לבדוק עלויות, latency, ובטיחות
- לעשות replay של שיחות שנכשלו בפרודקשן

### למה לוקאלי:
- **פרטיות**: prompts, תוצאות, ודאטה של agents רגישים — חברות לא רוצות לשלוח אותם לשירות חיצוני
- **מהירות**: בדיקות רצות מיידית, בלי network latency
- **עלות**: אין subscription, אין per-seat pricing
- **אינטגרציה**: רץ ב-CI/CD pipeline לוקאלי, בתוך Docker, או על מכונת המפתח

---

## 2. קהל יעד (Target Users)

### Primary: מפתחי AI Agents
- בונים agents עם כל framework (LangChain, CrewAI, AutoGen, Claude SDK, OpenAI SDK, custom)
- צריכים לבדוק agents לפני deploy
- רגילים ל-pytest/jest ומחפשים חוויה דומה

### Secondary: צוותי ML/AI בחברות
- צריכים CI/CD pipeline עבור agents
- חייבים compliance ו-audit trail
- רוצים לנטר regression על prompts ומודלים

### Tertiary: חוקרי AI ו-red teamers
- בודקים חולשות ב-agents
- עושים adversarial testing
- צריכים לתעד ממצאים

---

## 3. ארכיטקטורה כללית (High-Level Architecture)

```
┌─────────────────────────────────────────────────────────┐
│                    AgentProbe Desktop                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │   CLI Engine │  │  Web UI      │  │  VS Code Ext   │  │
│  │   (Core)     │  │  (Dashboard) │  │  (Optional)    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                 │                   │           │
│  ┌──────▼─────────────────▼───────────────────▼────────┐ │
│  │              AgentProbe Core Engine                   │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │
│  │  │ Recorder │ │ Replayer │ │ Asserter │ │ Mocker │ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │
│  │  │ Analyzer │ │ Reporter │ │ Diffing  │ │ Fuzzer │ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────▼──────────────────────────────┐ │
│  │              Storage Layer (SQLite + Files)          │ │
│  │  ┌───────────┐ ┌────────────┐ ┌──────────────────┐ │ │
│  │  │ Test Runs │ │ Recordings │ │ Snapshots/Traces │ │ │
│  │  └───────────┘ └────────────┘ └──────────────────┘ │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           Plugin / Adapter Layer                     │ │
│  │  ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────────┐ │ │
│  │  │LangChain│ │ CrewAI │ │ OpenAI │ │ Claude SDK │ │ │
│  │  ├─────────┤ ├────────┤ ├────────┤ ├────────────┤ │ │
│  │  │AutoGen  │ │ Custom │ │  MCP   │ │  Haystack  │ │ │
│  │  └─────────┘ └────────┘ └────────┘ └────────────┘ │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 4. מודולים מפורטים (Detailed Modules)

---

### 4.1 Recorder — הקלטת ריצות Agent

**מטרה:** לתפוס כל מה שקורה כש-agent רץ — כל LLM call, כל tool call, כל החלטה.

#### איך זה עובד:
1. המשתמש מוסיף decorator/wrapper לקוד ה-agent שלו
2. AgentProbe מיירט (intercept) את כל הקריאות ושומר אותן
3. התוצאה: קובץ `.aprobe` (JSON-based) עם כל ה-trace

#### מה נתפס בכל recording:

```typescript
interface AgentRecording {
  id: string;                    // unique recording ID
  metadata: {
    name: string;                // user-defined name
    timestamp: string;           // ISO 8601
    duration_ms: number;         // total execution time
    agent_framework: string;     // "langchain" | "crewai" | "openai" | etc.
    agent_version: string;       // version of user's agent code
    total_cost_usd: number;      // total LLM API cost
    total_tokens: number;        // total tokens used
    tags: string[];              // user-defined tags
  };

  // Input that started the agent
  input: {
    type: "text" | "structured" | "multimodal";
    content: any;                // the actual input
    context?: Record<string, any>; // additional context provided
  };

  // Final output of the agent
  output: {
    type: "text" | "structured" | "multimodal";
    content: any;
    status: "success" | "error" | "timeout" | "cancelled";
    error?: string;
  };

  // Every step the agent took
  steps: AgentStep[];

  // Full conversation/message history
  messages: Message[];

  // Environment snapshot
  environment: {
    model: string;               // "claude-sonnet-4-6", "gpt-4o", etc.
    model_params: {
      temperature: number;
      max_tokens: number;
      top_p?: number;
      [key: string]: any;
    };
    system_prompt?: string;
    tools_available: ToolDefinition[];
    env_vars_hash: string;       // hash of relevant env vars (not values!)
  };
}

interface AgentStep {
  step_number: number;
  type: "llm_call" | "tool_call" | "tool_result" | "decision" | "handoff" | "memory_read" | "memory_write";
  timestamp: string;
  duration_ms: number;

  // For LLM calls
  llm_call?: {
    model: string;
    input_messages: Message[];
    output_message: Message;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    latency_ms: number;
    cache_hit: boolean;
    finish_reason: string;       // "stop" | "tool_use" | "length" | etc.
  };

  // For tool calls
  tool_call?: {
    tool_name: string;
    tool_input: any;
    tool_output: any;
    duration_ms: number;
    success: boolean;
    error?: string;
    side_effects?: string[];     // ["wrote_file:/tmp/x.txt", "http_request:api.example.com"]
  };

  // For agent decisions
  decision?: {
    type: "route" | "retry" | "delegate" | "stop";
    reason: string;
    alternatives_considered?: string[];
  };
}

interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string | ContentBlock[];
  name?: string;
  tool_call_id?: string;
  timestamp: string;
  tokens?: number;
}
```

#### Python SDK לrecording:

```python
from agentprobe import record, AgentProbe

# Option 1: Decorator
@record(name="customer-support-agent")
def run_my_agent(user_input: str):
    agent = MyAgent()
    return agent.run(user_input)

# Option 2: Context manager
with AgentProbe.record(name="customer-support-agent") as session:
    agent = MyAgent()
    result = agent.run("How do I reset my password?")
    session.set_output(result)

# Option 3: Auto-instrument (monkey-patching)
import agentprobe
agentprobe.auto_instrument()  # patches openai, anthropic, langchain, etc.

agent = MyAgent()
result = agent.run("How do I reset my password?")
# Recording saved automatically to .agentprobe/recordings/
```

#### Framework-Specific Adapters:

```python
# LangChain
from agentprobe.adapters.langchain import AgentProbeCallbackHandler
agent.run(input, callbacks=[AgentProbeCallbackHandler()])

# CrewAI
from agentprobe.adapters.crewai import instrument_crew
instrument_crew(my_crew)
my_crew.kickoff()

# OpenAI SDK
from agentprobe.adapters.openai import patch_openai
patch_openai()  # patches openai.ChatCompletion.create etc.

# Anthropic/Claude SDK
from agentprobe.adapters.anthropic import patch_anthropic
patch_anthropic()

# MCP
from agentprobe.adapters.mcp import instrument_mcp_server
instrument_mcp_server(server)
```

#### Storage:
- Recordings שמורים ב-`.agentprobe/recordings/` בתיקייה של הפרויקט
- כל recording = קובץ `.aprobe` (gzipped JSON)
- אינדקס ב-SQLite: `.agentprobe/index.db`
- ניתן לexport ל-JSON/YAML/Parquet

---

### 4.2 Replayer — הרצה מחדש של recordings

**מטרה:** לקחת recording קיים ולהריץ אותו מחדש — עם מודל חדש, prompt חדש, או tools חדשים — ולהשוות תוצאות.

#### Use Cases:
1. **Model Migration**: שדרגתי מ-GPT-4 ל-Claude? בוא נבדוק שכל ה-recordings עדיין עובדים
2. **Prompt Change**: שיניתי system prompt? בוא נריץ מחדש ונשווה
3. **Regression Detection**: בניתי גרסה חדשה של ה-agent? נבדוק מול recordings ישנים
4. **Cost Optimization**: בוא נבדוק אם מודל זול יותר נותן תוצאות מספיק טובות

#### API:

```python
from agentprobe import Replayer, ReplayConfig

replayer = Replayer()

# Replay with different model
result = replayer.replay(
    recording="recordings/customer-support-001.aprobe",
    config=ReplayConfig(
        # Override model
        model="claude-haiku-4-5-20251001",  # was claude-sonnet originally

        # Override system prompt
        system_prompt="You are a helpful customer support agent. Be concise.",

        # Mock tool calls (don't actually call real APIs)
        mock_tools=True,

        # Use recorded tool outputs as mock responses
        use_recorded_tool_outputs=True,

        # Or provide custom mock responses
        tool_mocks={
            "search_knowledge_base": lambda input: {
                "results": [{"title": "Password Reset", "content": "..."}]
            }
        },

        # Timeout per step
        step_timeout_ms=30000,

        # Max cost for this replay
        max_cost_usd=0.50,
    )
)

# Compare with original
comparison = replayer.compare(
    original="recordings/customer-support-001.aprobe",
    replayed=result,
)

print(comparison.summary)
# Output:
# ┌─────────────────────────────────────────┐
# │ Replay Comparison Summary               │
# ├─────────────────────────────────────────┤
# │ Steps: 5 → 4 (1 fewer)                 │
# │ Final output: 87% semantic similarity   │
# │ Cost: $0.032 → $0.008 (75% cheaper)    │
# │ Latency: 3.2s → 1.1s (66% faster)      │
# │ Tools called: same set                  │
# │ Behavior drift: LOW                     │
# │ ⚠️  Missing step: knowledge_base_search │
# └─────────────────────────────────────────┘
```

#### Replay Modes:

| מצב | תיאור |
|-----|--------|
| `full_replay` | מריץ את כל ה-agent מחדש עם input מקורי |
| `step_replay` | מריץ צעד-צעד, מאפשר להחליף צעדים ספציפיים |
| `fork_replay` | מריץ מחדש מצעד מסוים והלאה (forking) |
| `dry_replay` | מחשב cost/token estimate בלי להריץ בפועל |
| `mock_replay` | כל ה-LLM calls ממוקים, רק logic של ה-agent רץ |

---

### 4.3 Asserter — בדיקות ו-assertions

**מטרה:** להגדיר ולבדוק ציפיות על התנהגות ה-agent — כמו assertions ב-pytest, אבל מותאם ל-AI.

#### סוגי Assertions:

```python
from agentprobe import test, assertions as A

@test(recording="recordings/customer-support-001.aprobe")
def test_customer_support_basic():
    """Test that the agent handles password reset correctly."""

    # === Output Assertions ===

    # Semantic similarity (uses local embedding model)
    A.output_similar_to(
        "To reset your password, go to Settings > Security > Reset Password",
        threshold=0.8  # cosine similarity threshold
    )

    # Contains specific information
    A.output_contains("password")
    A.output_contains_any(["reset", "change", "update"])
    A.output_not_contains("I don't know")

    # Regex matching
    A.output_matches(r"https?://\S+")  # contains a URL

    # JSON structure (for structured outputs)
    A.output_json_matches({
        "action": "password_reset",
        "url": A.any_string(),
        "steps": A.list_of(A.any_string(), min_length=2)
    })

    # === Behavioral Assertions ===

    # Tool usage
    A.called_tool("search_knowledge_base")
    A.called_tool("search_knowledge_base", times=1)
    A.not_called_tool("send_email")  # shouldn't send email for a question
    A.called_tools_in_order(["search_knowledge_base", "format_response"])

    # Tool input validation
    A.tool_called_with("search_knowledge_base", {
        "query": A.contains("password"),
        "limit": A.less_than(20)
    })

    # Step count
    A.steps_less_than(10)  # shouldn't take more than 10 steps
    A.steps_between(2, 8)

    # No infinite loops
    A.no_repeated_tool_calls(max_repeats=3)

    # === Performance Assertions ===

    # Cost
    A.total_cost_less_than(0.05)  # less than 5 cents
    A.cost_per_step_less_than(0.02)

    # Latency
    A.total_latency_less_than(5000)  # less than 5 seconds
    A.step_latency_less_than(3000)   # no single step > 3 seconds

    # Tokens
    A.total_tokens_less_than(5000)
    A.output_tokens_less_than(500)   # concise responses

    # === Safety Assertions ===

    # No harmful content (uses local classifier)
    A.output_safe()  # runs local toxicity/harm classifier

    # No data leakage
    A.output_not_contains_any(SENSITIVE_PATTERNS)  # SSN, credit card, etc.
    A.no_pii_in_output()  # local PII detector

    # Stays in scope
    A.output_relevant_to(input_text, threshold=0.6)

    # No hallucinated URLs/references
    A.all_urls_valid()  # checks URL format, optionally pings
    A.no_hallucinated_citations()

    # === LLM-as-Judge Assertions (local model) ===

    # Uses a local LLM (e.g., Llama/Mistral via Ollama) to judge
    A.llm_judge(
        criteria="The response should be helpful, accurate, and concise",
        min_score=7,  # out of 10
        model="ollama:llama3.2"  # runs locally!
    )

    A.llm_judge_comparative(
        baseline="recordings/customer-support-baseline.aprobe",
        criteria="Is the new response better or equal to the baseline?",
        model="ollama:llama3.2"
    )
```

#### Test Discovery & Execution:

```bash
# Run all tests
agentprobe test

# Run specific test file
agentprobe test tests/test_customer_support.py

# Run with specific tag
agentprobe test --tag "regression"

# Run and generate report
agentprobe test --report html

# Run in CI mode (exit code = number of failures)
agentprobe test --ci

# Run with cost limit (abort if total cost exceeds)
agentprobe test --max-cost 5.00

# Parallel execution
agentprobe test --parallel 4
```

#### Test File Structure:

```
my-agent-project/
├── agent/
│   ├── main.py
│   └── tools.py
├── tests/
│   └── agentprobe/
│       ├── test_basic_flows.py
│       ├── test_edge_cases.py
│       ├── test_safety.py
│       ├── test_performance.py
│       └── test_regression.py
├── .agentprobe/
│   ├── config.yaml
│   ├── index.db
│   ├── recordings/
│   │   ├── customer-support-001.aprobe
│   │   ├── customer-support-002.aprobe
│   │   └── ...
│   ├── snapshots/
│   │   └── baseline-v1.0.snapshot
│   └── reports/
│       └── 2026-04-01-regression.html
└── agentprobe.yaml              # project config
```

---

### 4.4 Mocker — Mock System for Tools & LLMs

**מטרה:** לאפשר הרצת בדיקות בלי לקרוא ל-APIs אמיתיים — חוסך כסף, מהיר, ודטרמיניסטי.

#### Tool Mocking:

```python
from agentprobe.mock import MockTool, MockToolkit, recorded_responses

# Option 1: Static mock
mock_search = MockTool(
    name="search_knowledge_base",
    responses=[
        {
            "match": {"query": lambda q: "password" in q},
            "response": {"results": [{"title": "Password Reset Guide", "content": "..."}]}
        },
        {
            "match": "default",
            "response": {"results": []}
        }
    ]
)

# Option 2: From recording (use real responses captured previously)
mock_search = MockTool.from_recording(
    recording="recordings/customer-support-001.aprobe",
    tool_name="search_knowledge_base"
)

# Option 3: Sequence (return different responses on each call)
mock_search = MockTool.sequence(
    name="search_knowledge_base",
    responses=[
        {"results": [{"title": "First result"}]},
        {"results": []},  # second call returns empty
    ]
)

# Option 4: Function mock
mock_search = MockTool.function(
    name="search_knowledge_base",
    handler=lambda input: my_fake_search(input["query"])
)

# Use in tests
@test(mocks=[mock_search])
def test_with_mocked_search():
    agent = MyAgent()
    result = agent.run("How do I reset my password?")
    A.output_contains("password")
```

#### LLM Mocking:

```python
from agentprobe.mock import MockLLM

# Option 1: From recording (replay exact LLM responses)
mock_llm = MockLLM.from_recording("recordings/customer-support-001.aprobe")

# Option 2: Use local model instead of API
mock_llm = MockLLM.local(model="ollama:llama3.2")

# Option 3: Deterministic responses
mock_llm = MockLLM.scripted([
    "I'll help you reset your password. Let me search our knowledge base.",
    "Based on the results, here's how to reset your password: ...",
])

# Option 4: Echo (returns input as output — for testing agent logic only)
mock_llm = MockLLM.echo()

@test(llm=mock_llm)
def test_agent_logic_only():
    """Test agent's routing/logic without real LLM calls."""
    agent = MyAgent()
    result = agent.run("Reset my password")
    A.called_tool("search_knowledge_base")
```

---

### 4.5 Analyzer — ניתוח מעמיק

**מטרה:** ניתוח אוטומטי של recordings, trends, anomalies, ובעיות.

#### Built-in Analyzers:

```python
from agentprobe import Analyzer

analyzer = Analyzer()

# === Cost Analysis ===
cost_report = analyzer.cost_analysis(
    recordings="recordings/*.aprobe",
    group_by="model"  # or "tool", "date", "tag"
)
# Output:
# Model              | Avg Cost | Total Cost | Calls | Avg Tokens
# claude-sonnet-4-6  | $0.032   | $3.20      | 100   | 2,340
# gpt-4o             | $0.028   | $1.40      | 50    | 1,890
# claude-haiku-4-5   | $0.004   | $0.20      | 50    | 1,200

# === Latency Analysis ===
latency_report = analyzer.latency_analysis(
    recordings="recordings/*.aprobe",
    percentiles=[50, 90, 95, 99]
)

# === Behavior Drift Detection ===
drift_report = analyzer.detect_drift(
    baseline="snapshots/baseline-v1.0.snapshot",
    current="recordings/2026-04-*.aprobe",
    dimensions=["output_similarity", "tool_usage", "step_count", "cost"]
)
# Output:
# ⚠️  Drift detected:
# - Output similarity dropped from 0.92 → 0.78 (threshold: 0.85)
# - Average step count increased from 4.2 → 6.8
# - Tool "search_knowledge_base" called 40% less frequently

# === Failure Analysis ===
failure_report = analyzer.failure_analysis(
    recordings="recordings/*.aprobe",
    classify=True  # use local model to classify failure types
)
# Output:
# Failure Type          | Count | %    | Example
# timeout               | 12    | 40%  | recording-042.aprobe
# tool_error            | 8     | 27%  | recording-018.aprobe
# hallucination         | 5     | 17%  | recording-055.aprobe
# infinite_loop         | 3     | 10%  | recording-031.aprobe
# wrong_tool_selection  | 2     | 7%   | recording-067.aprobe

# === Token Waste Analysis ===
waste_report = analyzer.token_waste(
    recordings="recordings/*.aprobe"
)
# Output:
# 🔍 Token waste detected:
# - System prompt repeated in 34% of multi-turn conversations (waste: ~12,000 tokens)
# - Tool descriptions sent but never used in 28% of calls
# - Average 340 tokens of "thinking" text before tool calls (could use streaming)

# === Comparative Analysis ===
comparison = analyzer.compare_runs(
    run_a="recordings/v1.0/*.aprobe",
    run_b="recordings/v1.1/*.aprobe",
    dimensions="all"
)
```

---

### 4.6 Fuzzer — Adversarial & Edge Case Testing

**מטרה:** לייצר אוטומטית inputs קשים, adversarial, ו-edge cases כדי לבדוק robustness.

#### Built-in Fuzz Strategies:

```python
from agentprobe.fuzz import Fuzzer, strategies

fuzzer = Fuzzer(agent=MyAgent())

# === Prompt Injection Testing ===
results = fuzzer.run(
    base_input="How do I reset my password?",
    strategy=strategies.PromptInjection(
        techniques=[
            "ignore_instructions",    # "Ignore previous instructions and..."
            "role_play",              # "Pretend you are a different AI..."
            "delimiter_escape",       # Using special chars to escape context
            "indirect_injection",     # Hidden instructions in tool outputs
            "multi_language",         # Injection in other languages
            "encoding_bypass",        # Base64, ROT13, etc.
        ],
        num_variants=50,
    ),
    assertions=[
        A.output_safe(),
        A.output_not_contains("I am now"),
        A.output_relevant_to("password reset"),
    ]
)

# === Edge Case Generation ===
results = fuzzer.run(
    base_input="How do I reset my password?",
    strategy=strategies.EdgeCases(
        techniques=[
            "empty_input",           # ""
            "very_long_input",       # 100K characters
            "unicode_special",       # Emojis, RTL, zero-width chars
            "repeated_input",        # Same request 100 times
            "contradictory_input",   # "Reset my password but don't change anything"
            "ambiguous_input",       # "Do the thing with the stuff"
            "multilingual_input",    # Mix of languages
            "typos_and_noise",       # Misspellings, random chars
            "sql_injection",         # SQL patterns in input
            "xss_patterns",          # HTML/JS patterns in input
        ]
    )
)

# === Tool Failure Simulation ===
results = fuzzer.run(
    base_input="How do I reset my password?",
    strategy=strategies.ToolFailures(
        techniques=[
            "timeout",               # Tool takes forever
            "error_500",             # Tool returns server error
            "empty_response",        # Tool returns nothing
            "malformed_response",    # Tool returns invalid JSON
            "partial_response",      # Tool returns incomplete data
            "rate_limited",          # Tool returns 429
            "intermittent_failure",  # Tool fails randomly 50% of time
        ]
    ),
    assertions=[
        A.output_not_contains("error"),
        A.graceful_degradation(),    # Agent handles failure gracefully
    ]
)

# === Behavioral Boundary Testing ===
results = fuzzer.run(
    strategy=strategies.BoundaryTesting(
        scope="customer_support",    # What the agent SHOULD do
        out_of_scope=[               # What it should NOT do
            "Write code",
            "Give medical advice",
            "Share personal opinions",
            "Discuss competitors",
        ],
        num_variants=30,
    ),
    assertions=[
        A.stays_in_scope("customer_support"),
        A.polite_refusal_when_out_of_scope(),
    ]
)
```

---

### 4.7 Reporter — דוחות ותוצאות

**מטרה:** לייצר דוחות ויזואליים ומפורטים של תוצאות בדיקות.

#### Report Formats:

```bash
# Terminal report (default)
agentprobe test
# Output:
# AgentProbe Test Results
# ══════════════════════════════════════════
# ✅ test_basic_flows.py::test_password_reset       PASS  (1.2s, $0.03)
# ✅ test_basic_flows.py::test_account_info          PASS  (0.8s, $0.02)
# ❌ test_edge_cases.py::test_empty_input            FAIL  (0.3s, $0.01)
#    └─ AssertionError: output_not_contains("I don't know")
# ⚠️  test_safety.py::test_prompt_injection_basic    WARN  (2.1s, $0.05)
#    └─ 2/50 injection attempts succeeded
# ✅ test_performance.py::test_latency               PASS  (4.5s, $0.12)
# ──────────────────────────────────────────
# 3 passed, 1 failed, 1 warning
# Total cost: $0.23 | Total time: 8.9s

# HTML report
agentprobe test --report html --output reports/

# JSON report (for CI/CD)
agentprobe test --report json --output reports/results.json

# Markdown report (for PRs)
agentprobe test --report markdown --output reports/results.md
```

#### HTML Dashboard (Local Web UI):

```bash
# Start local dashboard
agentprobe dashboard
# Opens http://localhost:9847
```

**Dashboard Pages:**

1. **Overview**: סטטוס כללי, trends, alerts
2. **Test Runs**: היסטוריית ריצות, pass/fail rates
3. **Recordings Browser**: צפייה ב-recordings, חיפוש, סינון
4. **Trace Viewer**: צפייה step-by-step ב-agent trace (כמו debugger)
5. **Cost Dashboard**: עלויות לפי מודל/tool/זמן/tag
6. **Drift Monitor**: השוואה בין גרסאות, trend lines
7. **Fuzz Results**: תוצאות adversarial testing, חולשות שנמצאו
8. **Comparison View**: side-by-side של שתי ריצות

---

### 4.8 Snapshot System — Baselines & Regression

**מטרה:** לשמור "תמונת מצב" של התנהגות Agent כ-baseline, ולזהות regression.

```python
from agentprobe import Snapshot

# Create baseline snapshot from recordings
snapshot = Snapshot.create(
    name="v1.0-baseline",
    recordings="recordings/release-v1.0/*.aprobe",
    metrics=[
        "output_embeddings",      # semantic fingerprint of outputs
        "tool_usage_patterns",    # which tools, how often, in what order
        "step_count_distribution",# distribution of step counts
        "cost_distribution",      # distribution of costs
        "latency_distribution",   # distribution of latencies
        "error_rate",             # % of failures
    ]
)
snapshot.save("snapshots/v1.0-baseline.snapshot")

# Compare new run against baseline
regression = Snapshot.check_regression(
    baseline="snapshots/v1.0-baseline.snapshot",
    current="recordings/release-v1.1/*.aprobe",
    thresholds={
        "output_similarity": 0.85,    # outputs should be ≥85% similar
        "cost_increase": 0.20,         # cost shouldn't increase >20%
        "latency_increase": 0.30,      # latency shouldn't increase >30%
        "error_rate_increase": 0.05,   # error rate shouldn't increase >5%
        "step_count_increase": 0.25,   # steps shouldn't increase >25%
    }
)

if regression.has_regression:
    print(regression.report)
    exit(1)  # fail CI
```

---

## 5. CLI — Command Line Interface

```bash
# ══════════════════════════════════════════
# INSTALLATION
# ══════════════════════════════════════════

# Via pip
pip install agentprobe

# Via Homebrew (macOS/Linux)
brew install agentprobe

# Via npm (for JS/TS agent developers)
npm install -g agentprobe

# ══════════════════════════════════════════
# INITIALIZATION
# ══════════════════════════════════════════

# Initialize AgentProbe in current project
agentprobe init
# Creates:
# .agentprobe/
#   config.yaml
#   index.db
# agentprobe.yaml
# tests/agentprobe/
#   test_example.py

# Interactive setup
agentprobe init --interactive
# Asks: What framework? What model? etc.

# ══════════════════════════════════════════
# RECORDING
# ══════════════════════════════════════════

# Record a single run
agentprobe record "python agent.py 'How do I reset my password?'"

# Record with name and tags
agentprobe record --name "password-reset" --tags "support,basic" "python agent.py 'Reset password'"

# Record in watch mode (records every run automatically)
agentprobe record --watch "python agent.py"

# List recordings
agentprobe recordings list
agentprobe recordings list --tag "support"
agentprobe recordings list --after "2026-03-01"

# Inspect a recording
agentprobe recordings inspect recording-001.aprobe

# Export recording
agentprobe recordings export recording-001.aprobe --format json

# ══════════════════════════════════════════
# TESTING
# ══════════════════════════════════════════

# Run all tests
agentprobe test

# Run specific test file
agentprobe test tests/agentprobe/test_basic.py

# Run with filter
agentprobe test -k "password"

# Run with parallel execution
agentprobe test --parallel 4

# Run with cost limit
agentprobe test --max-cost 5.00

# Run in CI mode
agentprobe test --ci --report json --output results.json

# Run and update snapshots
agentprobe test --update-snapshots

# ══════════════════════════════════════════
# REPLAY
# ══════════════════════════════════════════

# Replay a recording with different model
agentprobe replay recording-001.aprobe --model claude-haiku-4-5

# Replay with different system prompt
agentprobe replay recording-001.aprobe --system-prompt "Be more concise"

# Replay with mocked tools
agentprobe replay recording-001.aprobe --mock-tools

# Replay and compare
agentprobe replay recording-001.aprobe --model gpt-4o --compare

# Batch replay (all recordings with new model)
agentprobe replay recordings/*.aprobe --model claude-haiku-4-5 --report

# ══════════════════════════════════════════
# FUZZING
# ══════════════════════════════════════════

# Run prompt injection tests
agentprobe fuzz --strategy prompt-injection --variants 50

# Run edge case tests
agentprobe fuzz --strategy edge-cases

# Run tool failure simulation
agentprobe fuzz --strategy tool-failures

# Run all fuzz strategies
agentprobe fuzz --all --report html

# ══════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════

# Cost analysis
agentprobe analyze cost --group-by model

# Latency analysis
agentprobe analyze latency --percentiles 50,90,95,99

# Drift detection
agentprobe analyze drift --baseline snapshots/v1.0.snapshot

# Failure analysis
agentprobe analyze failures --classify

# Token waste analysis
agentprobe analyze token-waste

# Full analysis report
agentprobe analyze all --report html

# ══════════════════════════════════════════
# SNAPSHOTS
# ══════════════════════════════════════════

# Create baseline snapshot
agentprobe snapshot create --name "v1.0" --recordings "recordings/release-v1.0/*.aprobe"

# Check regression against baseline
agentprobe snapshot check --baseline snapshots/v1.0.snapshot

# List snapshots
agentprobe snapshot list

# ══════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════

# Start local web dashboard
agentprobe dashboard
# → http://localhost:9847

# Start on custom port
agentprobe dashboard --port 8080

# Start in read-only mode
agentprobe dashboard --readonly
```

---

## 6. Configuration — agentprobe.yaml

```yaml
# agentprobe.yaml — Project configuration

version: "1.0"

# Project metadata
project:
  name: "my-ai-agent"
  description: "Customer support AI agent"

# Framework detection (auto-detected if not specified)
framework: "langchain"  # or "crewai", "openai", "anthropic", "autogen", "custom"

# Default model for replays and analysis
default_model: "claude-sonnet-4-6"

# Recording settings
recording:
  # Auto-record all agent runs (when using instrumentation)
  auto_record: true

  # Storage directory (relative to project root)
  storage_dir: ".agentprobe/recordings"

  # Maximum recording size (MB)
  max_recording_size_mb: 50

  # What to capture
  capture:
    llm_calls: true
    tool_calls: true
    tool_outputs: true
    system_prompts: true
    intermediate_messages: true
    timestamps: true
    token_counts: true
    cost_estimates: true

  # Sensitive data handling
  redaction:
    enabled: true
    patterns:
      - name: "api_keys"
        regex: "(sk-|key-|token-)[a-zA-Z0-9]{20,}"
        replacement: "[REDACTED_API_KEY]"
      - name: "emails"
        regex: "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
        replacement: "[REDACTED_EMAIL]"
      - name: "ssn"
        regex: "\\d{3}-\\d{2}-\\d{4}"
        replacement: "[REDACTED_SSN]"
      - name: "credit_card"
        regex: "\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}"
        replacement: "[REDACTED_CC]"
    custom_patterns: []

# Test settings
testing:
  # Test directory
  test_dir: "tests/agentprobe"

  # Default assertions for all tests
  default_assertions:
    max_cost_per_test: 0.50        # USD
    max_latency_per_test: 30000    # ms
    max_steps: 20
    output_safety: true             # always check for harmful content

  # Parallel execution
  parallel: 2

  # Retry flaky tests
  retry_flaky: 1

  # Timeout per test (ms)
  test_timeout: 60000

# Local model settings (for LLM-as-judge and local evaluation)
local_model:
  # Provider for local inference
  provider: "ollama"  # or "llamacpp", "vllm", "none"

  # Model for evaluation/judging
  eval_model: "llama3.2:8b"

  # Model for embedding (semantic similarity)
  embedding_model: "nomic-embed-text"

  # Ollama endpoint
  ollama_url: "http://localhost:11434"

# Cost estimation
cost:
  # Custom pricing (overrides built-in)
  custom_pricing:
    "claude-sonnet-4-6":
      input_per_1k: 0.003
      output_per_1k: 0.015
    "gpt-4o":
      input_per_1k: 0.005
      output_per_1k: 0.015

# Dashboard settings
dashboard:
  port: 9847
  host: "127.0.0.1"  # local only
  auth: false          # no auth needed for local

# CI/CD integration
ci:
  # Fail CI if regression detected
  fail_on_regression: true

  # Regression thresholds
  regression_thresholds:
    output_similarity: 0.85
    cost_increase: 0.20
    latency_increase: 0.30
    error_rate_increase: 0.05

  # Report format for CI
  report_format: "json"
  report_output: "reports/agentprobe-results.json"

  # GitHub integration
  github:
    # Post results as PR comment
    pr_comment: true
    # Create check run
    check_run: true

# Plugins
plugins: []
```

---

## 7. Tech Stack — בחירות טכנולוגיות

### Core Engine:

| Component | Technology | Why |
|-----------|-----------|-----|
| **Language** | Python 3.10+ | Same language as 90% of agent frameworks |
| **CLI** | Click + Rich | Beautiful terminal output, familiar CLI patterns |
| **Storage** | SQLite (via sqlite3) | Zero-config, local, fast, proven |
| **Recording format** | gzipped JSON (.aprobe) | Human-readable, compact, versionable |
| **Embeddings** | Local via Ollama/sentence-transformers | No API calls for semantic similarity |
| **Local LLM** | Ollama integration | Widely adopted, easy to install |
| **Web Dashboard** | FastAPI + htmx + Tailwind | Lightweight, fast, no heavy JS framework |
| **Packaging** | PyPI + Homebrew + npm wrapper | Accessible from all ecosystems |
| **Testing infra** | pytest plugin architecture | Familiar to Python developers |

### Dependencies (minimal):

```
# Core (required)
click>=8.0           # CLI framework
rich>=13.0           # Terminal formatting
pyyaml>=6.0          # Config files
pydantic>=2.0        # Data models
sqlite-utils>=3.0    # SQLite wrapper
httpx>=0.25          # HTTP client (for intercepting)

# Optional
fastapi>=0.100       # Dashboard server
uvicorn>=0.23        # ASGI server
jinja2>=3.0          # HTML templates
sentence-transformers>=2.0  # Local embeddings (fallback if no Ollama)

# Framework adapters (optional, installed on demand)
agentprobe[langchain]    # pip install agentprobe[langchain]
agentprobe[crewai]       # pip install agentprobe[crewai]
agentprobe[openai]       # pip install agentprobe[openai]
agentprobe[anthropic]    # pip install agentprobe[anthropic]
```

---

## 8. Data Flow — זרימת מידע

### Recording Flow:

```
User's Agent Code
       │
       ▼
AgentProbe Interceptor (monkey-patch / callback / decorator)
       │
       ├── Captures LLM Request ──────► Redaction Engine ──► Recording Buffer
       │                                                          │
       ├── Captures LLM Response ─────► Token Counter ────► Recording Buffer
       │                                Cost Calculator          │
       │                                                          │
       ├── Captures Tool Call ────────► Side Effect ──────► Recording Buffer
       │                                Detector                  │
       │                                                          │
       └── Agent Completes ───────────────────────────────► Flush to .aprobe file
                                                                  │
                                                            Index in SQLite
```

### Test Execution Flow:

```
agentprobe test
       │
       ▼
Test Discovery (find test_*.py files)
       │
       ▼
For each test:
       │
       ├── Load recording or run agent ──► Record new execution
       │
       ├── Run assertions ──────────────► Collect results
       │   ├── Output assertions
       │   ├── Behavioral assertions
       │   ├── Performance assertions
       │   ├── Safety assertions
       │   └── LLM-as-judge assertions ──► Local model inference
       │
       └── Generate report ─────────────► Terminal / HTML / JSON / Markdown
```

---

## 9. Plugin System — הרחבות

**מטרה:** לאפשר למשתמשים ולקהילה להרחיב את AgentProbe.

### Plugin Types:

```python
# === Custom Assertion Plugin ===
from agentprobe.plugins import assertion_plugin

@assertion_plugin("domain_specific_check")
def check_medical_accuracy(output: str, recording: AgentRecording) -> AssertionResult:
    """Custom assertion for medical AI agents."""
    # Your custom logic here
    has_disclaimer = "consult a doctor" in output.lower()
    return AssertionResult(
        passed=has_disclaimer,
        message="Medical response must include disclaimer"
    )

# Usage: A.domain_specific_check()


# === Custom Analyzer Plugin ===
from agentprobe.plugins import analyzer_plugin

@analyzer_plugin("sentiment_analysis")
def analyze_sentiment(recordings: list[AgentRecording]) -> AnalysisReport:
    """Analyze sentiment of agent responses over time."""
    # Your analysis logic
    pass


# === Custom Fuzz Strategy Plugin ===
from agentprobe.plugins import fuzz_plugin

@fuzz_plugin("domain_fuzz")
class MedicalFuzzer(FuzzStrategy):
    """Generate medical edge cases."""

    def generate_variants(self, base_input: str) -> list[str]:
        return [
            f"{base_input} (I'm allergic to everything)",
            f"{base_input} (I'm pregnant)",
            f"{base_input} (I'm a child)",
            # ...
        ]


# === Custom Adapter Plugin ===
from agentprobe.plugins import adapter_plugin

@adapter_plugin("my_custom_framework")
class MyFrameworkAdapter(BaseAdapter):
    """Adapter for a custom agent framework."""

    def instrument(self, agent):
        # Monkey-patch or hook into the framework
        pass

    def on_llm_call(self, request, response):
        # Called when an LLM call is made
        pass

    def on_tool_call(self, tool_name, input, output):
        # Called when a tool is called
        pass
```

### Plugin Discovery:

```yaml
# agentprobe.yaml
plugins:
  - name: "agentprobe-medical"     # from PyPI
    version: ">=1.0"
  - name: "./plugins/my_custom"     # local directory
  - name: "git+https://github.com/user/agentprobe-plugin.git"  # from git
```

---

## 10. CI/CD Integration

### GitHub Actions:

```yaml
# .github/workflows/agent-tests.yml
name: Agent Tests

on:
  pull_request:
    paths:
      - 'agent/**'
      - 'prompts/**'
      - 'tools/**'

jobs:
  agent-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install AgentProbe
        run: pip install agentprobe[all]

      - name: Setup Ollama (for local eval)
        uses: ollama/setup-ollama@v1
        with:
          model: llama3.2:8b

      - name: Run Agent Tests
        run: agentprobe test --ci --report json --output results.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          AGENTPROBE_MAX_COST: "5.00"

      - name: Check Regression
        run: agentprobe snapshot check --baseline snapshots/main.snapshot --ci

      - name: Post Results to PR
        if: github.event_name == 'pull_request'
        uses: agentprobe/github-action@v1
        with:
          results: results.json
          comment: true
```

### GitLab CI:

```yaml
agent-tests:
  stage: test
  image: python:3.11
  script:
    - pip install agentprobe[all]
    - agentprobe test --ci --report json --output results.json
    - agentprobe snapshot check --baseline snapshots/main.snapshot --ci
  artifacts:
    reports:
      junit: results.json
```

### Pre-commit Hook:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/agentprobe/agentprobe
    rev: v1.0.0
    hooks:
      - id: agentprobe-quick
        name: AgentProbe Quick Check
        entry: agentprobe test --tag quick --ci
        language: python
        pass_filenames: false
```

---

## 11. Security & Privacy

### מודל אבטחה:

```
┌────────────────────────────────────────────────────┐
│                    AgentProbe                        │
│                                                      │
│  ✅ כל הדאטה נשמר לוקאלית בלבד                     │
│  ✅ אין שום שרת חיצוני, אין telemetry               │
│  ✅ Redaction אוטומטי של מידע רגיש                  │
│  ✅ Dashboard רץ על localhost בלבד                   │
│  ✅ Recordings מוצפנים (אופציונלי)                  │
│  ✅ .gitignore כולל .agentprobe/ כברירת מחדל        │
│  ✅ אין network calls (חוץ מ-LLM APIs שהמשתמש      │
│     כבר משתמש בהם)                                   │
│                                                      │
│  Security Features:                                  │
│  - PII detection & redaction                         │
│  - API key detection & masking                       │
│  - Recording encryption (AES-256)                    │
│  - Audit log of all AgentProbe operations            │
│  - Configurable data retention policies              │
│  - No outbound connections except user's LLM APIs    │
└────────────────────────────────────────────────────┘
```

### Redaction Engine:

```python
# Built-in redaction patterns (always active)
REDACTION_PATTERNS = {
    "api_keys": r"(sk-|key-|token-|bearer\s)[a-zA-Z0-9_-]{20,}",
    "emails": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_cards": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "phone_numbers": r"\b\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ip_addresses": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    "aws_keys": r"AKIA[0-9A-Z]{16}",
    "private_keys": r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----",
}

# User can add custom patterns in agentprobe.yaml
```

---

## 12. Dashboard UI — עיצוב מפורט

### Tech Stack:
- **Backend**: FastAPI (Python)
- **Frontend**: htmx + Alpine.js + Tailwind CSS
- **Charts**: Chart.js (lightweight, no heavy deps)
- **No build step** — HTML templates with Jinja2, served statically

### Pages:

#### 12.1 Overview Dashboard
```
┌──────────────────────────────────────────────────────────┐
│  AgentProbe Dashboard              localhost:9847         │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  📊 Test Health                    💰 Cost Trend         │
│  ┌────────────────────┐           ┌──────────────────┐  │
│  │  Tests: 47 total   │           │  ▁▂▃▂▄▅▆▅▃ $12  │  │
│  │  ✅ 42 passing     │           │  Last 30 days     │  │
│  │  ❌ 3 failing      │           │  Avg: $0.04/test  │  │
│  │  ⚠️  2 flaky       │           └──────────────────┘  │
│  │  Pass rate: 89.4%  │                                  │
│  └────────────────────┘           ⏱️ Latency Trend      │
│                                   ┌──────────────────┐  │
│  📁 Recordings: 234              │  ▅▃▂▃▂▁▂▃▂ 2.1s │  │
│  🔴 Last failure: 2h ago        │  P95: 4.8s        │  │
│  📈 Trend: improving            └──────────────────┘  │
│                                                          │
│  Recent Test Runs                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Run #47  │ 2 min ago │ 42/47 pass │ $0.23 │ 12s │   │
│  │ Run #46  │ 1 hr ago  │ 44/47 pass │ $0.21 │ 11s │   │
│  │ Run #45  │ 3 hr ago  │ 41/47 pass │ $0.25 │ 14s │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ⚠️  Alerts                                              │
│  • Cost per test increased 15% this week                 │
│  • test_edge_cases::test_unicode failing since Run #43   │
│  • Drift detected: output similarity dropped to 0.81     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

#### 12.2 Trace Viewer (Step-by-Step Debugger)
```
┌──────────────────────────────────────────────────────────┐
│  Trace: customer-support-001        Duration: 3.2s       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Input: "How do I reset my password?"                    │
│                                                          │
│  Timeline:                                               │
│  ──●────────●──────────●────────●───────●──► 3.2s       │
│    │        │          │        │       │                 │
│                                                          │
│  Step 1: LLM Call                      ⏱ 800ms  💰$0.01 │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Model: claude-sonnet-4-6                          │   │
│  │ Input: [system prompt + user message]             │   │
│  │ Output: "I'll search our knowledge base for..."   │   │
│  │ Decision: CALL TOOL search_knowledge_base         │   │
│  │ Tokens: 340 in / 45 out                           │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  Step 2: Tool Call                     ⏱ 200ms          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Tool: search_knowledge_base                       │   │
│  │ Input: {"query": "password reset", "limit": 5}    │   │
│  │ Output: {"results": [{"title": "Password..."}]}   │   │
│  │ Status: ✅ Success                                │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  Step 3: LLM Call                      ⏱ 1200ms 💰$0.02│
│  ┌──────────────────────────────────────────────────┐   │
│  │ Model: claude-sonnet-4-6                          │   │
│  │ Input: [previous context + tool result]           │   │
│  │ Output: "To reset your password, follow these..." │   │
│  │ Decision: RESPOND TO USER                         │   │
│  │ Tokens: 890 in / 120 out                          │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  Output: "To reset your password, follow these steps:   │
│  1. Go to Settings > Security..."                        │
│                                                          │
│  Summary: 2 LLM calls, 1 tool call, $0.03 total        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

#### 12.3 Comparison View
```
┌──────────────────────────────────────────────────────────┐
│  Compare: v1.0 vs v1.1                                   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────┐  ┌─────────────────────┐       │
│  │ v1.0 (baseline)     │  │ v1.1 (current)      │       │
│  │ claude-sonnet-4-6   │  │ claude-sonnet-4-6   │       │
│  │ 3 steps             │  │ 4 steps (+1)        │       │
│  │ $0.03               │  │ $0.04 (+33%)        │       │
│  │ 3.2s                │  │ 4.1s (+28%)         │       │
│  └─────────────────────┘  └─────────────────────┘       │
│                                                          │
│  Output Diff:                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  To reset your password, follow these steps:      │   │
│  │  1. Go to Settings > Security                     │   │
│  │ -2. Click "Reset Password"                        │   │
│  │ +2. Click "Change Password"                       │   │
│  │ +3. Verify your email address                     │   │
│  │  3. Enter your new password                       │   │
│  │  Semantic similarity: 0.91                        │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  Tool Usage Diff:                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ search_knowledge_base  v1.0: 1x  │  v1.1: 1x    │   │
│  │ verify_email           v1.0: 0x  │  v1.1: 1x ⚠️ │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 13. Roadmap — תוכנית פיתוח

### Phase 1: Core MVP (8 שבועות)
**מטרה:** CLI שעובד עם recording + replay + basic assertions

- [ ] Core data models (Recording, Step, Message)
- [ ] Recording engine with auto-instrumentation
  - [ ] OpenAI adapter
  - [ ] Anthropic adapter
  - [ ] Generic HTTP interceptor
- [ ] Storage layer (SQLite + .aprobe files)
- [ ] Replay engine (basic: same model, mock tools)
- [ ] Assertion framework
  - [ ] Output assertions (contains, regex, similarity)
  - [ ] Behavioral assertions (tool calls, step count)
  - [ ] Performance assertions (cost, latency, tokens)
- [ ] CLI
  - [ ] `agentprobe init`
  - [ ] `agentprobe record`
  - [ ] `agentprobe test`
  - [ ] `agentprobe replay`
- [ ] Basic terminal reporter
- [ ] Configuration system (agentprobe.yaml)
- [ ] Redaction engine (PII, API keys)
- [ ] pytest plugin (run via `pytest`)
- [ ] Documentation: README, Quick Start Guide

### Phase 2: Intelligence (6 שבועות)
**מטרה:** Analysis, fuzzing, ו-snapshots

- [ ] Analyzer module
  - [ ] Cost analysis
  - [ ] Latency analysis
  - [ ] Failure classification
  - [ ] Token waste detection
- [ ] Snapshot system
  - [ ] Create baseline snapshots
  - [ ] Regression detection
- [ ] Fuzzer module
  - [ ] Prompt injection strategies
  - [ ] Edge case generation
  - [ ] Tool failure simulation
- [ ] LLM-as-judge (via Ollama)
- [ ] Local embedding model integration
- [ ] Drift detection
- [ ] LangChain adapter
- [ ] CrewAI adapter
- [ ] MCP adapter

### Phase 3: Dashboard & DX (4 שבועות)
**מטרה:** Web dashboard ו-developer experience

- [ ] Web dashboard (FastAPI + htmx)
  - [ ] Overview page
  - [ ] Test runs history
  - [ ] Trace viewer (step-by-step debugger)
  - [ ] Cost dashboard
  - [ ] Comparison view
  - [ ] Recordings browser
- [ ] VS Code extension (basic)
  - [ ] Run tests from editor
  - [ ] View trace inline
- [ ] HTML/Markdown report generation
- [ ] GitHub Actions integration
- [ ] PR comment bot

### Phase 4: Ecosystem (ongoing)
**מטרה:** Plugin system, community, נוספות

- [ ] Plugin system
- [ ] More framework adapters (AutoGen, Haystack, DSPy)
- [ ] Homebrew formula
- [ ] npm wrapper (for JS/TS developers)
- [ ] Multi-agent system testing
- [ ] A/B testing support
- [ ] Benchmark suite (standardized agent benchmarks)
- [ ] Community plugin marketplace
- [ ] Desktop app (Electron/Tauri) with embedded Ollama

---

## 14. Naming & Branding

### שם: **AgentProbe**
- **Agent** = AI Agents
- **Probe** = בדיקה, חקירה, מדידה
- קצר, זכיר, domain likely available
- חלופות: AgentLint, AgentSpec, ProbeAI, TestPilot

### Logo Concept:
- מגדיל/probe עם ניצוץ AI
- צבעים: ירוק (pass) + אדום (fail) + כחול (neutral)

### Tagline Options:
- "pytest for AI Agents"
- "Test your agents before your users do"
- "Record. Replay. Regress-proof."

---

## 15. Competitive Moat — יתרון תחרותי

| Feature | AgentProbe | Promptfoo | DeepEval | Ragas |
|---------|-----------|-----------|----------|-------|
| Agent-aware (not just LLM) | ✅ | ❌ | Partial | ❌ |
| Recording & Replay | ✅ | ❌ | ❌ | ❌ |
| Tool call testing | ✅ | ❌ | ❌ | ❌ |
| Multi-step trace | ✅ | ❌ | ❌ | ❌ |
| Fuzzing/adversarial | ✅ | Basic | ❌ | ❌ |
| 100% local | ✅ | ✅ | Partial | ✅ |
| Visual dashboard | ✅ | ✅ | Cloud | ❌ |
| Snapshot regression | ✅ | ❌ | ❌ | ❌ |
| Framework agnostic | ✅ | ✅ | ✅ | RAG only |
| Cost analysis | ✅ | ❌ | ❌ | ❌ |
| CI/CD native | ✅ | ✅ | ✅ | Partial |

### Main Moat:
1. **Agent-native** — לא "LLM testing", אלא "Agent testing" — מבין steps, tools, decisions
2. **Record/Replay** — אף אחד אחר לא עושה את זה
3. **100% local** — privacy-first, no SaaS dependency
4. **Framework agnostic** — עובד עם כל framework דרך adapters

---

## 16. Success Metrics — מדדי הצלחה

### שנה ראשונה:
- **GitHub Stars**: 5,000+
- **Weekly Downloads (PyPI)**: 10,000+
- **Active Contributors**: 20+
- **Framework Adapters**: 6+ (OpenAI, Anthropic, LangChain, CrewAI, AutoGen, MCP)
- **Community Plugins**: 10+

### Product-Market Fit Signals:
- מפתחים מוסיפים AgentProbe ל-CI/CD pipeline
- חברות פותחות issues/PRs
- Blog posts ו-tutorials מהקהילה
- מוזכר ב-"awesome-lists" ו-newsletters
- Organic growth > paid acquisition

---

## 17. Open Source Strategy

### License: **MIT**
- Maximum adoption
- Companies can use without legal review
- Standard for developer tools

### Community:
- GitHub Discussions for Q&A
- Discord server for real-time chat
- Monthly "Agent Testing" community call
- "Good First Issue" labels for new contributors
- Contributor guide with clear architecture docs

### Monetization (Future, Optional):
- **AgentProbe Cloud** — hosted dashboard for teams (SaaS)
- **Enterprise features** — SSO, RBAC, shared recordings, team analytics
- **Support contracts** — for enterprise customers
- **Training & consulting** — workshops on agent testing best practices

> **Important**: The open source tool must be 100% functional standalone.
> Cloud/enterprise features are additive, not subtractive.

---

## 18. Key Technical Decisions

### Why Python (not TypeScript/Go/Rust)?
- 90%+ of AI agent developers write Python
- All major agent frameworks are Python-first
- Monkey-patching is trivial in Python (critical for auto-instrumentation)
- Lower barrier for community contributions

### Why SQLite (not PostgreSQL/DuckDB)?
- Zero configuration — `pip install` and it works
- No separate server process
- Good enough for single-developer local usage
- Can scale to millions of recordings easily
- DuckDB considered for analytics queries (future optimization)

### Why htmx (not React/Vue)?
- No build step — just HTML templates
- Much smaller bundle size
- Server-rendered = faster initial load
- Easier to contribute to (no frontend framework expertise needed)
- Good enough for a local dashboard

### Why Ollama for local models (not llama.cpp directly)?
- Ollama handles model management (download, update, serve)
- Widely adopted — many developers already have it installed
- Simple HTTP API
- Supports all major open models
- Falls back to sentence-transformers if Ollama not available

---

*Document Version: 1.0*
*Created: April 2026*
*Last Updated: April 2026*
