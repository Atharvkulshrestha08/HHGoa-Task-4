import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from src.agent.llm_agent import FraudInvestigationAgent

agent = FraudInvestigationAgent(data_dir=".")

steps = []

def on_step(step_type, data):
    if step_type == "tool_call":
        tool_name = data["tool"]
        args = data["args"]
        steps.append("TOOL: {}({})".format(tool_name, args))
        print("  [Step {}] Calling {}...".format(data["iteration"], tool_name))
    elif step_type == "tool_result":
        print("  [Result] {} -> {} chars".format(data["tool"], len(data["result"])))
    elif step_type == "response":
        steps.append("RESPONSE_READY")

print("=== Testing AI Fraud Investigation Agent ===\n")
print("Sending: 'Investigate case HHG-001. Give me your verdict.'\n")

result = agent.chat("Investigate case HHG-001. Give me your verdict.", on_step=on_step)

print("\n--- Final Response (first 800 chars) ---")
print(result[:800])
print("\n--- Stats ---")
print("Tool calls made:", agent.engine.get_tool_calls())
print("LLM tokens used:", agent.total_tokens)
