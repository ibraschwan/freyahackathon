"""Model calls of the builder, and the trace of a build run.

The builder uses Claude through the Claude Agent SDK with no tools: one prompt in, one text out. It works with a
Claude login or with ANTHROPIC_API_KEY. Every call is written to the trace with its model and its purpose.
"""
import asyncio, json, os, re, time

MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")

class Trace:
    """Plain-text log of one build run: start and end, every model call, what was created, what was tested."""
    def __init__(self, path):
        self.path, self.t0, self.calls, self.usd = path, time.time(), 0, 0.0
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        open(path, "w").write("")
        self.log("START " + time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    def log(self, line):
        line = re.sub(r"fak_[A-Za-z0-9]+", "fak_***", str(line))                      # a trace must never hold a key
        with open(self.path, "a") as f: f.write(f"[{time.time() - self.t0:7.1f}s] {line}\n")
        print(line, flush=True)
    def end(self, note=""):
        self.log(f"END {time.strftime('%Y-%m-%dT%H:%M:%S%z')} | {time.time() - self.t0:.0f} s | {self.calls} model calls, {self.usd:.2f} USD{' | ' + note if note else ''}")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:                                                                         # the spend ledger of the improvement loop, and a copy of every trace
            os.makedirs(os.path.join(root, "auto"), exist_ok=True); os.makedirs(os.path.join(root, "traces", "history"), exist_ok=True)
            with open(os.path.join(root, "auto", "spend.tsv"), "a") as f: f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{os.path.basename(self.path)}\t{self.calls}\t{self.usd:.2f}\t{time.time() - self.t0:.0f}\n")
            import shutil; shutil.copy(self.path, os.path.join(root, "traces", "history", time.strftime("%m%d-%H%M%S-") + os.path.basename(self.path)))
        except Exception: pass

async def ask(trace, purpose, system, prompt, model=None):
    """One model call. Returns the text of the answer."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    model = model or MODEL
    opts = ClaudeAgentOptions(model=model, system_prompt=system, allowed_tools=[], max_turns=1, setting_sources=[], permission_mode="dontAsk")
    t0, text, cost = time.time(), "", None
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, AssistantMessage): text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        elif isinstance(m, ResultMessage): cost = m.total_cost_usd
    trace.calls += 1
    trace.usd += float(cost or 0)
    trace.log(f"MODEL CALL {trace.calls}: model={model} | purpose: {purpose} | {time.time() - t0:.0f} s | prompt {len(prompt)} chars, answer {len(text)} chars" + (f" | ${cost:.2f}" if cost else ""))
    return text

def json_of(text):
    """The JSON object in a model answer: the last fenced block, or the outermost braces."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    cand = blocks[-1] if blocks else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(cand)

def tag_of(text, tag):
    m = re.search(r"<" + tag + r">\s*(.*?)\s*</" + tag + r">", text, flags=re.S)
    return m.group(1) if m else None

def run(coro): return asyncio.run(coro)
