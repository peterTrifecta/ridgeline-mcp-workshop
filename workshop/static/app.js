/* The projector chat page. No build step, no npm, no CDN — it has to work
   offline in a conference room. */

const el = (id) => document.getElementById(id);

const transcript = el("transcript");
const input = el("input");
const sendBtn = el("send");
const toolsToggle = el("tools-toggle");
const toolsLabel = el("tools-label");
const banner = el("banner");

let busy = false;

/* ---------- a very small markdown renderer ---------- */

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}

function renderMarkdown(src) {
  const lines = src.split("\n");
  let html = "";
  let i = 0;

  const isTableSep = (s) => /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(s) && s.includes("-");
  const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i++; continue; }

    // table
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      let body = "";
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        body += "<tr>" + cells(lines[i]).map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        i++;
      }
      html += "<table><thead><tr>" +
        head.map((c) => `<th>${inline(c)}</th>`).join("") +
        `</tr></thead><tbody>${body}</tbody></table>`;
      continue;
    }

    // heading
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      html += `<h${level}>${inline(heading[2])}</h${level}>`;
      i++;
      continue;
    }

    // lists
    if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const tag = ordered ? "ol" : "ul";
      let items = "";
      while (i < lines.length &&
             (ordered ? /^\s*\d+[.)]\s+/.test(lines[i]) : /^\s*[-*+]\s+/.test(lines[i]))) {
        items += `<li>${inline(lines[i].replace(/^\s*(?:[-*+]|\d+[.)])\s+/, ""))}</li>`;
        i++;
      }
      html += `<${tag}>${items}</${tag}>`;
      continue;
    }

    // paragraph
    let para = [];
    while (i < lines.length && lines[i].trim() &&
           !/^\s*[-*+]\s+/.test(lines[i]) && !/^#{1,6}\s/.test(lines[i]) &&
           !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
      para.push(lines[i]);
      i++;
    }
    html += `<p>${inline(para.join("\n")).replace(/\n/g, "<br>")}</p>`;
  }
  return html;
}

/* ---------- transcript ---------- */

function clearEmpty() {
  const empty = el("empty-state");
  if (empty) empty.remove();
}

function atBottom() {
  return transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 120;
}

function scroll(force) {
  if (force || atBottom()) transcript.scrollTop = transcript.scrollHeight;
}

function addTurn(className, html) {
  clearEmpty();
  const node = document.createElement("div");
  node.className = `turn ${className}`;
  node.innerHTML = html;
  transcript.appendChild(node);
  scroll(true);
  return node;
}

function formatArgs(args) {
  return Object.entries(args || {})
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
}

function addToolCall(name, args) {
  const node = addTurn("tool", "");
  node.innerHTML = `
    <div class="tool-line"><span class="lead">Claude is using:</span>
      <span class="tool-name">${escapeHtml(name)}</span>(${escapeHtml(formatArgs(args))})</div>
    <button class="tool-toggle">&#9656; show what came back</button>
    <pre class="tool-result hidden"></pre>`;
  const toggle = node.querySelector(".tool-toggle");
  const result = node.querySelector(".tool-result");
  toggle.addEventListener("click", () => {
    const hidden = result.classList.toggle("hidden");
    toggle.innerHTML = hidden ? "&#9656; show what came back" : "&#9662; hide";
    scroll(false);
  });
  return node;
}

function prettyJson(text) {
  try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
}

/* ---------- header state ---------- */

async function refreshState(applyToggle) {
  const state = await (await fetch("/api/state")).json();
  el("step-label").textContent = state.label;
  el("tools-live").textContent =
    state.tool_count === 1 ? "1 tool live" : `${state.tool_count} tools live`;

  const empty = el("empty-title");
  if (empty) {
    empty.textContent = state.label;
    el("empty-about").textContent = state.about;
  }
  if (applyToggle) setTools(state.tools_default);
  if (state.mcp_error) {
    banner.textContent = `The Ridgeline MCP server did not start: ${state.mcp_error}`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
  return state;
}

function setTools(on) {
  toolsToggle.checked = on;
  toolsLabel.textContent = on ? "Tools on" : "Tools off";
}

toolsToggle.addEventListener("change", () => setTools(toolsToggle.checked));

/* ---------- actions ---------- */

el("new-btn").addEventListener("click", async () => {
  const button = el("new-btn");
  button.disabled = true;
  button.textContent = "Restarting…";
  try {
    await fetch("/api/new", { method: "POST" });
    transcript.innerHTML =
      `<div class="empty" id="empty-state">
         <p class="empty-title" id="empty-title"></p>
         <p class="empty-about" id="empty-about"></p>
       </div>`;
    await refreshState(true);
  } finally {
    button.disabled = false;
    button.textContent = "New conversation";
  }
});

el("wire-btn").addEventListener("click", async () => {
  const panel = el("wire");
  if (!panel.classList.contains("hidden")) { panel.classList.add("hidden"); return; }
  const data = await (await fetch("/api/tools")).json();
  el("wire-body").textContent = JSON.stringify(data.tools, null, 2);
  panel.classList.remove("hidden");
});
el("wire-close").addEventListener("click", () => el("wire").classList.add("hidden"));

let zoom = 19;
const setZoom = (v) => {
  zoom = Math.min(32, Math.max(14, v));
  document.documentElement.style.setProperty("--base", `${zoom}px`);
};
el("zoom-in").addEventListener("click", () => setZoom(zoom + 2));
el("zoom-out").addEventListener("click", () => setZoom(zoom - 2));

/* ---------- sending ---------- */

el("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  send();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    send();
  }
});

async function send() {
  const message = input.value.trim();
  if (!message || busy) return;

  busy = true;
  sendBtn.disabled = true;
  input.value = "";
  addTurn("user", escapeHtml(message).replace(/\n/g, "<br>"));

  const pending = addTurn("assistant thinking", "Claude is thinking…");
  let answer = null;
  let text = "";
  const tools = {};

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, use_tools: toolsToggle.checked }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        if (!chunk.startsWith("data: ")) continue;
        const event = JSON.parse(chunk.slice(6));

        if (event.type === "text_delta") {
          if (pending.parentNode) pending.remove();
          if (!answer) answer = addTurn("assistant", "");
          text += event.text;
          answer.innerHTML = renderMarkdown(text);
          scroll(false);
        } else if (event.type === "tool_call") {
          if (pending.parentNode) pending.remove();
          answer = null;
          text = "";
          tools[event.id] = addToolCall(event.name, event.input);
        } else if (event.type === "tool_result") {
          const node = tools[event.id];
          if (node) {
            node.querySelector(".tool-result").textContent = prettyJson(event.result);
            if (event.is_error) node.classList.add("is-error");
          }
        } else if (event.type === "error") {
          if (pending.parentNode) pending.remove();
          addTurn("turn-error", escapeHtml(event.message));
          answer = null;
          text = "";
        }
      }
    }
  } catch (error) {
    addTurn("turn-error", escapeHtml(`Could not reach the chat backend: ${error}`));
  } finally {
    if (pending.parentNode) pending.remove();
    busy = false;
    sendBtn.disabled = false;
    input.focus();
    refreshState(false);
  }
}

refreshState(true);
