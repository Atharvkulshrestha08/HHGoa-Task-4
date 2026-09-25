"""
🕵️ AI Fraud Investigation Agent — Interactive Dashboard
A real AI copilot that reasons, queries the knowledge graph, and investigates fraud live.
"""

import sys
import os
import json
import time
import streamlit as st

# Fix imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from src.agent.hybrid_agent import HybridFraudAgent

# -- Page config --
st.set_page_config(
    page_title="AI Fraud Investigation Agent",
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -- Custom CSS --
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #0a0e1a;
    --bg-secondary: #111827;
    --bg-card: #1a1f35;
    --accent-blue: #3b82f6;
    --accent-cyan: #06b6d4;
    --accent-red: #ef4444;
    --accent-green: #22c55e;
    --accent-amber: #f59e0b;
    --accent-purple: #a855f7;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --border-dim: #1e293b;
}

/* Main app background */
.stApp {
    background: linear-gradient(135deg, var(--bg-primary) 0%, #0f172a 50%, #1a1033 100%) !important;
    font-family: 'Inter', sans-serif;
    color: var(--text-primary);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #161b22 100%) !important;
    border-right: 1px solid rgba(59, 130, 246, 0.15) !important;
}

section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li {
    color: #c9d1d9 !important;
    font-size: 0.88rem;
}

/* Chat messages */
.stChatMessage {
    background: rgba(26, 31, 53, 0.85) !important;
    border: 1px solid rgba(59, 130, 246, 0.12) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(20px) !important;
    padding: 1rem 1.2rem !important;
    margin-bottom: 0.8rem !important;
}

/* Chat input */
.stChatInput textarea {
    background: rgba(17, 24, 39, 0.95) !important;
    border: 1px solid rgba(59, 130, 246, 0.3) !important;
    border-radius: 12px !important;
    color: #f1f5f9 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
}

.stChatInput textarea:focus {
    border-color: rgba(59, 130, 246, 0.7) !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
}

/* Expanders for tool calls */
.streamlit-expanderHeader {
    background: rgba(17, 24, 39, 0.9) !important;
    border: 1px solid rgba(59, 130, 246, 0.2) !important;
    border-radius: 8px !important;
    color: var(--accent-cyan) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
}

.streamlit-expanderContent {
    background: rgba(10, 14, 26, 0.95) !important;
    border: 1px solid rgba(59, 130, 246, 0.1) !important;
    border-radius: 0 0 8px 8px !important;
}

/* Code blocks */
code {
    color: var(--accent-cyan) !important;
    background: rgba(6, 182, 212, 0.08) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85em !important;
}

pre code {
    background: rgba(10, 14, 26, 0.95) !important;
    border: 1px solid rgba(59, 130, 246, 0.15) !important;
    border-radius: 8px !important;
    padding: 1rem !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(168, 85, 247, 0.15)) !important;
    border: 1px solid rgba(59, 130, 246, 0.35) !important;
    border-radius: 10px !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.35), rgba(168, 85, 247, 0.25)) !important;
    border-color: rgba(59, 130, 246, 0.6) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2) !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background: rgba(17, 24, 39, 0.9) !important;
    border: 1px solid rgba(59, 130, 246, 0.25) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
}

/* Metric cards */
.stMetric {
    background: rgba(26, 31, 53, 0.6) !important;
    border: 1px solid rgba(59, 130, 246, 0.12) !important;
    border-radius: 10px !important;
    padding: 0.8rem !important;
}

.stMetric label {
    color: var(--text-secondary) !important;
}

/* Headers */
h1, h2, h3, h4 {
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-primary);
}
::-webkit-scrollbar-thumb {
    background: rgba(59, 130, 246, 0.3);
    border-radius: 3px;
}

/* Tool call badge */
.tool-badge {
    display: inline-block;
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(59, 130, 246, 0.1));
    border: 1px solid rgba(6, 182, 212, 0.3);
    border-radius: 6px;
    padding: 2px 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: #06b6d4;
    margin: 2px 4px 2px 0;
}

