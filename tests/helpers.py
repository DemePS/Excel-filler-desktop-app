"""Test helpers: a mocked Claude API (real SDK, fake HTTP), a scripted UI, a tiny PDF writer."""

from __future__ import annotations

import json

import httpx
from anthropic import AnthropicFoundry

from coding_agent.ui import UI


def sse(blocks, stop):
    msg = {"id": "m", "type": "message", "role": "assistant", "model": "x", "content": [], "stop_reason": None,
           "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1,
                                             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    ev = [("message_start", {"type": "message_start", "message": msg})]
    for i, (kind, value) in enumerate(blocks):
        if kind == "text":
            ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}),
                   ("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": value}})]
        else:
            ev += [("content_block_start", {"type": "content_block_start", "index": i,
                                            "content_block": {"type": "tool_use", "id": f"toolu_{kind}_{i}", "name": kind, "input": {}}}),
                   ("content_block_delta", {"type": "content_block_delta", "index": i,
                                            "delta": {"type": "input_json_delta", "partial_json": json.dumps(value)}})]
        ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    ev += [("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 5}}),
           ("message_stop", {"type": "message_stop"})]
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in ev)


class FakeClaude:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def handler(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        if not body.get("stream"):  # the background memory curator
            return httpx.Response(200, json={"id": "c", "type": "message", "role": "assistant", "model": "x",
                                             "content": [{"type": "text", "text": "NO_CHANGE"}], "stop_reason": "end_turn",
                                             "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
        blocks, stop = self.script.pop(0)
        return httpx.Response(200, text=sse(blocks, stop), headers={"content-type": "text/event-stream"})

    def client(self):
        return AnthropicFoundry(api_key="k", base_url="https://x.services.ai.azure.com/anthropic",
                                http_client=httpx.Client(transport=httpx.MockTransport(self.handler)))

    def tool_results(self, request_index):
        """The tool results the agent sent back in a given request, by tool name."""
        return {r["tool_use_id"].split("_")[1]: r for r in self.requests[request_index]["messages"][-1]["content"]}


class ScriptedUI(UI):
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.events = []

    def status(self, text): self.events.append(("status", text))
    def success(self, text): self.events.append(("success", text))
    def failure(self, text): self.events.append(("failure", text))
    def message(self, text): self.events.append(("message", text))
    def cell_changes(self, title, rows, more): self.events.append(("cells", title, rows))
    def panel(self, title, lines=(), tone="change"): self.events.append(("panel", title, tone))
    def assistant_text(self, text): self.events.append(("text", text))

    def confirm(self, question, choices=("yes", "no")):
        self.events.append(("confirm", question))
        return self.answers.pop(0) if self.answers else "no"

    def ask_text(self, prompt, multiline=False):
        self.events.append(("ask_text", prompt))
        return self.answers.pop(0) if self.answers else ""


def make_pdf(path, pages):
    """A minimal PDF with one line of text per page."""
    objs = ["<</Type/Catalog/Pages 2 0 R>>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<</Type/Pages/Kids[{kids}]/Count {len(pages)}>>")
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 14 Tf 20 100 Td ({text}) Tj ET"
        objs.append(f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 200]/Contents {4 + 2 * i} 0 R"
                    f"/Resources<</Font<</F1 {font} 0 R>>>>>>")
        objs.append(f"<</Length {len(stream)}>>stream\n{stream}\nendstream")
    objs.append("<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    out, offsets = "%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(out.encode("latin-1"))
