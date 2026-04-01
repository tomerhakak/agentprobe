"""Example: Customer Support Agent using AgentProbe.

A simple agent that answers customer questions by searching a knowledge base.
No real API keys needed — the search tool is simulated for demo purposes.
"""

from __future__ import annotations

import time
from typing import Any

from agentprobe import record, RecordingSession


# ---------------------------------------------------------------------------
# Simulated knowledge base (no API key required)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = {
    "refund": {
        "title": "Refund Policy",
        "content": (
            "Refunds are available within 30 days of purchase. "
            "To request a refund, contact support with your order number. "
            "Refunds are processed within 5-7 business days."
        ),
    },
    "shipping": {
        "title": "Shipping Information",
        "content": (
            "Standard shipping takes 5-7 business days. "
            "Express shipping takes 1-2 business days and costs $9.99. "
            "Free shipping on orders over $50."
        ),
    },
    "account": {
        "title": "Account Management",
        "content": (
            "You can reset your password at account.example.com/reset. "
            "To delete your account, email privacy@example.com. "
            "Two-factor authentication is available in account settings."
        ),
    },
    "hours": {
        "title": "Business Hours",
        "content": (
            "Our support team is available Monday-Friday, 9am-6pm EST. "
            "Live chat is available 24/7. "
            "Response time for email tickets is under 4 hours."
        ),
    },
}


def search_knowledge_base(query: str) -> list[dict[str, str]]:
    """Simulate a knowledge base search. Returns matching articles."""
    query_lower = query.lower()
    results = []
    for key, article in KNOWLEDGE_BASE.items():
        if key in query_lower or any(
            word in article["content"].lower() for word in query_lower.split()
        ):
            results.append(article)
    # Fallback: return the most general article
    if not results:
        results.append({
            "title": "General Help",
            "content": "For further assistance, please contact support@example.com or call 1-800-555-0199.",
        })
    return results


def format_response(articles: list[dict[str, str]], query: str) -> str:
    """Format search results into a customer-friendly response."""
    if not articles:
        return "I'm sorry, I couldn't find information about that. Please contact our support team."

    parts = []
    for article in articles:
        parts.append(article["content"])

    response = " ".join(parts)
    return f"Based on your question about '{query}': {response}"


# ---------------------------------------------------------------------------
# The Agent — decorated with @record for AgentProbe tracing
# ---------------------------------------------------------------------------

@record("customer-support-agent", tags=["support", "example"])
def run_agent(query: str, session: RecordingSession) -> str:
    """Handle a customer support query.

    This function is decorated with @record, which automatically:
    - Creates a recording session
    - Passes it as the `session` keyword argument
    - Finishes the recording when the function returns

    Args:
        query: The customer's question.
        session: Injected by @record — used to trace each step.

    Returns:
        A customer-friendly response string.
    """
    # 1. Record the input
    session.set_input(query, input_type="text")
    session.set_environment(
        model="gpt-4o-mini",
        system_prompt="You are a helpful customer support agent.",
        tools=[{"name": "search_kb", "description": "Search the knowledge base"}],
    )

    # 2. Simulate an LLM call that decides to search
    session.add_llm_call(
        model="gpt-4o-mini",
        input_messages=[
            {"role": "system", "content": "You are a helpful customer support agent."},
            {"role": "user", "content": query},
        ],
        output_message={
            "role": "assistant",
            "content": f"I'll search the knowledge base for information about: {query}",
        },
        input_tokens=45,
        output_tokens=20,
        latency_ms=320.0,
    )

    # 3. Search the knowledge base (tool call)
    start = time.perf_counter()
    results = search_knowledge_base(query)
    tool_duration = (time.perf_counter() - start) * 1000

    session.add_tool_call(
        tool_name="search_kb",
        tool_input={"query": query},
        tool_output={"results": results, "count": len(results)},
        duration_ms=tool_duration,
        success=True,
    )

    # 4. Record a decision
    session.add_decision(
        decision_type="tool_selection",
        reason=f"Selected search_kb because user asked about: {query}",
        alternatives=["escalate_to_human", "ask_clarifying_question"],
    )

    # 5. Format the response (tool call)
    start = time.perf_counter()
    answer = format_response(results, query)
    format_duration = (time.perf_counter() - start) * 1000

    session.add_tool_call(
        tool_name="format_response",
        tool_input={"articles_count": len(results), "query": query},
        tool_output={"response": answer},
        duration_ms=format_duration,
        success=True,
    )

    # 6. Final LLM call to polish the answer
    session.add_llm_call(
        model="gpt-4o-mini",
        input_messages=[
            {"role": "system", "content": "You are a helpful customer support agent."},
            {"role": "user", "content": query},
            {"role": "assistant", "content": f"Search results: {results}"},
        ],
        output_message={"role": "assistant", "content": answer},
        input_tokens=120,
        output_tokens=60,
        latency_ms=450.0,
    )

    # 7. Record the output
    session.set_output(answer, output_type="text", status="success")

    return answer


# ---------------------------------------------------------------------------
# Run standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    queries = [
        "What is your refund policy?",
        "How long does shipping take?",
        "How do I reset my password?",
    ]

    for q in queries:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"{'='*60}")
        result = run_agent(q)
        print(f"A: {result}")
