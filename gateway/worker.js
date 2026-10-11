/**
 * token-cost-optimizer gateway — Cloudflare Worker
 *
 * A transparent proxy for OpenAI-compatible chat APIs. It compresses the
 * bulky parts of your prompts (tool outputs, logs, JSON dumps, pasted HTML)
 * before forwarding the request upstream. Your client only changes base_url.
 *
 * What it will NOT do:
 *  - rewrite prompts or change their meaning (noise removal only)
 *  - store your API key (forwarded, never persisted)
 *  - compress small messages (below MIN_COMPRESS_CHARS, passed through)
 *  - compress when savings are negligible (< MIN_SAVINGS_RATIO, passed through)
 *
 * Ports of the Python toolkit (~/scripts):
 *  - estimateTokens  <- estimate_tokens.py  (chars/3.8 heuristic, CJK/1.3)
 *  - cleanLog        <- clean_log.py        (ANSI/progress/UUID/dedup)
 *  - compressJson    <- compress_json.py    (schema + one sample)
 *  - pruneHtml       <- prune_dom.py        (regex port; HTMLRewriter upgrade later)
 *  - pruneCodeLight  <- prune_code.py       (generic regex path only, heuristic)
 */

const MIN_COMPRESS_CHARS = 2000;   // don't touch small messages
const MIN_SAVINGS_RATIO = 0.20;    // pass through if we can't save >=20%

/* ---------------- token estimation (port of estimate_tokens.py) ---------------- */
function estimateTokens(text) {
  let cjk = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp >= 0x4e00 && cp <= 0x9fff) cjk++;
  }
  const other = [...text].length - cjk;
  return Math.max(1, Math.floor(cjk / 1.3 + other / 3.8));
}

