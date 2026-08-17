"""
LangGraph agent that orchestrates the chatbot's decision-making:
answer directly, use RAG (via tools), or call an MCP tool.

Uses Groq (openai/gpt-oss-120b) with native tool-calling.
"""

from typing import Annotated, TypedDict
import asyncio

REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from groq import AsyncGroq
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

from app.config import settings
from app.utils.logger import logger
from app.mcp_tools.server import (
    get_past_solutions,
    create_order,
    check_available_slots,
    book_meeting,
    add_call_notes,
    get_client_context,
    search_knowledge_base,
)

# ==============================
# System Prompt
# ==============================
SYSTEM_PROMPT = """You are the chat assistant for Coding Media (website: https://codingmedia.in/, contact: +91 83064 71487), a software development / IT company based in Jaipur, Rajasthan, India. The agency provides custom services: website development, website/graphic design (including catalogs and browsing/portal interfaces), AI automation/chatbots, custom software, and marketing services. This is a services business — you never quote a fixed catalog price.

If a client asks the agency's name, website, contact number, or location, answer directly using the details above — do NOT say you don't have this information, and do NOT ask the client for their own phone number to "look it up." This information is always available to you.

Language rule (STRICT — follow this exactly):
- Mirror the client's language MIX, not just the script.
- If the client writes in Hinglish (Hindi words mixed with English, typed in Latin/English script — e.g. "aap log kya services dete ho"), you MUST reply in Hinglish too — using a natural mix of Hindi and English words in Latin script. Do NOT reply in pure English, and do NOT switch to Devanagari script.
- If the client writes in pure English (no Hindi words at all), reply in pure English.
- If the client writes in Devanagari (Hindi script), reply in Devanagari.
- When the message is very short/ambiguous (e.g. just "hi"), match the general tone: if any Hindi/Hinglish cue is present, lean Hinglish in Latin script; otherwise use simple English.
- Examples:
  - User: "aap log kya services dete ho?" -> Reply in Hinglish: "Hum yeh services dete hain: ..." (NOT pure English, NOT Devanagari)
  - User: "What services do you offer?" -> Reply in English.
  - User: "आप क्या सेवाएं देते हैं?" -> Reply in Devanagari Hindi.

Your responsibilities:
1. Understand what the client needs and which service category it falls under (web-development, web-design, graphic-design, ai-automation, custom-software).
1b. Use search_knowledge_base whenever a client asks about company details, services, processes, policies, or general FAQs that aren't covered by your built-in identity info (name/location/contact) above. Prefer calling this tool over answering from memory for anything beyond basic identity facts.
2. Use get_past_solutions to show relevant case studies when it would help build trust or clarify what the agency can do.
3. Qualify the lead — ask about their requirement, timeline, and rough scope. Do NOT ask for exact budget numbers aggressively; let it come up naturally.
4. Once a client shows genuine interest, use create_order to capture the lead.
5. NEVER call book_meeting with a date/time you guessed or assumed. Always call check_available_slots first for a SPECIFIC date, show the client the real available slots, and wait for them to explicitly pick one before calling book_meeting. If the client says something vague like "anytime" or "whenever works", ask them to pick a specific date first, then show slots for that date. If a client wants to change an already-booked time, confirm the new slot the same way — book_meeting will automatically handle cancelling their old meeting.
6. At the start of a conversation with a returning client (if phone number is known), use get_client_context to recall their history and personalize your response — don't ask for info you already have.
7. NEVER finalize or quote exact pricing. Pricing depends on project scope and is decided by the human team after understanding requirements. You can say things like "pricing depends on scope, our team will share a quote after understanding your requirements."
8. If a client asks something you genuinely don't know or that requires human judgment (e.g. contract terms, highly custom technical feasibility), be honest about it and offer to connect them with the team or book a call.
9. Be warm, professional, and concise. Avoid long paragraphs — this is a chat interface, not an essay.
10. When the client's message is ambiguous, has typos, or uses unclear terminology (e.g. "browser" when they might mean "browse" or "website"), do NOT silently reinterpret it into more complex/technical scope than they described. Instead, reflect back what you understood in simple terms and ask them to confirm — e.g. "Just to confirm, you're looking for a website where customers can browse your product catalog — is that right?" Keep your interpretation as close to their literal words as possible until they confirm or add detail. Avoid introducing complex scope (like user accounts, checkout, or advanced features) unless the client mentions it themselves.
11. Never invent case studies, prices, or capabilities that were not provided to you via tools or context.

Always aim to move the conversation toward one of two outcomes: capturing a qualified lead (create_order) or booking a consultation call (book_meeting) — but only when it feels natural, not forced.
"""


