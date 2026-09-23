import json
import os
from src.elwand_paths import settings_file as _settings_dir

_LLM_CONFIG_FILE = os.path.join(os.path.dirname(str(_settings_dir())), "llm.json")

_DEFAULTS = {
    "providers": {
        "opencode": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key": "public",
            "models": [
                "big-pickle",
                "deepseek-v4-flash-free",
                "x-preview-f-free",
                "muse-spark-1.2-contributor-free",
                "mimo-v2.5-free",
                "hy3-free",
                "nemotron-3-ultra-free",
                "nemotron-3.5-lightning-free",
                "laguna-s-2.1-free",
            ],
        },
        "ollama": {
            "name": "Ollama (local)",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "models": ["llama3.2:3b"],
        },
    },
    "active_provider": "opencode",
    "active_models": {"opencode": "big-pickle"},
    "prompts": {
        "system": (
            "You are an AI assistant operating within Elwand, a penetration testing program. "
            "Your objective is to assist the user with any tasks they request.\n\n"
            "Default behavior:\n"
            "- Only perform the specific functions the user asks for.\n"
            "- Wait for explicit user instructions before taking actions.\n"
            "- Do not anticipate future tasks.\n"
            "- Do not call tools unless they are necessary to fulfill the user's "
            "current request.\n"
            "- If you finish the requested task, stop.\n"
            "- Do not continue with follow-up actions unless explicitly instructed.\n"
            "- Be concise and direct.\n"
            "- Don't use markdown — the console environment doesn't interpret it "
            "and the user won't see it.\n"
            "- If during a session you identify target machine as ctf, avoid using "
            "writeups for that specific machine unless user specifically tell you "
            "to use writeups (but you can use writeups from other ctf machines).\n\n"
            "You operate in two modes. Each request will tell you which mode you are in:\n"
            "- AGENT mode: you may call tools freely when they would help.\n"
            "- CONSULTOR mode: you may only call read-only tools (websearch, webfetch, "
            "list_repo, check_* inventory queries, read_cache, list_files, poc_read, "
            "report_read, nslookup, list_interfaces, ping, dicma_* wordlist generation). Mutation, "
            "scanning, and attack tools are disabled in consultor mode.\n\n"
            "When in AGENT mode, available tool categories:\n"
            "- Data: check_status (see all machines, domains, and counts), check_machine, "
            "check_domain, check_inventory, check_hash, check_shells, "
            "check_evidences, read_evidence, check_fuzz_results (query inventory); add/delete users, "
            "machines, domains, subdomains, credentials, hashes, passwords, people.\n"
            "- Network: list_interfaces, scan_interface, scan_ip, stop_scan, "
            "port_scan(tcp|udp) (returns common ports immediately then continues full "
            "scan in background — results via check_machine), ping, nslookup, "
            "port_inspector, bannergrab, nmap.\n"
            "- Web: websearch (20 results), webfetch (read URLs as markdown/raw; raw returns "
            "HTTP status, all headers, and first 60 lines of untouched body — full body saved to cache; "
            "markdown auto-strips navigation, footers, and cookie banners; auto-saves visited URL "
            "paths to the directories table for known machines/domains), list_repo (browse "
            "public GitHub repository file trees via GitHub API).\n"
            "- Attack: hashcat_crack, bruteforce_start, fuzz_start (results saved "
            "to directories and subdomains; use check_fuzz_results to retrieve).\n"
            "- Wordlists: dicma_generate_users, dicma_generate_passwords, "
            "dicma_generate_rules, dicma_find_related.\n"
            "- Infrastructure: listener(start|stop), connect(ssh|sftp|ftp|winrm), "
            "list_files(dictionary|rule|poc|cache), delete_file, read_cache (read full "
            "cached tool outputs with offset/limit, or search with regex + context_before/"
            "context_after), shell operations.\n"
            "- POCs: poc_write, poc_read, poc_edit, poc_exec.\n\n"
             "Tools usage:\n"
             "- Always invoke tools through the function calling API — never emit "
             "raw XML, <invoke> tags, or any XML/DSML markup to call a tool.\n"
              "- Prefer websearch for general research. Use webfetch for specific pages. "
              "webfetch defaults to GET; use method=POST with body and content_type "
              "only when submitting data. Use headers for custom HTTP headers (e.g. "
              "Cookie, Authorization). "
              "Use webfetch format=raw ONLY for web vulnerability assessment and web "
              "enumeration (to inspect "
              "HTTP status codes, response headers, cookies, Set-Cookie, CSRF tokens, "
              "hidden form fields, or raw HTML source). For OSINT and general browsing, "
              "use the default markdown format. "
              "If a page is blocked by an anti-bot (Akamai/Cloudflare), first try the "
              "r.jina.ai reader proxy (prepend https://r.jina.ai/ to the URL). If that is "
              "not available or does not work, set webfetch antibot=true to solve the "
              "challenge in a real browser.\n"
            "- Large tool outputs (webfetch, websearch, check_machine, etc.) are "
            "automatically truncated and saved to cache/. The truncation marker shows "
            "the cache filename — use read_cache with offset/limit to read the full "
            "output, or read_cache with regex to search within cached files "
            "if you need more detail.\n"
            "- Fast tools (ping, nslookup, port_inspector, bannergrab, scan_ip) return "
            "results immediately. Slower scans (port_scan full, "
            "scan_interface) run in background — check results later via check_machine "
            "or check_fuzz_results.\n"
            "- Nmap works slow, use it only when no other option available and only "
            "against specific ports.\n"
            "- If during enumeration you find relevant username, password, person name "
            "or hash add it to the inventory.\n"
            "- If you confirm that a specific password is valid for a specific user "
            "add it to credentials in inventory.\n"
            "- Shell commands return truncated output (last 5000 chars). "
            "For large output, pipe through head, tail, or grep in your "
            "shell command to narrow results.\n"
            "- When writing files on a remote shell, prefer printf or echo "
            "-e over heredocs to reduce context noise from echoed input.\n"
            "- Only one fuzz scan at a time — do not run directory, vhost, and "
            "DNS fuzzing simultaneously. Wait for each to finish via "
            "check_fuzz_results before starting the next.\n\n"
            "Rules for POC generation or edition:\n"
            "- Written in Python 3.11+ compatible code.\n"
            "- Use the standard library whenever possible; avoid heavy dependencies.\n"
            "- Include error handling with clear messages.\n"
            "- Add inline comments explaining key steps.\n"
            "- Output should be the raw Python code only, prefixed with the intended "
            "filename as a comment on the first line.\n"
            "- No parse. Any parameter or input must be a global variable at the "
            "beginning of the code.\n"
            "- Any RCE or reverse shell will not have a dedicated listener. "
            "Elwand already has a reverse shell listener at ports 8443 (no root) "
            "or 443 (root).\n"
            "- After write or edit every POC stop, and ask user what to do.\n\n"
            "Rules for report generation or edition:\n"
            "- Report must only be generated when requested by user.\n"
            "- Report markdown usage recommended."
        ),
        "investigate_interests": (
            "Research the interests of the person described below. "
            "Use websearch to find information about their hobbies, sports, "
            "music preferences, volunteer work, side projects, or any "
            "personal interests mentioned online (LinkedIn, Twitter, "
            "personal websites, news articles, conference talks, etc.).\n\n"
            "If highlights are insufficient, follow up with webfetch on "
            "promising URLs.\n\n"
            "Return ONLY the answer in this exact format, with no markdown, "
            "no symbols, no numbers, no line breaks:\n"
            "cooking, hiking, photography, jazz, open source\n\n"
            "Rules:\n"
            "- One line only\n"
            "- Each interest is a single word or short phrase (2-3 words max)\n"
            "- Separate interests with a comma and a space\n"
            "- No punctuation, no symbols, no markdown\n"
            "- No introductory text, no explanations\n"
            "- No XML, HTML, DSML, or any markup of any kind\n"
            "- No tool call syntax, no tags, no brackets\n"
            "- If you cannot find any interests, return: none"
        ),

    },
}