/* ---------------- log denoising (port of clean_log.py) ---------------- */
function cleanLog(text) {
  let clean = text
    // ANSI escape sequences (real bytes and literal forms)
    .replace(/(\x1B|\\u001b|\\033)(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, "")
    // UUID -> <uuid>, long hex -> <hash> (also desensitizes)
    .replace(/\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b/g, "<uuid>")
    .replace(/\b[0-9a-fA-F]{32,}\b/g, "<hash>")
    // timestamps -> <ts> (relative order is what matters when debugging)
    .replace(/\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?/g, "<ts>");

  const skip = [
    /^\s*[\d.]+\s*kB\s*[\d.]+\s*kB\/s/,          // download speeds
    /^\s*[-/\\]\s*fetching/i,
    /^\s*npm\s+http\s+fetch/i,
    /^\s*Downloading\s+/i,
    /\[=*>*[\s\-*]*\]/,                            // progress bars
    /\[PROGRESS\]/i,
    /^\s*\[\s*\d+%\s*\]/,                         // percentages
    /^\s*[\d.]+\s*%\s*\(\d+\/\d+\s*modules?\s*downloaded\)/i,
  ];

  const lines = clean.split("\n").filter((l) => !skip.some((p) => p.test(l)));

  // collapse blank runs
  const compact = [];
  let lastEmpty = false;
  for (const l of lines) {
    if (!l.trim()) { if (!lastEmpty) { compact.push(l); lastEmpty = true; } }
    else { compact.push(l); lastEmpty = false; }
  }

  // fold repeated lines: "line [xN]"
  const deduped = [];
  for (let i = 0; i < compact.length;) {
    let j = i + 1;
    while (j < compact.length && compact[j] === compact[i]) j++;
    const n = j - i;
    if (n > 2 && compact[i].trim()) deduped.push(`${compact[i]}  [x${n}]`);
    else for (let k = i; k < j; k++) deduped.push(compact[k]);
    i = j;
  }

  // still huge? keep head + tail (errors live at the edges)
  if (deduped.length > 250) {
    return [...deduped.slice(0, 100),
      `... [omitted ${deduped.length - 200} middle lines to save tokens] ...`,
      ...deduped.slice(-100)].join("\n");
  }
  return deduped.join("\n");
}

/* ---------------- JSON -> schema + sample (port of compress_json.py) ---------------- */
function summarizeJson(data, depth = 0, keepSample = false) {
  const MAX_DEPTH = 3;
  if (depth > MAX_DEPTH) return "...";
  if (Array.isArray(data)) {
    if (!data.length) return [];
    return [summarizeJson(data[0], depth + 1, keepSample), `... (${data.length} total items)`];
  }
  if (data !== null && typeof data === "object") {
    const out = {};
    const keys = Object.keys(data);
    for (const k of keys.slice(0, 15)) out[k] = summarizeJson(data[k], depth + 1, keepSample);
    if (keys.length > 15) out["_total_keys_count"] = keys.length;
    return out;
  }
  if (keepSample) {
    if (typeof data === "string" && data.length > 120) return data.slice(0, 117) + "...";
    return data;
  }
  if (data === null) return "null";
  if (Array.isArray(data)) return "array";
  return typeof data; // "string" | "number" | "boolean"
}

function compressJson(text, keepSample = false) {
  const data = JSON.parse(text); // throws if not JSON — caller handles
  return JSON.stringify(summarizeJson(data, 0, keepSample), null, 2);
}

/* ---------------- HTML pruning (simplified port of prune_dom.py) ----------------
 * The Python version builds an interactive element tree with HTMLParser.
 * This port does the high-value cheap passes with regex: strip scripts,
 * styles, svg, comments, base64, then collapse to text + interactive tags.
 * A streaming HTMLRewriter version would be more precise — future upgrade.
 */
function pruneHtml(html) {
  let t = html
    .replace(/<!--[\s\S]*?-->/g, "")                                   // comments
    .replace(/<script[\s\S]*?<\/script>/gi, "")                         // scripts
    .replace(/<style[\s\S]*?<\/style>/gi, "")                           // styles
    .replace(/<svg[\s\S]*?<\/svg>/gi, "")                              // svg
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, "")
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
    .replace(/data:[a-zA-Z0-9/+\-.;=]+;base64,[a-zA-Z0-9+/=]+/g, "data:...[base64]")
    .replace(/\sstyle="[^"]{80,}"/gi, ' style="..."')                   // long inline styles
    .replace(/<img\b[^>]*>/gi, " [image] ");                            // images -> marker (base64 already neutralized)

  // keep interactive elements with their key attributes, drop the rest to text
  const keepAttrs = ["id", "name", "type", "placeholder", "role", "aria-label", "href", "value", "data-testid", "title", "alt", "action"];
  const lines = [];
  const tagRe = /<(button|input|textarea|select|option|a|form|label)\b([^>]*)>([^<]{0,80})/gi;
  let m, n = 0;
  while ((m = tagRe.exec(t)) && n < 300) {
    n++;
    const attrs = [];
    const attrRe = /([\w-:]+)="([^"]{0,80})"/g;
    let am;
    while ((am = attrRe.exec(m[2]))) {
      if (keepAttrs.includes(am[1].toLowerCase())) attrs.push(`${am[1]}="${am[2]}"`);
    }
    const text = m[3].trim().replace(/\s+/g, " ");
    lines.push(`<${m[1]}${attrs.length ? " " + attrs.join(" ") : ""}>${text ? " " + text : ""}`);
  }
  const textOnly = t.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 4000);
  return `# [pruned HTML: ${n} interactive elements]\n${lines.join("\n")}\n\n# [page text, truncated]\n${textOnly}`;
}

/* ---------------- light code pruning (generic path of prune_code.py) ----------------
 * The Python AST version can't run here; this is the same regex fallback the
 * original uses for non-Python files. Honest about it: heuristic, not AST.
 */
function pruneCodeLight(code) {
  const kws = ["class ", "function ", "def ", "interface ", "type ", "export ", "public ", "private ", "const ", "let ", "var ", "fn ", "func "];
  return code.split("\n")
    .filter((l) => kws.some((k) => l.trim().startsWith(k)))
    .join("\n");
}

/* Find a JSON block embedded in prose ("here's the output:\n{...}").
 * Scans for balanced brackets from the first { or [, respecting strings. */
function extractJsonBlock(text) {
  const i1 = text.indexOf("{");
  const i2 = text.indexOf("[");
  if (i1 === -1 && i2 === -1) return null;
  const start = (i1 === -1) ? i2 : (i2 === -1) ? i1 : Math.min(i1, i2);
  const open = text[start];
  const close = open === "{" ? "}" : "]";
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
    else if (ch === open) depth++;
    else if (ch === close && --depth === 0) {
      const candidate = text.slice(start, i + 1);
      try { return { start, end: i + 1, parsed: JSON.parse(candidate) }; }
      catch { return null; }
    }
  }
  return null;
}