# ==============================
# Agent State
# ==============================
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ==============================
# Tools registration
# ==============================
tools = [
    get_past_solutions,
    create_order,
    check_available_slots,
    book_meeting,
    add_call_notes,
    get_client_context,
    search_knowledge_base,
]

tool_node = ToolNode(tools)

# Build Groq-compatible tool schemas from the MCP tool functions
_groq_client = AsyncGroq(api_key=settings.groq_api_key)


def _build_groq_tool_schema(tool_fn) -> dict:
    """
    Convert an MCP tool (FastMCP-decorated async function) into a
    Groq-compatible OpenAI-style tool schema using its docstring
    and type hints.
    """
    import inspect

    sig = inspect.signature(tool_fn)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == float:
            param_type = "number"
        elif param.annotation == bool:
            param_type = "boolean"

        properties[name] = {"type": param_type, "description": f"{name} parameter"}

        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": tool_fn.__name__,
            "description": (tool_fn.__doc__ or "").strip().split("\n")[0],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_GROQ_TOOL_SCHEMAS = [_build_groq_tool_schema(t) for t in tools]


# ==============================
# Graph nodes
# ==============================
async def call_model(state: AgentState) -> dict:
    """
    Calls Groq with the current conversation + tool definitions.
    Groq decides whether to respond directly or call a tool.
    """
    lc_messages = state["messages"]

    current_datetime_ist = datetime.now(IST)
    date_context = (
        f"\n\nCurrent date and time (IST, Asia/Kolkata): "
        f"{current_datetime_ist.strftime('%A, %d %B %Y, %I:%M %p')} "
        f"(ISO date: {current_datetime_ist.strftime('%Y-%m-%d')}). "
        f"Always use this as the actual current date/time — never guess or assume "
        f"a different year. When the client says 'today', 'tomorrow', 'this week', etc., "
        f"resolve it relative to this exact date."
    )

    groq_messages = [{"role": "system", "content": SYSTEM_PROMPT + date_context}]
    for msg in lc_messages:
        if isinstance(msg, HumanMessage):
            groq_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                groq_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": str(tc["args"]),
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
            else:
                groq_messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            groq_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": str(msg.content),
                }
            )

    response = None
    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = await asyncio.wait_for(
                _groq_client.chat.completions.create(
                    model=settings.groq_model,
                    messages=groq_messages,
                    tools=_GROQ_TOOL_SCHEMAS,
                    temperature=0.4,
                    max_tokens=1024,
                ),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            break
        except Exception as e:
            logger.warning(
                f"Groq call failed on attempt {attempt}/{MAX_RETRIES + 1}: {e}"
            )
            last_error = e
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if response is None:
        logger.error(f"Groq failed after {MAX_RETRIES + 1} attempts: {last_error}")
        raise RuntimeError(str(last_error))

    choice = response.choices[0].message

    if choice.tool_calls:
        import json

        tool_calls = []
        for tc in choice.tool_calls:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                }
            )
        ai_msg = AIMessage(content=choice.content or "", tool_calls=tool_calls)
    else:
        ai_msg = AIMessage(content=choice.content or "")

    return {"messages": [ai_msg]}


def should_continue(state: AgentState) -> str:
    """Route to tool execution if the last AI message requested tool calls."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


# ==============================
# Build the graph
# ==============================
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

agent_graph = workflow.compile()


async def run_agent(
    user_message: str, conversation_history: list[BaseMessage] | None = None
) -> tuple[str, bool]:
    """
    Entry point to run the agent for a single user message.

    Returns:
        A tuple of (reply_text, used_tools) — used_tools is True if any
        tool was called during this turn, signaling the caller should
        NOT cache this response (tool results can be time-sensitive,
        personalized, or dynamic).
    """
    messages = list(conversation_history or [])
    messages.append(HumanMessage(content=user_message))

    try:
        result = await agent_graph.ainvoke({"messages": messages})
        result_messages = result["messages"]

        used_tools = any(
            isinstance(m, AIMessage) and m.tool_calls for m in result_messages
        )

        final_message = result_messages[-1]
        return (
            final_message.content or "Sorry, I couldn't generate a response.",
            used_tools,
        )
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        return (
            "Sorry, I'm having trouble responding right now. "
            "Our team has been notified. Please try again in a moment."
        ), False