/* Investigation card */
.case-card {
    background: linear-gradient(135deg, rgba(26, 31, 53, 0.9), rgba(17, 24, 39, 0.8));
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 12px;
    padding: 1.2rem;
    margin: 0.5rem 0;
}

/* Pulse animation for active */
@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 5px rgba(34, 197, 94, 0.3); }
    50% { box-shadow: 0 0 20px rgba(34, 197, 94, 0.6); }
}

.agent-active {
    animation: pulse-glow 2s infinite;
}

/* Status indicator */
.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
}

.status-active { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.status-idle { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
</style>
""", unsafe_allow_html=True)


# -- Initialize session state --
if "agent" not in st.session_state:
    st.session_state.agent = HybridFraudAgent(data_dir=os.path.dirname(os.path.abspath(__file__)) + "/..")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "tool_calls_history" not in st.session_state:
    st.session_state.tool_calls_history = []

if "active_case" not in st.session_state:
    st.session_state.active_case = None

if "total_investigations" not in st.session_state:
    st.session_state.total_investigations = 0


# -- Sidebar --
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <span style="font-size: 2.5rem;">🕵️</span>
        <h2 style="margin: 0.3rem 0 0 0; font-size: 1.3rem; background: linear-gradient(135deg, #3b82f6, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            Fraud Investigation AI
        </h2>
        <p style="color: #64748b; font-size: 0.78rem; margin-top: 0.2rem;">
            Agentic ReAct Loop • Groq LLM • Graph Analytics
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Case Quick Launch
    st.markdown("##### 🎯 Quick Launch Case")
    case_ids = [f"HHG-{str(i).zfill(3)}" for i in range(1, 21)]
    selected_case = st.selectbox("Select a case to investigate:", ["— Choose —"] + case_ids, label_visibility="collapsed")

    if selected_case != "— Choose —":
        if st.button(f"🔍 Investigate {selected_case}", use_container_width=True):
            st.session_state.pending_message = f"Investigate case {selected_case}. Start with the case context, then gather baseline data, check for anomalies, run pattern detectors, search case memory, and give me your full verdict with recommended actions."
            st.session_state.active_case = selected_case
            st.rerun()

    st.divider()

    # Scenario shortcuts
    st.markdown("##### ⚡ Investigation Scenarios")

    if st.button("🔎 Compare two cases", use_container_width=True):
        st.session_state.pending_message = "Compare HHG-001 and HHG-002. Pull context for both, contrast their patterns, and tell me which is more likely to be fraud and why."
        st.rerun()

    if st.button("🕸️ Hunt for fraud rings", use_container_width=True):
        st.session_state.pending_message = "Search for device-based fraud rings across the test cases. Check shared devices, proxy usage, and coordinated patterns. Which cases might be connected?"
        st.rerun()

    if st.button("📊 Portfolio risk summary", use_container_width=True):
        st.session_state.pending_message = "Give me a quick risk summary of all 20 test cases. For each, pull the case context and give a one-line risk assessment."
        st.rerun()

    if st.button("🧪 What-if scenario", use_container_width=True):
        st.session_state.pending_message = "Let's run a what-if: If the flagged transaction in HHG-003 was $50 instead of its actual amount, would your verdict change? Walk through the policy logic."
        st.rerun()

    st.divider()

    # Session stats
    st.markdown("##### 📈 Session Stats")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Messages", len(st.session_state.messages))
    with col2:
        st.metric("Tool Calls", len(st.session_state.tool_calls_history))

    col3, col4 = st.columns(2)
    with col3:
        st.metric("LLM Tokens", f"{st.session_state.agent.total_tokens:,}")
    with col4:
        st.metric("Investigations", st.session_state.total_investigations)

    st.divider()

    # Reset
    if st.button("🗑️ Clear Session", use_container_width=True):
        st.session_state.agent.reset_conversation()
        st.session_state.messages = []
        st.session_state.tool_calls_history = []
        st.session_state.active_case = None
        st.session_state.total_investigations = 0
        st.rerun()

    # Model info
    st.markdown(f"""
    <div style="margin-top: 1rem; padding: 0.8rem; background: rgba(17, 24, 39, 0.6); border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.15);">
        <p style="margin: 0; font-size: 0.75rem; color: #64748b;">
            <span class="status-dot status-active"></span>
            <strong style="color: #94a3b8;">Model:</strong> Qwen 3.8-27B via Groq<br>
            <strong style="color: #94a3b8;">Tools:</strong> 15 graph investigation tools<br>
            <strong style="color: #94a3b8;">Data:</strong> 590K txns • 144K identities • 5.5K cases<br>
            <strong style="color: #94a3b8;">Mode:</strong> ReAct (Thought → Tool → Observe → Act)
        </p>
    </div>
    """, unsafe_allow_html=True)


# -- Main Chat Interface --
st.markdown("""
<div style="text-align: center; margin-bottom: 1.5rem;">
    <h1 style="font-size: 1.8rem; font-weight: 700; margin: 0; 
               background: linear-gradient(135deg, #3b82f6, #06b6d4, #a855f7); 
               -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        🕵️ AI Fraud Investigation Agent
    </h1>
    <p style="color: #64748b; font-size: 0.88rem; margin-top: 0.3rem;">
        Interactive AI copilot for real-time fraud investigation • Ask anything • Watch it reason
    </p>
</div>
""", unsafe_allow_html=True)

# Display existing messages
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👨‍💻"):
            st.markdown(msg["content"])
    elif msg["role"] == "assistant":
        with st.chat_message("assistant", avatar="🕵️"):
            # Show tool calls if any
            if "tool_calls" in msg and msg["tool_calls"]:
                for tc in msg["tool_calls"]:
                    with st.expander(f"🔧 `{tc['tool']}` → {json.dumps(tc['args'], default=str)[:80]}"):
                        st.code(json.dumps(tc["args"], indent=2, default=str), language="json")
                        if "result" in tc:
                            st.code(tc["result"][:1000], language="json")
            st.markdown(msg["content"])


# -- Handle pending messages from sidebar buttons --
if "pending_message" in st.session_state:
    user_input = st.session_state.pending_message
    del st.session_state.pending_message
else:
    user_input = st.chat_input("Ask me to investigate a case, compare patterns, or run a what-if scenario...")

if user_input:
    # Display user message
    with st.chat_message("user", avatar="👨‍💻"):
        st.markdown(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})

    # Agent response with live tool-call display
    with st.chat_message("assistant", avatar="🕵️"):
        tool_calls_this_turn = []
        status_container = st.empty()
        tool_display_container = st.container()

        def on_step(step_type: str, data):
            """Callback for live streaming of agent steps."""
            if step_type == "tool_call":
                tool_name = data["tool"]
                args = data["args"]
                iteration = data["iteration"]

                status_container.markdown(f"""
                <div style="padding: 0.5rem 1rem; background: rgba(6, 182, 212, 0.08); 
                     border-left: 3px solid #06b6d4; border-radius: 0 8px 8px 0; margin-bottom: 0.5rem;">
                    <span style="color: #06b6d4; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                        ⏳ Step {iteration}: Calling <code>{tool_name}</code>...
                    </span>
                </div>
                """, unsafe_allow_html=True)

                tc_record = {"tool": tool_name, "args": args}
                tool_calls_this_turn.append(tc_record)

            elif step_type == "tool_result":
                tool_name = data["tool"]
                result = data["result"]
                if tool_calls_this_turn:
                    tool_calls_this_turn[-1]["result"] = result

                with tool_display_container:
                    with st.expander(f"🔧 `{tool_name}` → result", expanded=False):
                        st.code(result[:1500], language="json")

                st.session_state.tool_calls_history.append({
                    "tool": tool_name,
                    "timestamp": time.strftime("%H:%M:%S")
                })

            elif step_type == "response":
                status_container.empty()

        # Run the agent
        with st.spinner("🧠 Agent is reasoning..."):
            response = st.session_state.agent.chat(user_input, on_step=on_step)
            st.session_state.total_investigations += 1

        # Display the response
        st.markdown(response)

    # Save to session
    st.session_state.messages.append({
        "role": "assistant",
        "content": response,
        "tool_calls": tool_calls_this_turn
    })
