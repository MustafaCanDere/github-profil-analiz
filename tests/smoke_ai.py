"""AI modülünü sahte bir Claude API sunucusuna karşı dener (gerçek anahtar gerektirmez)."""

import http.server
import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import anthropic  # noqa: E402

from ghanaliz import ai  # noqa: E402

seen = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        seen.update(json.loads(self.rfile.read(int(self.headers["content-length"]))))
        seen["path"] = self.path
        seen["gemini_key"] = self.headers.get("x-goog-api-key")
        reply = {"description": "d", "topics": ["Hello World"], "readme": "# r"}
        if ":generateContent" in self.path:
            body = json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(reply)}]},
                                               "finishReason": "STOP"}]}).encode()
        else:
            body = json.dumps({
                "id": "msg_test", "type": "message", "role": "assistant", "model": ai.MODEL,
                "content": [{"type": "text", "text": json.dumps(reply)}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

bot = ai.ClaudeAssistant("sk-test")
bot.client = anthropic.Anthropic(api_key="sk-test", base_url=f"http://127.0.0.1:{srv.server_port}", max_retries=0)
out = bot._ask("deneme", ai.REPO_SCHEMA)
assert out["readme"] == "# r", out
assert seen["model"] == ai.MODEL and seen["fallbacks"] == "default", seen
assert seen["output_config"]["format"]["type"] == "json_schema", seen
assert ai.clean_topics(out["topics"]) == ["hello-world"]

gem = ai.GeminiAssistant("g-test", model="gemini-3.8-flash")
gem.url = f"http://127.0.0.1:{srv.server_port}/v1beta/models/gemini-3.8-flash:generateContent"
seen.clear()
out = gem._ask("deneme", ai.REPO_SCHEMA)
assert out["readme"] == "# r", out
assert seen["gemini_key"] == "g-test", seen
assert seen["generationConfig"]["responseJsonSchema"] == ai.REPO_SCHEMA, seen
print("AI smoke test OK")
