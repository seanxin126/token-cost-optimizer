# token-cost-optimizer

Your LLM API bill has a leak. This plugs it.

If you run AI agents, you've seen it: a tool returns 40KB of JSON, a build log dumps 200 lines of progress bars, someone pastes an entire HTML page into the prompt. You pay per token for all of that noise.

token-cost-optimizer sits between your app and the LLM API and strips the noise before it costs you money.

## How it works

Point your OpenAI-compatible client at the gateway instead of the API directly:

```python
# before
client = OpenAI(base_url="https://api.openai.com/v1", api_key="sk-...")

# after — one line changes
client = OpenAI(base_url="https://your-gateway.workers.dev/v1", api_key="sk-...")
```

That's the integration. The gateway looks at each request, compresses the bulky parts (long tool results, logs, JSON blobs, HTML), and forwards everything else untouched. Every response comes back with a small report of what was saved.

Prefer to keep things local? There's also a CLI toolkit — 7 small Python scripts, no dependencies beyond Python 3.8:

```bash
./tco messy-response.json        # see what it would save, before you send it
./tco build.log compressed.log   # or write the result to a file
```

## Real numbers

Measured on real inputs:

| Input | Before | After | Saved |
|---|---|---|---|
| Python source → signature skeleton | 3,420 chars | 277 chars | 91.9% |
| Terminal build log → denoised | — | — | 63.5% |
| JSON API response → schema + sample | — | — | 70–98% |
| HTML page → readable content | — | — | 90–98% |

Ranges depend on how noisy your input is. If your prompts are already tight, there's nothing to strip — the tool will tell you that instead of pretending otherwise.

## What it doesn't do

Honesty up front, so nobody's disappointed later:

- **It doesn't rewrite your prompts.** It removes noise, not meaning. The model sees the same information, minus the padding.
- **Code compression on the gateway is heuristic.** The full AST-based version lives in the Python toolkit (`prune_code.py`). The gateway does a lighter pass — good enough for pasted snippets, not a replacement for the real thing.
- **It's not a cache.** If you want semantic caching, that's a different tool. This one shrinks what you send; it doesn't remember what you sent.
- **Chinese-social-media scripts are excluded from the gateway.** Two of the seven scripts (`compress_xhs_note.py`, `optimize_browser_context.py`) are built for Xiaohongshu automation — useful, but irrelevant here. They stay in the repo as-is.

## The gateway

One Cloudflare Worker. No server to run, no database, no queue.

- **Self-host:** deploy it yourself on Cloudflare's free tier. Takes about ten minutes. Your API keys never touch anyone else's infrastructure.
- **Hosted:** a managed version is planned at around $9/month for people who'd rather not touch wrangler. Not available yet — the open-source gateway comes first.

Your LLM API key goes in the request as usual; the gateway forwards it and never stores it. If that promise matters to you (it should), self-hosting is the answer.

## Repo layout

```
scripts/        the 7 Python compressors + tco entry point (offline toolkit)
gateway/        the Cloudflare Worker (JS port of the core compressors)
SKILL.md        the original role-prompt this project was born from (see below)
```

## Origin story

This started as a personal problem: I was running AI agents and watching tokens burn on log noise and bloated tool outputs. I asked an AI to act in a "skill" role and generate a set of compression scripts. It worked unreasonably well, so I kept using them, kept improving them, and eventually put a gateway in front so I wouldn't have to think about it at all.

`SKILL.md` is that original role-prompt, kept for provenance. An AI wrote the tool that saves you money on AI. Make of that what you will.

## License

MIT. Use it, fork it, sell it, whatever.
