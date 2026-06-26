from __future__ import annotations

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from runner import run_agent_task
from utils import DocumentExtractionError, LOGS_DIR, load_env_file


AGENT_DIR = Path(__file__).resolve().parent


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DAIMON Proposal Agent</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #6b7280;
      --line: #d9dee7;
      --accent: #2f6f73;
      --accent-dark: #24585b;
      --soft: #eef6f5;
      --code: #f2f4f7;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      height: 100vh;
      overflow: hidden;
    }

    .app {
      display: grid;
      grid-template-columns: minmax(340px, 44vw) minmax(360px, 1fr);
      height: 100vh;
    }

    .document {
      background: var(--panel);
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    .chat {
      display: flex;
      flex-direction: column;
      min-width: 0;
      background: #fbfcfd;
    }

    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.92);
    }

    .title {
      min-width: 0;
    }

    .title h1 {
      margin: 0;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 700;
      letter-spacing: 0;
    }

    .title p {
      margin: 3px 0 0;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .doc-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .doc-actions a,
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 13px;
      text-decoration: none;
      cursor: pointer;
      line-height: 1;
    }

    button.primary {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      min-width: 86px;
    }

    button.primary:hover {
      background: var(--accent-dark);
      border-color: var(--accent-dark);
    }

    button:disabled {
      opacity: 0.56;
      cursor: wait;
    }

    .result {
      padding: 28px 34px 56px;
      overflow: auto;
      line-height: 1.52;
      font-size: 14px;
    }

    .empty {
      color: var(--muted);
      max-width: 560px;
    }

    .result h1,
    .result h2,
    .result h3 {
      margin: 24px 0 10px;
      line-height: 1.22;
      letter-spacing: 0;
    }

    .result h1 { font-size: 24px; }
    .result h2 { font-size: 19px; }
    .result h3 { font-size: 16px; }
    .result p { margin: 0 0 12px; }
    .result ul,
    .result ol {
      margin: 0 0 14px 22px;
      padding: 0;
    }
    .result li { margin: 5px 0; }
    .result code {
      background: var(--code);
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 1px 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }
    .result pre {
      background: var(--code);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      overflow: auto;
    }

    .messages {
      flex: 1;
      overflow: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .message {
      max-width: 82%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 13px;
      font-size: 14px;
      line-height: 1.45;
      white-space: pre-wrap;
    }

    .message.user {
      align-self: flex-end;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }

    .message.agent {
      align-self: flex-start;
      background: #fff;
    }

    .message.error {
      align-self: flex-start;
      background: #fff5f3;
      border-color: #efb8ad;
      color: #8a2f22;
    }

    .composer {
      border-top: 1px solid var(--line);
      padding: 14px;
      background: #fff;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
    }

    textarea {
      width: 100%;
      min-height: 52px;
      max-height: 180px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 11px 12px;
      font: inherit;
      line-height: 1.35;
      color: var(--text);
    }

    .status {
      padding: 8px 20px;
      min-height: 33px;
      color: var(--muted);
      font-size: 12px;
      border-top: 1px solid var(--line);
      background: #fff;
    }

    .run-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 12px;
    }

    .pill {
      background: var(--soft);
      color: var(--accent-dark);
      border: 1px solid #c6dedc;
      border-radius: 999px;
      padding: 4px 8px;
    }

    @media (max-width: 820px) {
      body { overflow: auto; }
      .app {
        grid-template-columns: 1fr;
        height: auto;
        min-height: 100vh;
      }
      .document {
        min-height: 48vh;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .chat { min-height: 52vh; }
      .result { padding: 22px; }
      .message { max-width: 94%; }
    }
  </style>
</head>
<body>
  <main class="app">
    <section class="document">
      <header>
        <div class="title">
          <h1>Result Document</h1>
          <p id="version">No run yet</p>
        </div>
        <nav class="doc-actions">
          <a id="pdfLink" href="#" hidden target="_blank" rel="noreferrer">PDF</a>
          <a id="traceLink" href="#" hidden target="_blank" rel="noreferrer">Trace</a>
        </nav>
      </header>
      <article id="result" class="result">
        <p class="empty">Ask the proposal agent a question. The final answer will appear here as the current document version.</p>
      </article>
    </section>

    <section class="chat">
      <header>
        <div class="title">
          <h1>DAIMON Proposal Agent</h1>
          <p>Chat with the work-package assistant</p>
        </div>
      </header>
      <div id="messages" class="messages"></div>
      <form id="composer" class="composer">
        <textarea id="input" name="message" placeholder="create a draft of WP2" required></textarea>
        <button id="send" class="primary" type="submit">Send</button>
      </form>
      <div id="status" class="status">Ready</div>
    </section>
  </main>

  <script>
    const messages = document.getElementById("messages");
    const form = document.getElementById("composer");
    const input = document.getElementById("input");
    const send = document.getElementById("send");
    const statusEl = document.getElementById("status");
    const resultEl = document.getElementById("result");
    const versionEl = document.getElementById("version");
    const pdfLink = document.getElementById("pdfLink");
    const traceLink = document.getElementById("traceLink");

    function escapeHtml(value) {
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function inlineMarkdown(text) {
      let html = escapeHtml(text);
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
      return html;
    }

    function markdownToHtml(markdown) {
      const lines = markdown.split(/\r?\n/);
      const html = [];
      let list = null;
      let inCode = false;
      let code = [];

      function closeList() {
        if (list) {
          html.push(`</${list}>`);
          list = null;
        }
      }

      for (const raw of lines) {
        const line = raw.trimEnd();
        if (line.trim().startsWith("```")) {
          if (inCode) {
            html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
            code = [];
            inCode = false;
          } else {
            closeList();
            inCode = true;
          }
          continue;
        }
        if (inCode) {
          code.push(line);
          continue;
        }
        if (!line.trim()) {
          closeList();
          continue;
        }

        const heading = line.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
          closeList();
          const level = heading[1].length;
          html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }

        const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
        if (bullet) {
          if (list !== "ul") {
            closeList();
            html.push("<ul>");
            list = "ul";
          }
          html.push(`<li>${inlineMarkdown(bullet[1])}</li>`);
          continue;
        }

        const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
        if (numbered) {
          if (list !== "ol") {
            closeList();
            html.push("<ol>");
            list = "ol";
          }
          html.push(`<li>${inlineMarkdown(numbered[1])}</li>`);
          continue;
        }

        closeList();
        html.push(`<p>${inlineMarkdown(line)}</p>`);
      }

      closeList();
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      }
      return html.join("");
    }

    function addMessage(kind, text) {
      const node = document.createElement("div");
      node.className = `message ${kind}`;
      node.textContent = text;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
    }

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setResult(data) {
      const runId = data.artifacts?.run_id || "run";
      const meta = [
        data.intent ? `<span class="pill">${escapeHtml(data.intent)}</span>` : "",
        data.selected_skill ? `<span class="pill">${escapeHtml(data.selected_skill)}</span>` : "",
        data.review_status ? `<span class="pill">${escapeHtml(data.review_status)}</span>` : ""
      ].join("");
      resultEl.innerHTML = `<div class="run-meta">${meta}</div>${markdownToHtml(data.answer || "")}`;
      versionEl.textContent = runId;

      if (data.artifact_urls?.answer_pdf) {
        pdfLink.href = data.artifact_urls.answer_pdf;
        pdfLink.hidden = false;
      }
      if (data.artifact_urls?.trace_md) {
        traceLink.href = data.artifact_urls.trace_md;
        traceLink.hidden = false;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;

      addMessage("user", message);
      input.value = "";
      send.disabled = true;
      setStatus("Running agent...");

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Agent run failed");
        }
        addMessage("agent", data.answer || "(empty answer)");
        setResult(data);
        setStatus(`Saved logs in ${data.artifacts.run_dir}`);
      } catch (error) {
        addMessage("error", error.message);
        setStatus("Error");
      } finally {
        send.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""


def artifact_url(path: str) -> str | None:
    if not path:
        return None
    try:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(LOGS_DIR.resolve())
    except ValueError:
        return None
    return "/runs/" + "/".join(relative.parts)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/runs/"):
            relative = unquote(self.path.removeprefix("/runs/"))
            target = (LOGS_DIR / relative).resolve()
            try:
                target.relative_to(LOGS_DIR.resolve())
            except ValueError:
                self.send_error(403)
                return
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            content_type = "application/octet-stream"
            if target.suffix == ".pdf":
                content_type = "application/pdf"
            elif target.suffix == ".md":
                content_type = "text/markdown; charset=utf-8"
            elif target.suffix == ".json":
                content_type = "application/json; charset=utf-8"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            message = (payload.get("message") or "").strip()
            if not message:
                self.send_json(400, {"error": "Message is required."})
                return

            result = run_agent_task(
                message,
                max_attempts=int(payload.get("max_attempts") or 2),
                rebuild_memory=False,
            )
            artifacts = result["artifacts"]
            result["artifact_urls"] = {
                "answer_pdf": artifact_url(artifacts.get("answer_pdf")),
                "answer_md": artifact_url(artifacts.get("answer_md")),
                "trace_md": artifact_url(artifacts.get("trace_md")),
                "trace_json": artifact_url(artifacts.get("trace_json")),
            }
            self.send_json(200, result)
        except DocumentExtractionError as exc:
            self.send_json(
                500,
                {
                    "error": "Document extraction failed. Rebuild memory after fixing source conversion.",
                    "details": str(exc),
                },
            )
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})


def parse_args():
    parser = argparse.ArgumentParser(description="DAIMON proposal agent web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main():
    args = parse_args()
    load_env_file(AGENT_DIR / ".env")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"DAIMON proposal agent UI: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