/* ---------------- type detection + dispatch ---------------- */
function detectType(text) {
  const t = text.trim();
  // structural signals first — a 200-line code file must not be mistaken for a log
  if ((t.startsWith("{") && t.endsWith("}")) || (t.startsWith("[") && t.endsWith("]"))) {
    try { JSON.parse(t); return "json"; } catch { /* not JSON */ }
  }
  if (/<html|<!doctype html|<body/i.test(t) && (t.match(/</g) || []).length > 10) return "html";
  if (/^(class |def |function |import |from |const |let |var |#include |package |public |private )/m.test(t)) return "code";
  // log: needs an actual log signal, not just "many lines"
  if (/^(\x1B\[|Downloading |npm http |\[=+>|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|Traceback|Error:|WARN|INFO)/m.test(t)) return "log";
  return "text";
}

function compressContent(content, keepSample = true) {
  if (typeof content !== "string" || content.length < MIN_COMPRESS_CHARS) {
    return { text: content, saved: 0, type: "passthrough" };
  }
  const type = detectType(content);
  let compressed = content;
  let ctype = type;
  try {
    if (type === "json") compressed = compressJson(content, keepSample);
    else if (type === "html") compressed = pruneHtml(content);
    else if (type === "log") compressed = cleanLog(content);
    else if (type === "code") compressed = pruneCodeLight(content);
    else {
      // prose-wrapped JSON, the common agent tool-output shape
      const block = extractJsonBlock(content);
      if (block && block.end - block.start > MIN_COMPRESS_CHARS / 2) {
        const inner = JSON.stringify(summarizeJson(block.parsed, 0, keepSample), null, 2);
        compressed = content.slice(0, block.start) + inner + content.slice(block.end);
        ctype = "json-in-prose";
      } else {
        return { text: content, saved: 0, type: "passthrough" };
      }
    }
  } catch {
    return { text: content, saved: 0, type: "passthrough" }; // never break the request
  }
  const before = estimateTokens(content);
  const after = estimateTokens(compressed);
  const saved = before - after;
  if (saved / before < MIN_SAVINGS_RATIO) {
    return { text: content, saved: 0, type: "passthrough" }; // not worth it
  }
  return { text: compressed, saved, type: ctype };
}

/* ---------------- request handling ---------------- */
async function handleChatCompletions(request, env) {
  const upstream = (env.UPSTREAM_BASE_URL || "https://api.openai.com").replace(/\/$/, "");
  let body;
  try { body = await request.json(); }
  catch { return new Response("invalid JSON body", { status: 400 }); }

  let totalSaved = 0;
  const applied = [];
  if (Array.isArray(body.messages)) {
    body.messages = body.messages.map((msg, i) => {
      if (msg && typeof msg.content === "string") {
        const r = compressContent(msg.content);
        if (r.saved > 0) {
          totalSaved += r.saved;
          applied.push({ index: i, type: r.type, saved_tokens: r.saved });
          return { ...msg, content: r.text };
        }
      }
      return msg;
    });
  }

  const upstreamResp = await fetch(`${upstream}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // API key forwarded, never stored
      ...(request.headers.get("Authorization")
        ? { Authorization: request.headers.get("Authorization") } : {}),
    },
    body: JSON.stringify(body),
  });

  // pass through the upstream response, just add savings headers
  const headers = new Headers(upstreamResp.headers);
  headers.set("X-TCO-Saved-Tokens", String(totalSaved));
  headers.set("X-TCO-Compressed", applied.length ? JSON.stringify(applied) : "none");
  return new Response(upstreamResp.body, { status: upstreamResp.status, headers });
}

async function handleCompress(request) {
  let body;
  try { body = await request.json(); }
  catch { return new Response("invalid JSON body", { status: 400 }); }
  const text = body.text || "";
  const r = compressContent(text);
  return Response.json({
    type: r.type,
    original_chars: text.length,
    compressed_chars: r.text.length,
    estimated_tokens_before: estimateTokens(text),
    estimated_tokens_after: estimateTokens(r.text),
    tokens_saved: r.saved,
    compressed: r.text.slice(0, 8000),
    truncated: r.text.length > 8000,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/v1/chat/completions" && request.method === "POST") {
      return handleChatCompletions(request, env);
    }
    if (url.pathname === "/v1/compress" && request.method === "POST") {
      return handleCompress(request);
    }
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({
        ok: true,
        service: "token-cost-optimizer gateway",
        version: "0.1.0",
        endpoints: ["POST /v1/chat/completions", "POST /v1/compress"],
      });
    }
    return new Response("not found", { status: 404 });
  },
};

// export pure functions for node-based testing
export { estimateTokens, cleanLog, compressJson, pruneHtml, pruneCodeLight, detectType, extractJsonBlock, compressContent };
