import json
import time as _time

CHARS_PER_TOKEN = 4
DEFAULT_BUFFER = 20_000
DEFAULT_KEEP_TOKENS = 8_000
SUMMARY_OUTPUT_TOKENS = 4_096
TOOL_OUTPUT_MAX_CHARS = 2_000


def _cdbg(msg):
    try:
        import os as _os
        from src.elwand_paths import logs_dir as _logs_dir
        p = _os.path.join(_logs_dir(), "debugging_logs")
        _os.makedirs(_os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(f"{_time.strftime('%H:%M:%S')}  [compact] {msg}\n")
    except (PermissionError, OSError):
        pass

CHARS_PER_TOKEN = 4
DEFAULT_BUFFER = 20_000
DEFAULT_KEEP_TOKENS = 8_000
SUMMARY_OUTPUT_TOKENS = 4_096
TOOL_OUTPUT_MAX_CHARS = 2_000

SUMMARY_TEMPLATE = """Output exactly the Markdown structure inside <template> and keep the section order unchanged. Do not include the <template> tags in your response.
<template>
## Goal
- [single-sentence task summary]

## Constraints & Preferences
- [user constraints, preferences, specs, or "(none)"]

## Targets Discovered
- [machines, domains, subdomains or "(none)"]

## Credentials & Access
- [usernames, passwords, hashes, access obtained or "(none)"]

## Progress
### Done
- [completed work or "(none)"]

### In Progress
- [current work or "(none)"]

### Blocked
- [blockers or "(none)"]

## Key Findings
- [vulnerabilities, interesting services, versions, or "(none)"]

## Previously Fetched URLs
- [list webfetch'd URLs and why they were fetched, or "(none)"]

## Search Queries Made
- [list websearch queries and what was found, or "(none)"]

## Cache Files Available
- [list caché filenames from the context below if a cache/ listing is provided, or "(none)"]

## Next Steps
- [ordered next actions or "(none)"]
</template>

Rules:
- Keep every section, even when empty.
- Use terse bullets, not prose paragraphs.
- Preserve exact IPs, usernames, URLs, file paths, error strings, and identifiers when known.
- Do not mention the summary process or that context was compacted."""

COMPACTION_SYSTEM = (
    "You are an anchored context summarization assistant for penetration testing sessions.\n\n"
    "Summarize only the conversation history you are given. The newest turns may be kept "
    "verbatim outside your summary, so focus on the older context that still matters for "
    "continuing the work.\n\n"
    "If the prompt includes a <previous-summary> block, treat it as the current anchored "
    "summary. Update it with the new history by preserving still-true details, removing "
    "stale details, and merging in new facts.\n\n"
    "Always follow the exact output structure requested by the user prompt. Keep every "
    "section, preserve exact IPs and identifiers when known, and prefer terse bullets "
    "over paragraphs.\n\n"
    "Do not answer the conversation itself. Do not mention that you are summarizing, "
    "compacting, or merging context."
)


def estimate_tokens(text):
    return max(1, len(text) // CHARS_PER_TOKEN)


def _truncate(text):
    if isinstance(text, str) and len(text) > TOOL_OUTPUT_MAX_CHARS:
        _cdbg(f"truncate tool_output orig_len={len(text)} truncated_len={TOOL_OUTPUT_MAX_CHARS}")
        return text[:TOOL_OUTPUT_MAX_CHARS] + "\n[truncated]"
    return str(text)


def _msg_attr(msg, key, default=None):
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _serialize_message(msg):
    role = _msg_attr(msg, "role", "")
    content = _msg_attr(msg, "content")
    msg_type = type(msg).__name__
    content_len = len(str(content or ""))
    has_tc = bool(_msg_attr(msg, "tool_calls"))
    _cdbg(f"serialize role={role} type={msg_type} content_len={content_len} has_tool_calls={has_tc}")

    if role == "user":
        return "[User]: " + (content or "")

    if role == "assistant":
        parts = []
        if content:
            parts.append("[Assistant]: " + str(content))
        tool_calls = _msg_attr(msg, "tool_calls")
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                else:
                    fn = getattr(tc, "function", None)
                    fn = {"name": getattr(fn, "name", "?"), "arguments": getattr(fn, "arguments", "{}")}
                name = fn.get("name", "?") if isinstance(fn, dict) else "?"
                try:
                    args_str = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
                    if isinstance(args_str, str):
                        args = json.loads(args_str)
                    else:
                        args = args_str
                except Exception:
                    args = args_str
                parts.append(f"[Assistant tool call]: {name}({json.dumps(args)})")
        return "\n".join(parts)

    if role == "tool":
        output = _truncate(str(content or ""))
        return f"[Tool result]: {output}"

    if role == "system":
        if _msg_attr(msg, "_is_compaction"):
            return None
        return "[System]: " + str(content or "")

    return None


def _find_compaction(messages):
    for i in range(len(messages) - 1, -1, -1):
        if _msg_attr(messages[i], "_is_compaction"):
            return i
    return None


def select_messages(messages, keep_tokens):
    conversation = []
    compaction_idx = _find_compaction(messages)
    start = compaction_idx + 1 if compaction_idx is not None else 0
    total_msgs = len(messages)

    for msg in messages[start:]:
        serialized = _serialize_message(msg)
        if serialized:
            conversation.append(serialized)

    _cdbg(f"select total_msgs={total_msgs} start={start} conv_count={len(conversation)} keep_tokens={keep_tokens} has_prev_compaction={compaction_idx is not None}")

    if not conversation:
        _cdbg("select no_conversation")
        return None, None, 0

    total = 0
    split = len(conversation)
    split_prefix = ""
    split_suffix = ""

    for i in range(len(conversation) - 1, -1, -1):
        next_tokens = estimate_tokens(conversation[i])
        if total + next_tokens > keep_tokens:
            remaining = max(0, keep_tokens - total) * CHARS_PER_TOKEN
            if remaining > 0:
                split_prefix = conversation[i][:-remaining]
                split_suffix = conversation[i][-remaining:]
                split = i + 1
            break
        total += next_tokens
        split = i

    for i in range(split, len(conversation)):
        line = conversation[i]
        if line.startswith("[User]:") or line.startswith("[Assistant"):
            split = i
            split_prefix = ""
            split_suffix = ""
            break
    else:
        split = len(conversation)
        split_prefix = ""
        split_suffix = ""

    head = "\n\n".join(
        conversation[:split] + ([split_prefix] if split_prefix else [])
    )
    recent = "\n\n".join(
        ([split_suffix] if split_suffix else []) + conversation[split:]
    )

    _cdbg(f"select result head_chars={len(head)} recent_chars={len(recent)} split={split} split_idx={split + start} kept_tokens={total}")
    return head, recent, split + start


def build_summary_prompt(previous_summary=None, head_messages=None):
    parts = []
    if previous_summary:
        parts.append(
            "Update the anchored summary below using the conversation history above.\n"
            "Preserve still-true details, remove stale details, and merge in the new facts.\n"
            f"<previous-summary>\n{previous_summary}\n</previous-summary>"
        )
    else:
        parts.append("Create a new anchored summary from the conversation history.")
    parts.append(SUMMARY_TEMPLATE)
    if head_messages:
        parts.append(head_messages)
    return "\n\n".join(parts)


def usable_context(model_context_limit, output_max_tokens, buffer=None):
    if model_context_limit <= 0:
        return 0
    buf = buffer if buffer is not None else DEFAULT_BUFFER
    reserved = min(buf, output_max_tokens) if output_max_tokens > 0 else buf
    return max(0, model_context_limit - reserved)


def is_overflow(tokens_used, model_context_limit, buffer=None):
    if model_context_limit <= 0:
        return False
    buf = buffer if buffer is not None else DEFAULT_BUFFER
    return tokens_used >= model_context_limit - buf


def _list_cache_files(messages):
    cache_map = {}
    for i, m in enumerate(messages):
        tc_id = _msg_attr(m, "tool_call_id")
        content = _msg_attr(m, "content") or ""
        if not isinstance(content, str):
            continue
        if tc_id and "read_cache" in content:
            import re
            match = re.search(r'read_cache\("([^"]+)"\)', content)
            if match:
                fname = match.group(1)
                if fname not in cache_map:
                    cache_map[fname] = _find_tool_url(messages, i, tc_id)
    try:
        import os as _os
        from src.elwand_paths import cache_dir
        d = str(cache_dir())
        if not _os.path.isdir(d):
            return None
        files = sorted(
            f for f in _os.listdir(d) if _os.path.isfile(_os.path.join(d, f))
        )[:30]
        result = []
        for f in files:
            size = _os.path.getsize(_os.path.join(d, f))
            url = cache_map.get(f, "")
            if url:
                result.append((f, f"{f} — {url} ({size} bytes)"))
            else:
                result.append((f, f"{f} ({size} bytes)"))
        return result
    except Exception:
        return None


def _find_tool_url(messages, tool_idx, tool_call_id):
    for i in range(max(0, tool_idx - 20), min(len(messages), tool_idx + 1)):
        m = messages[i]
        role = _msg_attr(m, "role")
        if role != "assistant":
            continue
        tc = _msg_attr(m, "tool_calls")
        if not tc:
            continue
        for t in tc:
            tid = _msg_attr(t, "id")
            if tid == tool_call_id:
                fn = _msg_attr(_msg_attr(t, "function", {}), "name", "")
                args = _msg_attr(_msg_attr(t, "function", {}), "arguments", "")
                if fn == "webfetch":
                    return _extract_url(args)
                if fn == "websearch":
                    return f'search: {_extract_query(args)}'
    return ""


def _extract_url(args_str):
    try:
        import json as _json
        if isinstance(args_str, str):
            args = _json.loads(args_str)
        else:
            args = args_str
        return args.get("url", "")[:120]
    except Exception:
        return ""


def _extract_query(args_str):
    try:
        import json as _json
        if isinstance(args_str, str):
            args = _json.loads(args_str)
        else:
            args = args_str
        return args.get("query", "")[:100]
    except Exception:
        return ""


def compact_messages(
    messages,
    client,
    model_context_limit,
    keep_tokens=None,
    buffer=None,
):
    keep = keep_tokens if keep_tokens is not None else DEFAULT_KEEP_TOKENS
    prev_idx = _find_compaction(messages)
    previous_summary = None
    previous_recent = None
    _cdbg(f"compact_msgs enter msgs={len(messages)} keep={keep} limit={model_context_limit} prev_compaction={prev_idx is not None}")
    if prev_idx is not None:
        previous_summary = messages[prev_idx].get("content", "")
        previous_recent = messages[prev_idx].get("_recent", "")
        _cdbg(f"compact_msgs prev_summary_len={len(previous_summary)} prev_recent_len={len(previous_recent or '')}")

    head, recent, split_idx = select_messages(messages, keep)
    if not head:
        _cdbg("compact_msgs skip: no head to summarize")
        return False

    _cdbg(f"compact_msgs head_chars={len(head)} recent_chars={len(recent)} split_idx={split_idx}")

    context_parts = []
    if previous_recent:
        context_parts.append(previous_recent)
    if head:
        context_parts.append(head)
    if not context_parts:
        _cdbg("compact_msgs skip: empty context_parts")
        return False

    summary_prompt = build_summary_prompt(
        previous_summary=previous_summary,
        head_messages="\n\n".join(context_parts),
    )

    cache_files = _list_cache_files(messages)
    if cache_files:
        cache_list = "Cache files currently available:\n" + "\n".join(
            label for _, label in cache_files)
        summary_prompt += "\n\n" + cache_list
        _cdbg(f"compact_msgs cache_list={len(cache_files)} files")

    usable = usable_context(model_context_limit, SUMMARY_OUTPUT_TOKENS, buffer)
    prompt_tokens = estimate_tokens(summary_prompt)
    _cdbg(f"compact_msgs prompt_chars={len(summary_prompt)} prompt_tokens={prompt_tokens} usable={usable} limit_check={usable - SUMMARY_OUTPUT_TOKENS}")
    if prompt_tokens > usable - SUMMARY_OUTPUT_TOKENS:
        _cdbg("compact_msgs skip: prompt too large for context")
        return False

    _cdbg(f"compact_msgs llm_call start prompt_chars={len(summary_prompt)}")
    t0 = _time.monotonic()
    try:
        resp = client.chat([
            {"role": "system", "content": COMPACTION_SYSTEM},
            {"role": "user", "content": summary_prompt},
        ])
        summary = resp.choices[0].message.content if resp and resp.choices else ""
        elapsed = _time.monotonic() - t0
        _cdbg(f"compact_msgs llm_done summary_len={len(summary)} elapsed={elapsed:.2f}s")
    except Exception as e:
        elapsed = _time.monotonic() - t0
        _cdbg(f"compact_msgs llm_error: {type(e).__name__} after {elapsed:.2f}s")
        return False

    if not summary or not summary.strip():
        _cdbg("compact_msgs skip: empty summary from LLM")
        return False

    context_msgs = [m for m in messages if _msg_attr(m, "_is_context")]
    new_messages = list(context_msgs)
    new_messages.append({
        "role": "system",
        "content": summary,
        "_is_compaction": True,
        "_recent": recent,
    })
    tail_count = len(messages[split_idx:])
    new_messages.extend(messages[split_idx:])

    _cdbg(f"compact_msgs rebuild context_msgs={len(context_msgs)} tail_msgs={tail_count} total_new={len(new_messages)}")

    messages.clear()
    messages.extend(new_messages)
    _cdbg(f"compact_msgs done final_len={len(messages)}")
    return True