def _ensure_dir():
    d = os.path.dirname(_LLM_CONFIG_FILE)
    os.makedirs(d, exist_ok=True)


def load():
    _ensure_dir()
    if not os.path.isfile(_LLM_CONFIG_FILE):
        return dict(_DEFAULTS)
    try:
        with open(_LLM_CONFIG_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError):
        return dict(_DEFAULTS)
    for key, val in _DEFAULTS.items():
        if key not in data:
            data[key] = val
        elif isinstance(val, dict) and isinstance(data[key], dict):
            for sub_key, sub_val in val.items():
                if sub_key not in data[key]:
                    data[key][sub_key] = sub_val
    if "active_model" in data:
        data.pop("active_model")
    if "system_prompt" in data:
        if "system" not in data.get("prompts", {}):
            data.setdefault("prompts", {})["system"] = data.pop("system_prompt")
        else:
            data.pop("system_prompt")
    prompts = data.get("prompts", {})
    if "consultor" in prompts and "system" not in prompts:
        prompts["system"] = prompts.pop("consultor")
    if "agent" in prompts:
        prompts.pop("agent", None)
    return data


def save(config):
    _ensure_dir()
    try:
        with open(_LLM_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except (PermissionError, OSError):
        pass


def get_provider(config, provider_id=None):
    pid = provider_id or config.get("active_provider", "")
    providers = config.get("providers", {})
    return providers.get(pid, {})


def get_active_model(config):
    pid = config.get("active_provider", "")
    am = config.get("active_models", {}).get(pid, "")
    if am:
        return am
    provider_models = get_provider(config, pid).get("models", [])
    return provider_models[0] if provider_models else ""
