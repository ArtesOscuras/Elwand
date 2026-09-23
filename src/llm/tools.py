"""Agent tool definitions — OpenAI function calling schema + handlers."""

import os

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_user",
            "description": "Add a user to the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "The username"},
                    "utype": {"type": "string", "enum": ["local", "domain"], "description": "User type"},
                    "machine": {"type": "string", "description": "Machine IP if local type"},
                    "domain": {"type": "string", "description": "Domain name if domain type"},
                    "origin": {"type": "string", "description": "How the user was found"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_user",
            "description": "Delete a user from the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username to delete"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_machine",
            "description": "Add a machine (IP) to the network inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4 address"},
                },
                "required": ["ip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_domain",
            "description": "Add a domain to the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain name"},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_subdomain",
            "description": "Add a subdomain to an existing domain in the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Parent domain name (e.g. 'example.com')"},
                    "subdomain": {"type": "string", "description": "Full subdomain (e.g. 'admin.example.com')"},
                },
                "required": ["domain", "subdomain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_machine",
            "description": "Get all known inventory info about a machine (IP, hostname, OS, ports, banners, web services, users, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Machine IP address or ID number (e.g. '192.168.1.100' or '5')",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_domain",
            "description": "Get all known info about a domain (subdomains, directories, web services, associated machines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain name (e.g. 'example.com')",
                    },
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "List all inventory: users, credentials, passwords, hashes, people, tickets, dictionaries, rules, POCs. Not machines/domains — use check_machine/check_domain for those.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_status",
            "description": "Show current Elwand state: all machines, domains, and inventory counts (users, credentials, hashes, shells, evidence).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_hash",
            "description": (
                "Get hash info. Without parameters: list all hashes (ID, type, "
                "truncated value). With hash_id: return full hash details "
                "(complete value, type, mode)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_id": {"type": "integer", "description": "Specific hash ID to get full details"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_shells",
            "description": "List all shell sessions with ID, type, status, IP, ports, OS, and timestamps.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_evidences",
            "description": (
                "List evidence sessions with metadata, filenames, and request directories "
                "(no file contents). Without 'name': lists sessions (paginated). With 'name': "
                "lists that session's files and request dirs (paginated)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Optional session name. If set, list that session's files and request directories instead of listing sessions."},
                    "offset": {"type": "integer", "description": "1-indexed start (default 1)"},
                    "limit": {"type": "integer", "description": "Max entries (sessions default 20; request dirs default 60)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_fuzz_results",
            "description": (
                "Retrieve fuzz results for a machine (by IP or ID). "
                "Returns saved directories and subdomains. Use offset/limit to paginate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Machine IP address or ID number (e.g. '192.168.1.100' or '5')",
                    },
                    "offset": {"type": "integer", "description": "1-indexed entry to start from (default: 1)"},
                    "limit": {"type": "integer", "description": "Max entries per section (default: 60)"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_credential",
            "description": "Add credential (username + password or NT hash). Auto-detects NT hash vs plaintext; computes NTLM for plaintext.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username"},
                    "secret": {"type": "string", "description": "Password or 32-char NT hash"},
                },
                "required": ["username", "secret"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_hash",
            "description": "Add a hash entry to the hash inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_type": {"type": "string", "description": "Hash type name (e.g. NTLM, MD5)"},
                    "hash_value": {"type": "string", "description": "The hash string"},
                    "hascat_mode": {"type": "string", "description": "Optional hashcat mode"},
                },
                "required": ["hash_type", "hash_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_hash",
            "description": "Delete a hash from the inventory by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_id": {"type": "integer", "description": "Hash ID to delete"},
                },
                "required": ["hash_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_password",
            "description": "Add a password to the password inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "password": {"type": "string", "description": "The password string"},
                },
                "required": ["password"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_interfaces",
            "description": "List available network interfaces for scanning.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_interface",
            "description": "Scan the local network on a given interface, looking for machines. Use list_interfaces first to see available interfaces.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iface": {"type": "string", "description": "Interface name, e.g. en0"},
                },
                "required": ["iface"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_ip",
            "description": "Scan a specific IP address to identify the machine (device type, OS, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4 address to scan"},
                },
                "required": ["ip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_scan",
            "description": "Stop the active network scan if one is running.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "port_scan",
            "description": (
                "Scan TCP or UDP ports on an IP. Returns common ports immediately, "
                "then continues full scan in background — results via check_machine."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["tcp", "udp"], "description": "TCP or UDP scan"},
                    "ip": {"type": "string", "description": "IPv4 address"},
                },
                "required": ["method", "ip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Ping an IP address to check if it's alive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4 address or hostname"},
                },
                "required": ["ip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nslookup",
            "description": "DNS lookup — resolve a hostname to IP addresses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Hostname or domain to resolve"},
                },
                "required": ["host"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "port_inspector",
            "description": "Inspect a TCP port by sending service-specific probes and returning identified banners.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4 address"},
                    "port": {"type": "integer", "description": "Port number (default 80)"},
                },
                "required": ["ip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bannergrab",
            "description": (
                "Open a raw TCP connection to an IP and port, wait up to 2 seconds "
                "for a banner or response, and return whatever data is received. "
                "Use this to grab service banners without sending any probes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4 address"},
                    "port": {"type": "integer", "description": "Port number"},
                },
                "required": ["ip", "port"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nmap",
            "description": (
                "Run nmap with custom arguments against a target. "
                "Do NOT include the target in arguments. Open ports are automatically "
                "saved to the machine inventory for known machines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target IP address or hostname to scan.",
                    },
                    "arguments": {
                        "type": "string",
                        "description": (
                            "Nmap arguments (flags and options) WITHOUT the target. "
                            "Examples: '-sV -sC -p 80,443' for service/script scan, "
                            "'-sS -p-' for SYN scan of all ports, "
                            "'-O -sV' for OS and service detection, "
                            "'-sU --top-ports 100' for top 100 UDP ports."
                        ),
                    },
                },
                "required": ["target", "arguments"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_credential",
            "description": "Delete a credential by username.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username of the credential"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_machine",
            "description": "Delete a machine from the inventory by IP or ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Machine IP address or ID number"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_domain",
            "description": "Delete a domain from the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain name to delete"},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_password",
            "description": "Delete a password from the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "password": {"type": "string", "description": "The password to delete"},
                },
                "required": ["password"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "webfetch",
            "description": "Fetch a URL as markdown or raw. Default GET; use POST only with body+content_type. Markdown strips navigation/footers. Raw returns status, headers, and first 60 lines (full body in cache). Paginate with offset/limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                    "format": {"type": "string", "enum": ["markdown", "raw"], "description": "Output format (default: markdown). Raw: see status, headers, and raw HTML."},
                    "method": {"type": "string", "enum": ["GET", "POST"], "description": "HTTP method (default: GET). Use POST only when submitting form/JSON data."},
                    "body": {"type": "string", "description": "Request body for POST (form-encoded or JSON). Ignored if method is GET."},
                    "content_type": {"type": "string", "description": "Content-Type header for POST body (default: application/x-www-form-urlencoded). E.g. 'application/json'. Ignored for GET."},
                    "headers": {"type": "object", "description": "Extra HTTP headers as key:value pairs for GET or POST. E.g. {'Cookie': 'session=abc', 'Authorization': 'Bearer xyz'}. Optional."},
                    "offset": {"type": "integer", "description": "Line to start from (default: 1). Ignored for raw."},
                    "limit": {"type": "integer", "description": "Max lines to return (default: 500). Ignored for raw."},
                    "antibot": {"type": "boolean", "description": "If true, attempt to bypass anti-bot challenges (Akamai, Cloudflare) by solving them in a real browser."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "websearch",
            "description": "Search the web and return results with title, URL, and snippet. Use this to find information about people, companies, or any topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "num_results": {"type": "integer", "description": "Number of results (default: 20)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_repo",
            "description": "List files and directories in a public GitHub repository using the GitHub REST API. No authentication needed for public repos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or organization (e.g. 'torvalds')"},
                    "repo": {"type": "string", "description": "Repository name (e.g. 'linux')"},
                    "path": {"type": "string", "description": "Directory path inside the repo (default: root). Use to navigate subdirectories."},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_person",
            "description": "Add a person (real human, employee, contact) to the people inventory. Use for OSINT-discovered individuals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "First name of the person"},
                    "last_name": {"type": "string", "description": "Last name(s) of the person"},
                    "company": {"type": "string", "description": "Company the person works for"},
                    "domain": {"type": "string", "description": "Domain associated with the person"},
                    "username": {"type": "string", "description": "OS username if linked to a system user"},
                    "role": {"type": "string", "description": "Job title or role"},
                    "linkedin_url": {"type": "string", "description": "LinkedIn profile URL"},
                    "source": {"type": "string", "description": "How this person was found (e.g. websearch, LinkedIn, agent)"},
                    "interests": {"type": "string", "description": "Known interests or topics"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_person",
            "description": "Delete a person from the people inventory by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {"type": "integer", "description": "Person ID to delete"},
                },
                "required": ["person_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dicma_generate_users",
            "description": "Generate username permutations from a person's full name using DICMA. Saves the output to the wordlist directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string", "description": "Full name of the person, e.g. 'Joan Garcia'"},
                    "output_name": {"type": "string", "description": "Output filename (e.g. 'users.txt'). Default: dicma_users.txt"},
                },
                "required": ["full_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dicma_find_related",
            "description": "Find semantically related words using the LLM via DICMA's neighbour expansion. Uses the active LLM config from Elwand settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "words": {"type": "string", "description": "Comma-separated seed words, e.g. 'football,music,hiking'"},
                    "n1": {"type": "integer", "description": "Number of level-1 neighbours per word (default: 50)"},
                    "n2": {"type": "integer", "description": "Optional level-2 neighbours per L1 result (default: 0)"},
                    "n3": {"type": "integer", "description": "Optional level-3 neighbours per L2 result (default: 0)"},
                    "output_name": {"type": "string", "description": "Output filename. Default: dicma_related.txt"},
                },
                "required": ["words"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dicma_generate_passwords",
            "description": "Generate password permutations from seed words using DICMA. Uses built-in suffix/prefix patterns. Saves to wordlist directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "words": {"type": "string", "description": "Comma-separated seed words, e.g. 'megacorp,summer2024'"},
                    "mode": {"type": "string", "enum": ["light", "normal", "full"], "description": "Generation mode (default: normal). Full mode creates massive output."},
                    "output_name": {"type": "string", "description": "Output filename. Default: dicma_passwords.txt"},
                },
                "required": ["words"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dicma_generate_rules",
            "description": "Generate hashcat rules from built-in patterns or a custom dictionary. Saves to the rules directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dictionary": {"type": "string", "description": "Optional dictionary filename from the wordlist directory to extract patterns from. Leave empty to use built-in rockyou-based patterns."},
                    "mode": {"type": "string", "enum": ["light", "normal", "full"], "description": "Generation mode (default: normal). Full mode creates massive output."},
                    "output_name": {"type": "string", "description": "Output filename. Default: dicma_rules.rule"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hashcat_crack",
            "description": "Crack a hash using hashcat with a wordlist. The hash must already be in the inventory (added via add_hash).",
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_value": {"type": "string", "description": "The hash string to crack (must exist in inventory)"},
                    "wordlist": {"type": "string", "description": "Wordlist filename from the wordlist directory (e.g. 'rockyou.txt')"},
                },
                "required": ["hash_value", "wordlist"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bruteforce_start",
            "description": "Start a brute force attack against a target service. Uses credential and password inventories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol": {"type": "string", "enum": ["ftp", "ssh", "smb", "rdp", "ldap", "mssql", "mysql", "pgsql"], "description": "Protocol to attack"},
                    "target": {"type": "string", "description": "Target IP address"},
                    "port": {"type": "integer", "description": "Port number (uses default if omitted)"},
                },
                "required": ["protocol", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fuzz_start",
            "description": (
                "Start an async fuzzing scan (directory, vhost, or DNS). "
                "Returns immediately — results are saved and can be retrieved with check_fuzz_results. "
                "Aborts if wildcard/catch-all is detected."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["directory", "vhost", "dns"], "description": "Fuzzing method: 'directory' for URL paths, 'vhost' for virtual hosts, 'dns' for DNS subdomains"},
                    "target": {"type": "string", "description": "Target IP address, machine ID, or domain name"},
                    "wordlist": {"type": "string", "description": "Wordlist filename from the wordlist directory (e.g. 'common.txt', 'subdomains.txt')"},
                    "port": {"type": "integer", "description": "Port number (default: 80). Only used for 'directory' method."},
                    "scheme": {"type": "string", "enum": ["http", "https"], "description": "HTTP or HTTPS (default: http). Ignores self-signed certificates."},
                    "skip_codes": {"type": "array", "items": {"type": "integer"}, "description": "HTTP status codes to skip/ignore (default: [404]). Pass empty array to show all codes."},
                    "hide_size": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2, "description": "Hide responses whose body size (bytes) falls within [min, max] range. Both inclusive."},
                    "workers": {"type": "integer", "description": "Number of concurrent threads (default: 50). Reduce if server is slow or blocking requests."},
                },
                "required": ["method", "target", "wordlist"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listener",
            "description": "Start or stop a background service listener (reverse shell or mDNS).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "stop"], "description": "Start or stop the listener"},
                    "service": {"type": "string", "enum": ["shells-listener", "mdns-listener"], "description": "Service to manage"},
                },
                "required": ["action", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List available files by type: wordlist dictionaries, hashcat rules, POC scripts, or cached tool outputs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_type": {
                        "type": "string",
                        "enum": ["dictionary", "rule", "poc", "cache"],
                        "description": "Type of files: dictionary (wordlists), rule (hashcat), poc (Python scripts), cache (truncated tool outputs)",
                    },
                },
                "required": ["file_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cache",
            "description": "Read a cached tool output file from cache/. Use offset/limit to paginate, or regex with context_before/context_after to search for specific content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Filename from list_files(cache) or the truncation marker"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed, default 1). Ignored if regex is set."},
                    "limit": {"type": "integer", "description": "Max lines to read (default 200). Ignored if regex is set."},
                    "regex": {"type": "string", "description": "Optional regex pattern to search within the file. When set, returns matching lines with surrounding context instead of offset/limit pagination."},
                    "context_before": {"type": "integer", "description": "Lines to show before each regex match (default: 2)"},
                    "context_after": {"type": "integer", "description": "Lines to show after each regex match (default: 10)"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_evidence",
            "description": (
                "Read a specific file from an evidence session (session.json, request.json, "
                "response.json, body.html). Use offset/limit to paginate, or regex with "
                "context_before/context_after to search. List sessions with check_evidences."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Evidence session name (from check_evidences)"},
                    "filename": {"type": "string", "description": "Relative file path within the session, e.g. 'session.json' or '0001_GET_root/request.json'"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed, default 1). Ignored if regex is set."},
                    "limit": {"type": "integer", "description": "Max lines to read (default 200). Ignored if regex is set."},
                    "regex": {"type": "string", "description": "Optional regex pattern to search within the file. When set, returns matching lines with surrounding context instead of offset/limit pagination."},
                    "context_before": {"type": "integer", "description": "Lines to show before each regex match (default: 2)"},
                    "context_after": {"type": "integer", "description": "Lines to show after each regex match (default: 10)"},
                },
                "required": ["name", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file by type: dictionary, rule, poc, or cache.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_type": {"type": "string", "enum": ["dictionary", "rule", "poc", "cache"], "description": "Type of file to delete"},
                    "filename": {"type": "string", "description": "The filename to delete"},
                },
                "required": ["file_type", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_evidence",
            "description": "Delete an evidence session by name or all evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Evidence session name to delete, or 'all' to delete all evidence"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_shell",
            "description": "Delete a shell session by ID or all shell sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shell_id": {"type": "string", "description": "Shell session ID to delete, or 'all' to delete all"},
                },
                "required": ["shell_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": (
                "Send a command to a shell session. The command may still be running when this returns. "
                "Use shell_wait for more output, shell_interrupt to stop it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "shell_id": {"type": "integer", "description": "Shell session ID from check_shells"},
                    "command": {"type": "string", "description": "Command to execute (e.g. 'whoami', 'ls -la', 'find /')"},
                },
                "required": ["shell_id", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_wait",
            "description": "Wait for more output from a running shell command. Call after shell_exec returned status 'running'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shell_id": {"type": "integer", "description": "Shell session ID from check_shells"},
                },
                "required": ["shell_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_interrupt",
            "description": "Send Ctrl+C to interrupt the running command in a shell. Returns any remaining output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shell_id": {"type": "integer", "description": "Shell session ID from check_shells"},
                },
                "required": ["shell_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "connect",
            "description": "Connect to a remote machine via SSH, SFTP, FTP, or WinRM using stored credentials.",
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol": {
                        "type": "string",
                        "enum": ["ssh", "sftp", "ftp", "winrm"],
                        "description": "Connection protocol (ssh:22, sftp:22, ftp:21, winrm:5985 as default ports)",
                    },
                    "host": {"type": "string", "description": "Machine ID or IP address"},
                    "username": {"type": "string", "description": "Username (must exist in credentials, use 'anonymous' for anonymous FTP)"},
                    "port": {"type": "integer", "description": "Port number (if different from default)"},
                },
                "required": ["protocol", "host", "username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poc_write",
            "description": (
                "Create or overwrite a proof-of-concept Python file in the pocs/ directory. "
                "Use this to save POC scripts generated by the LLM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename (e.g. 'cve_2024_1234.py'). Must end with .py"},
                    "content": {"type": "string", "description": "The full Python source code to write to the file."},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poc_read",
            "description": (
                "Read a proof-of-concept Python file from the pocs/ directory. "
                "Use this to review the content of an existing POC before editing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to read (e.g. 'cve_2024_1234.py')"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed, default 1)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read (default 2000)"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poc_edit",
            "description": "Edit a POC file by replacing an exact string match in the pocs/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to edit (e.g. 'cve_2024_1234.py')"},
                    "old_string": {"type": "string", "description": "The exact text to find and replace in the file."},
                    "new_string": {"type": "string", "description": "The replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences instead of just the first (default false)."},
                    "new_filename": {"type": "string", "description": "Optional new filename to rename the POC to (must end with .py)."},
                },
                "required": ["filename", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poc_exec",
            "description": (
                "Execute a POC Python script and return its output. "
                "Output is truncated to last 10 lines or last 2000 bytes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The POC filename to execute (e.g. 'sqli_poc.py')"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_write",
            "description": (
                "Create or overwrite a markdown report file in the reports/ directory. "
                "Use only when the user requests a report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename (e.g. 'recon_report.md'). Must end with .md"},
                    "content": {"type": "string", "description": "The full markdown content to write to the report."},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_read",
            "description": (
                "Read a markdown report from the reports/ directory. Supports offset/limit "
                "pagination or regex search with context lines (like read_cache)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to read (e.g. 'recon_report.md')"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed, default 1)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read (default 150)"},
                    "regex": {"type": "string", "description": "Optional regex to search for; returns matching lines with context."},
                    "context_before": {"type": "integer", "description": "Lines before each regex match (default 2)"},
                    "context_after": {"type": "integer", "description": "Lines after each regex match (default 10)"},
                },
                "required": ["filename"],
            },
        },
    },
]

_HANDLERS = {}

CONSULTOR_TOOLS = frozenset({
    "check_status", "check_machine", "check_domain", "check_inventory",
    "check_hash", "check_shells", "check_evidences", "read_evidence", "check_fuzz_results",
    "webfetch", "websearch", "list_repo",
    "read_cache", "list_files", "poc_read", "report_read",
    "nslookup", "list_interfaces", "ping",
    "dicma_generate_users", "dicma_find_related",
    "dicma_generate_passwords", "dicma_generate_rules",
})


def register(name):
    def decorator(fn):
        _HANDLERS[name] = fn
        return fn
    return decorator


def execute(name, args_dict, tool_context=None):
    if tool_context and getattr(tool_context, "_agent_stop_event", None) and tool_context._agent_stop_event.is_set():
        return f"Tool '{name}' cancelled (agent stop requested)."
    handler = _HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        result = handler(args_dict, tool_context)
        return _bound_tool_output(result, name)
    except Exception as e:
        return f"Tool error: {e}"


# ─── Tool Handlers ──────────────────────────────────────────
# All handlers receive (args_dict, tool_context).
# tool_context is the App instance (or None).

MAX_SHELL_CHARS = 5000
MAX_TOOL_LINES = 2000
MAX_TOOL_BYTES = 50 * 1024
TOOL_BYTE_LIMITS = {
    "poc_exec": 2000,
    "port_inspector": 2000,
    "check_machine": 3000,
    "websearch": 8000,
    "webfetch": 3000,
    "read_cache": 6000,
    "read_evidence": 6000,
}
TOOL_LINE_LIMITS = {
    "webfetch": 60,
    "read_cache": 200,
    "read_evidence": 200,
}


def _bound_tool_output(output, tool_name):
    if not isinstance(output, str):
        return output
    byte_limit = TOOL_BYTE_LIMITS.get(tool_name, MAX_TOOL_BYTES)
    line_limit = TOOL_LINE_LIMITS.get(tool_name, MAX_TOOL_LINES)
    lines = output.split("\n")
    byte_len = len(output.encode("utf-8"))
    if len(lines) <= line_limit and byte_len <= byte_limit:
        return output
    from src.elwand_paths import cache_dir
    import time as _time
    ts = int(_time.time())
    filename = f"tool_{ts}_{tool_name}.txt"
    path = os.path.join(str(cache_dir()), filename)
    try:
        with open(path, "w") as f:
            f.write(output)
    except (PermissionError, OSError):
        return output
    head = line_limit // 2
    tail = max(0, line_limit // 2 - 1)
    marker = f"\n... output truncated ({len(lines)} lines, {byte_len} bytes). To read the rest: read_cache(\"{filename}\")\n"
    preview = "\n".join(lines[:head])
    if tail > 0 and len(lines) > head:
        preview += marker + "\n".join(lines[-tail:])
    else:
        preview += marker
    if len(preview.encode("utf-8")) > byte_limit:
        marker_bytes = len(marker.encode("utf-8"))
        content_limit = max(100, byte_limit - marker_bytes - 10)
        preview = preview[:content_limit] + marker
        if len(preview.encode("utf-8")) > byte_limit:
            preview = preview[:byte_limit]
    return preview


def _resolve_cache_path(filename):
    from src.elwand_paths import cache_dir
    base = str(cache_dir())
    resolved = os.path.normpath(os.path.join(base, filename))
    if not resolved.startswith(os.path.normpath(base) + os.sep) and resolved != os.path.normpath(base):
        return None
    return resolved


def _resolve_evidence_path(name, filename):
    from src.elwand_paths import evidence_dir
    root = os.path.normpath(str(evidence_dir()))
    base = os.path.normpath(os.path.join(root, name))
    if not base.startswith(root + os.sep):
        return None
    resolved = os.path.normpath(os.path.join(base, filename))
    if not resolved.startswith(base + os.sep) and resolved != base:
        return None
    return resolved


def _fmt_shell(prefix, combined):
    total = len(combined)
    if total > MAX_SHELL_CHARS:
        combined = combined[-MAX_SHELL_CHARS:]
        return f"{prefix}[{total} chars total, last {MAX_SHELL_CHARS}]\n{combined}"
    return f"{prefix}\n{combined}"


@register("add_user")
def _add_user(args, ctx=None):
    from src.machines.credential_db import save_user
    save_user(
        username=args.get("username", ""),
        utype=args.get("utype", ""),
        machine=args.get("machine", ""),
        domain=args.get("domain", ""),
        origin=args.get("origin", "agent"),
    )
    return f"User '{args.get('username')}' added."


@register("delete_user")
def _delete_user(args, ctx=None):
    from src.machines.credential_db import delete_user, load_usernames
    username = args.get("username", "")
    if username not in load_usernames():
        return f"User '{username}' not found."
    delete_user(username)
    return f"User '{username}' deleted."


@register("add_machine")
def _add_machine(args, ctx=None):
    from src.machines import store, machine_db
    ip = args.get("ip", "")
    machine = store.add_or_update(ip=ip, method="agent")
    machine.device_type = "device unknown"
    machine_db.save_machine_info(machine)
    return f"Machine #{machine.id} ({ip}) added."


@register("add_domain")
def _add_domain(args, ctx=None):
    from src.machines import domain_db
    domain = args.get("domain", "")
    domain_db.init_or_update(domain, 0, "", "agent")
    return f"Domain '{domain}' added."


@register("add_subdomain")
def _add_subdomain(args, ctx=None):
    from src.machines import domain_db
    domain = args.get("domain", "")
    subdomain = args.get("subdomain", "")
    if not domain or not subdomain:
        return "Missing domain or subdomain."
    domain_db.save_subdomain(domain, subdomain, "agent")
    return f"Subdomain '{subdomain}' added to domain '{domain}'."


@register("check_machine")
def _check_machine(args, ctx=None):
    from src.machines import store, machine_db
    from src.machines.credential_db import load_users

    target = args.get("target", "").strip()
    if not target:
        return "Error: no target specified."

    machine = store.get(target)
    if not machine:
        for m in store.get_all():
            if str(m.id) == target:
                machine = m
                break

    if not machine:
        return f"Machine '{target}' not found in inventory."

    m = machine
    lines = [f"Machine #{m.id}: {m.ip}"]
    if getattr(m, "hostname", ""):
        lines.append(f"  Hostname: {m.hostname}")
    if getattr(m, "ipv6", ""):
        lines.append(f"  IPv6: {m.ipv6}")
    if getattr(m, "mac", ""):
        lines.append(f"  MAC: {m.mac}")
    if getattr(m, "device_type", ""):
        lines.append(f"  Device type: {m.device_type}")
    if getattr(m, "model", ""):
        lines.append(f"  Model: {m.model}")
    if getattr(m, "os", ""):
        lines.append(f"  OS: {m.os}")
    if getattr(m, "domain", ""):
        lines.append(f"  Domain: {m.domain}")
    methods = getattr(m, "methods", set())
    if methods:
        lines.append(f"  Methods: {', '.join(sorted(methods))}")
    if getattr(m, "first_seen", None):
        lines.append(f"  First seen: {m.first_seen.isoformat()}")
    if getattr(m, "last_seen", None):
        lines.append(f"  Last seen: {m.last_seen.isoformat()}")

    try:
        tcp = machine_db.load_tcp_ports(m.id)
        if tcp:
            lines.append(f"  TCP ports ({len(tcp)}): {', '.join(str(p) for p in tcp)}")
    except Exception:
        pass

    try:
        udp = machine_db.load_udp_ports(m.id)
        if udp:
            lines.append(f"  UDP ports ({len(udp)}): {', '.join(str(p) for p in udp)}")
    except Exception:
        pass

    try:
        banners = machine_db.load_banners(m.id)
        if banners:
            lines.append(f"  Banners ({len(banners)}):")
            for port, output, probe in banners[:10]:
                truncated = output[:500] + "..." if len(output) > 500 else output
                lines.append(f"    Port {port}: {truncated}")
            if len(banners) > 10:
                lines.append(f"    ... and {len(banners)-10} more banners")
    except Exception:
        pass

    try:
        ws = machine_db.load_web_services(m.id)
        if ws:
            lines.append(f"  Web services ({len(ws)}):")
            for port, output in ws:
                truncated = output[:500] + "..." if len(output) > 500 else output
                lines.append(f"    Port {port}: {truncated}")
    except Exception:
        pass

    try:
        domains = machine_db.load_domains(m.id)
        if domains:
            parts = [f"{d} ({s})" if s else d for d, s in domains]
            lines.append(f"  Associated domains ({len(domains)}): {', '.join(parts)}")
    except Exception:
        pass

    try:
        dirs = machine_db.load_directories(m.id)
        if dirs:
            paths = [d for d, _ in dirs[:30]]
            suffix = f" (+{len(dirs) - 30} more)" if len(dirs) > 30 else ""
            lines.append(f"  Directories ({len(dirs)}): {', '.join(paths)}{suffix}")
    except Exception:
        pass

    try:
        all_users = load_users()
        machine_users = [u for u in all_users if u.get("machine") == m.ip]
        if machine_users:
            user_strs = [f"{u['username']} ({u.get('type', '?')})" for u in machine_users[:20]]
            lines.append(f"  Users ({len(machine_users)}): {', '.join(user_strs)}")
            if len(machine_users) > 20:
                lines.append(f"    ... and {len(machine_users) - 20} more")
    except Exception:
        pass

    return "\n".join(lines)


@register("check_domain")
def _check_domain(args, ctx=None):
    from src.machines import domain_db

    domain = args.get("domain", "").strip()
    if not domain:
        return "Error: no domain specified."

    if not domain_db.exists(domain):
        return f"Domain '{domain}' not found in inventory."

    lines = [f"Domain: {domain}"]

    info = domain_db.load_domain_info(domain)
    if info:
        if info.get("first_seen"):
            lines.append(f"  First seen: {info['first_seen']}")
        if info.get("last_seen"):
            lines.append(f"  Last seen: {info['last_seen']}")

    try:
        subs = domain_db.load_subdomains(domain)
        if subs:
            lines.append(f"  Subdomains ({len(subs)}):")
            for sub, ts, method in subs[:30]:
                meta = f" ({method})" if method else ""
                lines.append(f"    {sub}{meta}")
            if len(subs) > 30:
                lines.append(f"    ... and {len(subs) - 30} more")
    except Exception:
        pass

    try:
        dirs = domain_db.load_directories(domain)
        if dirs:
            paths = [d for d, _ in dirs[:30]]
            suffix = f" (+{len(dirs) - 30} more)" if len(dirs) > 30 else ""
            lines.append(f"  Directories ({len(dirs)}): {', '.join(paths)}{suffix}")
    except Exception:
        pass

    try:
        ws = domain_db.load_web_services(domain)
        if ws:
            lines.append(f"  Web services ({len(ws)}):")
            for port, output in ws[:10]:
                truncated = output[:500] + "..." if len(output) > 500 else output
                lines.append(f"    Port {port}: {truncated}")
            if len(ws) > 10:
                lines.append(f"    ... and {len(ws) - 10} more")
    except Exception:
        pass

    try:
        machines = domain_db.load_domain_machines(domain)
        valid = [m for m in machines if m.get("machine_id") and m["machine_id"] != 0]
        if valid:
            lines.append(f"  Machines ({len(valid)}):")
            for m in valid[:15]:
                src = f" ({m['source']})" if m.get("source") else ""
                lines.append(f"    #{m['machine_id']} {m['machine_ip']}{src}")
            if len(valid) > 15:
                lines.append(f"    ... and {len(valid) - 15} more")
    except Exception:
        pass

    return "\n".join(lines)


@register("check_inventory")
def _check_inventory(args, ctx=None):
    import os
    from src.machines.credential_db import load_users, load_passwords, load_hashes, load_credentials, load_tickets
    from src.machines.people_db import load_people
    from src.elwand_paths import lst_dir, rules_dir, pocs_dir, reports_dir

    lines = ["Current Elwand inventory:"]

    users = load_users()
    if users:
        lines.append(f"\nUsers ({len(users)}):")
        for u in users[:50]:
            info = f"  #{u['id']} {u['username']} ({u.get('type', '?')})"
            if u.get("domain"):
                info += f" domain: {u['domain']}"
            if u.get("machine"):
                info += f" machine: {u['machine']}"
            if u.get("origin"):
                info += f" origin: {u['origin']}"
            lines.append(info)
        if len(users) > 50:
            lines.append(f"  ... and {len(users) - 50} more")

    creds = load_credentials()
    if creds:
        lines.append(f"\nCredentials ({len(creds)}):")
        for c in creds[:50]:
            info = f"  #{c['id']} {c['username']}"
            if c.get("domain"):
                info += f" domain: {c['domain']}"
            flags = []
            if c.get("password"):
                flags.append("password")
            if c.get("hash_nt"):
                flags.append("NT")
            if flags:
                info += f" ({', '.join(flags)})"
            lines.append(info)
        if len(creds) > 50:
            lines.append(f"  ... and {len(creds) - 50} more")

    pwds = load_passwords()
    if pwds:
        lines.append(f"\nPasswords ({len(pwds)}):")
        for p in pwds[:50]:
            lines.append(f"  {p}")
        if len(pwds) > 50:
            lines.append(f"  ... and {len(pwds) - 50} more")

    hashes = load_hashes()
    if hashes:
        lines.append(f"\nHashes ({len(hashes)}):")
        for h in hashes[:30]:
            hval = h["hash"]
            truncated = hval[:60] + "..." if len(hval) > 60 else hval
            info = f"  #{h['id']} [{h.get('type', '?')}] {truncated}"
            if h.get("hascat_mode"):
                info += f" mode: {h['hascat_mode']}"
            lines.append(info)
        if len(hashes) > 30:
            lines.append(f"  ... and {len(hashes) - 30} more")

    people = load_people()
    if people:
        lines.append(f"\nPeople ({len(people)}):")
        for p in people[:30]:
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or f"#{p['id']}"
            info = f"  #{p['id']} {name}"
            if p.get("company"):
                info += f" company: {p['company']}"
            if p.get("domain"):
                info += f" domain: {p['domain']}"
            if p.get("username"):
                info += f" username: {p['username']}"
            if p.get("role"):
                info += f" role: {p['role']}"
            lines.append(info)
        if len(people) > 30:
            lines.append(f"  ... and {len(people) - 30} more")

    tickets = load_tickets()
    if tickets:
        lines.append(f"\nTickets ({len(tickets)}):")
        for t in tickets[:20]:
            lines.append(
                f"  #{t['id']} {t.get('principal', '?')}@{t.get('realm', '?')} "
                f"svc: {t.get('service', '?')} [{t.get('ticket_type', '?')}]"
            )
        if len(tickets) > 20:
            lines.append(f"  ... and {len(tickets) - 20} more")

    lst = str(lst_dir())
    if os.path.isdir(lst):
        lst_files = sorted(
            f for f in os.listdir(lst) if os.path.isfile(os.path.join(lst, f))
        )
        if lst_files:
            lines.append(f"\nDictionaries ({len(lst_files)}):")
            for f in lst_files[:30]:
                lines.append(f"  {f}")
            if len(lst_files) > 30:
                lines.append(f"  ... and {len(lst_files) - 30} more")

    rules_d = str(rules_dir())
    if os.path.isdir(rules_d):
        rule_files = sorted(
            f for f in os.listdir(rules_d) if os.path.isfile(os.path.join(rules_d, f))
        )
        if rule_files:
            lines.append(f"\nHashcat rules ({len(rule_files)}):")
            for f in rule_files[:30]:
                lines.append(f"  {f}")
            if len(rule_files) > 30:
                lines.append(f"  ... and {len(rule_files) - 30} more")

    pocs_d = str(pocs_dir())
    if os.path.isdir(pocs_d):
        poc_files = sorted(
            f for f in os.listdir(pocs_d) if os.path.isfile(os.path.join(pocs_d, f))
        )
        if poc_files:
            lines.append(f"\nPOCs ({len(poc_files)}):")
            for f in poc_files[:30]:
                lines.append(f"  {f}")
            if len(poc_files) > 30:
                lines.append(f"  ... and {len(poc_files) - 30} more")

    reports_d = str(reports_dir())
    if os.path.isdir(reports_d):
        report_files = sorted(
            f for f in os.listdir(reports_d) if os.path.isfile(os.path.join(reports_d, f))
        )
        if report_files:
            lines.append(f"\nReports ({len(report_files)}):")
            for f in report_files[:30]:
                lines.append(f"  {f}")
            if len(report_files) > 30:
                lines.append(f"  ... and {len(report_files) - 30} more")

    return "\n".join(lines)


@register("check_status")
def _check_status(args, ctx=None):
    from src.machines import store, machine_db, domain_db
    from src.machines.credential_db import (
        load_users, load_passwords, load_credentials, load_hashes)
    from src.shells import shell_db
    import os
    from src.elwand_paths import evidence_dir, lst_dir, rules_dir, pocs_dir, reports_dir

    lines = ["Current Elwand state:"]

    machines = store.get_all()
    if machines:
        lines.append(f"\nMachines ({len(machines)}):")
        for m in machines:
            info = f"  #{m.id} {m.ip}"
            if getattr(m, "hostname", ""):
                info += f" ({m.hostname})"
            if getattr(m, "domain", ""):
                info += f"  domain: {m.domain}"
            if getattr(m, "device_type", ""):
                info += f"  device: {m.device_type}"
            try:
                tcp = machine_db.load_tcp_ports(m.id)
                udp = machine_db.load_udp_ports(m.id)
                parts = []
                if tcp:
                    parts.append(f"tcp:{len(tcp)}")
                if udp:
                    parts.append(f"udp:{len(udp)}")
                if parts:
                    info += f"  ports: {', '.join(parts)}"
            except Exception:
                pass
            lines.append(info)
    else:
        lines.append("\nNo machines in inventory.")

    domains = domain_db.list_all()
    if domains:
        lines.append(f"\nDomains ({len(domains)}):")
        for d in domains:
            lines.append(f"  {d}")
    else:
        lines.append("\nNo domains in inventory.")

    users = load_users()
    creds = load_credentials()
    pwds = load_passwords()
    hashes = load_hashes()

    parts = []
    if users:
        parts.append(f"{len(users)} users")
    if creds:
        parts.append(f"{len(creds)} credentials")
    if pwds:
        parts.append(f"{len(pwds)} passwords")
    if hashes:
        parts.append(f"{len(hashes)} hashes")
    if parts:
        lines.append(f"\nInventory: {', '.join(parts)}")

    sessions = shell_db.get_all()
    if sessions:
        lines.append(f"\nShell sessions: {len(sessions)} active")

    ev_dir = str(evidence_dir())
    if os.path.isdir(ev_dir):
        evs = [e for e in os.listdir(ev_dir)
               if os.path.isdir(os.path.join(ev_dir, e))]
        if evs:
            lines.append(f"Evidence sessions: {len(evs)}")

    for label, path in [("Dictionaries", lst_dir()),
                         ("Hashcat rules", rules_dir()),
                         ("POCs", pocs_dir()),
                         ("Reports", reports_dir())]:
        p = str(path)
        if os.path.isdir(p):
            files = [f for f in os.listdir(p)
                     if os.path.isfile(os.path.join(p, f))]
            if files:
                lines.append(f"{label}: {len(files)}")

    return "\n".join(lines)


@register("check_hash")
def _check_hash(args, ctx=None):
    from src.machines.credential_db import load_hashes
    hash_id = args.get("hash_id")
    hashes = load_hashes()
    if not hashes:
        return "No hashes in inventory."
    if hash_id is not None:
        h = next((x for x in hashes if x.get("id") == hash_id), None)
        if not h:
            return f"Hash #{hash_id} not found."
        return (
            f"Hash #{h['id']}\n"
            f"  Type: {h.get('type', '?')}\n"
            f"  Value: {h['hash']}\n"
            f"  Mode: {h.get('hascat_mode', 'N/A')}"
        )
    lines = [f"Hashes ({len(hashes)}):"]
    for h in hashes:
        hval = h["hash"]
        truncated = hval[:60] + "..." if len(hval) > 60 else hval
        info = f"  #{h['id']} [{h.get('type', '?')}] {truncated}"
        if h.get("hascat_mode"):
            info += f" mode: {h['hascat_mode']}"
        lines.append(info)
    return "\n".join(lines)


@register("check_shells")
def _check_shells(args, ctx=None):
    from src.shells.shell_db import get_all

    sessions = get_all()
    if not sessions:
        return "No active shell sessions."

    lines = [f"Shell sessions ({len(sessions)}):"]
    for s in sessions:
        sid = s["id"]
        stype = s.get("type", "?")
        status = s.get("status", "?")
        active = s.get("active", False)
        ip = s.get("ip", "?")
        port = s.get("source_port", "?")
        lport = s.get("listener_port", 0)
        conn = s.get("connected_at", None)
        last = s.get("last_active", None)
        shell_os = s.get("os", "")

        flags = []
        if active:
            flags.append("active")
        if shell_os:
            flags.append(shell_os)

        line = f"  #{sid} [{stype}] {status}"
        line += f" {ip}:{port}"
        if lport and lport != 0:
            line += f" (listener: {lport})"
        if flags:
            line += f" ({', '.join(flags)})"
        if conn:
            line += f" connected: {conn.isoformat()}"
        if last:
            line += f" last: {last.isoformat()}"
        lines.append(line)

    return "\n".join(lines)


@register("check_evidences")
def _check_evidences(args, ctx=None):
    import json
    import os
    from src.elwand_paths import evidence_dir

    base = str(evidence_dir())
    if not os.path.isdir(base):
        return "No evidence directory found."

    names = sorted(
        n for n in os.listdir(base)
        if os.path.isdir(os.path.join(base, n))
    )
    if not names:
        return "No evidence sessions found."

    name = args.get("name", "").strip()
    if name:
        if name not in names:
            return f"Evidence session '{name}' not found."
        return _describe_evidence_session(base, name, args)

    offset = int(args.get("offset", 1))
    limit = int(args.get("limit", 20)) or 20
    if offset < 1:
        offset = 1
    start = offset - 1
    end = start + limit
    shown = names[start:end]

    lines = [f"Evidence sessions ({len(names)} total):"]
    for n in shown:
        session_dir = os.path.join(base, n)
        lines.append(f"\n  {n}/")
        meta_path = os.path.join(session_dir, "session.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                if meta.get("target"):
                    lines.append(f"    target: {meta['target']}")
                if meta.get("browser"):
                    lines.append(f"    browser: {meta['browser']}")
                if meta.get("started_at"):
                    lines.append(f"    started: {meta['started_at']}")
                if meta.get("ended_at"):
                    lines.append(f"    ended: {meta['ended_at']}")
                if meta.get("request_count", 0):
                    lines.append(f"    requests: {meta['request_count']}")
            except (json.JSONDecodeError, PermissionError, OSError):
                pass

        try:
            entries = sorted(os.listdir(session_dir))
        except (PermissionError, OSError):
            entries = []
        files = [e for e in entries if os.path.isfile(os.path.join(session_dir, e))]
        dirs = [e for e in entries if os.path.isdir(os.path.join(session_dir, e))]

        if files:
            lines.append(f"    files ({len(files)})")
        if dirs:
            lines.append(f"    request dirs ({len(dirs)})")

    if end < len(names):
        lines.append(f"\n  ... {len(names) - end} more sessions — use offset={end + 1}")
    lines.append('\nUse check_evidences(name="<session>") to list its files and request dirs.')
    return "\n".join(lines)


def _describe_evidence_session(base, name, args):
    import json
    import os

    session_dir = os.path.join(base, name)
    lines = [f"Evidence session: {name}/"]

    meta_path = os.path.join(session_dir, "session.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            if meta.get("target"):
                lines.append(f"  target: {meta['target']}")
            if meta.get("browser"):
                lines.append(f"  browser: {meta['browser']}")
            if meta.get("started_at"):
                lines.append(f"  started: {meta['started_at']}")
            if meta.get("ended_at"):
                lines.append(f"  ended: {meta['ended_at']}")
            if meta.get("request_count", 0):
                lines.append(f"  requests: {meta['request_count']}")
        except (json.JSONDecodeError, PermissionError, OSError):
            pass

    try:
        entries = sorted(os.listdir(session_dir))
    except (PermissionError, OSError):
        entries = []
    files = [e for e in entries if os.path.isfile(os.path.join(session_dir, e))]
    dirs = [e for e in entries if os.path.isdir(os.path.join(session_dir, e))]

    if files:
        lines.append(f"\nFiles ({len(files)}):")
        for f in files:
            lines.append(f"  {f}")

    if dirs:
        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 60)) or 60
        if offset < 1:
            offset = 1
        start = offset - 1
        end = start + limit
        shown = dirs[start:end]
        lines.append(f"\nRequest dirs ({len(dirs)} total):")
        for d in shown:
            lines.append(f"  {d}/")
        if end < len(dirs):
            lines.append(f"  ... {len(dirs) - end} more request dirs — use offset={end + 1}")
    else:
        lines.append("\nNo request dirs.")

    return "\n".join(lines)


@register("check_fuzz_results")
def _check_fuzz_results(args, ctx=None):
    from src.machines import store, machine_db, domain_db

    target = args.get("target", "").strip()
    if not target:
        return "Error: no target specified."

    machine = store.get(target)
    if not machine:
        for m in store.get_all():
            if str(m.id) == target:
                machine = m
                break

    if not machine:
        return f"Machine '{target}' not found in inventory."

    offset = int(args.get("offset", 1))
    limit = int(args.get("limit", 60)) or 60
    start = max(0, offset - 1)
    end = start + limit

    dir_rows = machine_db.load_directories(machine.id)

    domain = getattr(machine, "domain", "")
    sub_rows = []
    if domain:
        try:
            sub_rows = domain_db.load_subdomains(domain)
        except Exception:
            pass

    if not dir_rows and not sub_rows:
        return f"No fuzz or directory results for machine #{machine.id} ({machine.ip})."

    lines = [f"Fuzz & directory results for #{machine.id} ({machine.ip}):"]

    if dir_rows:
        lines.append(f"\nSaved directories ({len(dir_rows)} total):")
        for path, _ in dir_rows[start:end]:
            lines.append(f"  {path}")
        if end < len(dir_rows):
            lines.append(
                f"  ... {len(dir_rows) - end} more — use offset={end + 1}")

    if sub_rows:
        lines.append(f"\nSubdomains for {domain} ({len(sub_rows)} total):")
        for name, _, method in sub_rows[start:end]:
            lines.append(f"  {name} [{method}]")
        if end < len(sub_rows):
            lines.append(
                f"  ... {len(sub_rows) - end} more — use offset={end + 1}")

    return "\n".join(lines)


@register("add_credential")
def _add_credential(args, ctx=None):
    from src.machines.credential_db import save_credential, save_user
    username = args.get("username", "")
    secret = args.get("secret", "")
    import re
    nt_pattern = re.compile(r"^[a-fA-F0-9]{32}$")
    if nt_pattern.match(secret):
        cid = save_credential(username, "", hash_nt=secret, hash_nt_origin="agent")
        save_user(username, origin="agent")
        return f"Credential #{cid}: {username} (NT hash) added."
    from src.gui.views.user_pass import _ntlm_hash
    hnt = _ntlm_hash(secret)
    cid = save_credential(username, secret, hash_nt=hnt,
                          password_origin="agent", hash_nt_origin="agent")
    save_user(username, origin="agent")
    return f"Credential #{cid}: {username} / {secret} added."


@register("add_hash")
def _add_hash(args, ctx=None):
    from src.machines.credential_db import save_hash_entry
    hid = save_hash_entry(
        hash_type=args.get("hash_type", ""),
        hash_value=args.get("hash_value", ""),
        hascat_mode=args.get("hascat_mode", ""),
        origin="agent",
    )
    return f"Hash #{hid} added."


@register("delete_hash")
def _delete_hash(args, ctx=None):
    from src.machines.credential_db import delete_hash_entry
    hid = args.get("hash_id")
    delete_hash_entry(hid)
    return f"Hash #{hid} deleted."


@register("add_password")
def _add_password(args, ctx=None):
    from src.machines.credential_db import save_password
    save_password(args.get("password", ""))
    return "Password added."


@register("list_interfaces")
def _list_interfaces(args, ctx=None):
    from src.network_iface import interfaces, ifaddresses, AF_INET
    result = []
    for iface in interfaces():
        if iface == "lo0":
            continue
        addrs = ifaddresses(iface).get(AF_INET)
        if addrs:
            for a in addrs:
                result.append(f"  {iface}: {a['addr']}/{a['netmask']}")
    if not result:
        return "No network interfaces with IPv4 found."
    return "Available interfaces:\n" + "\n".join(result)


@register("scan_interface")
def _scan_interface(args, ctx=None):
    iface = args.get("iface", "")
    if not ctx:
        return "Cannot scan: no tool context available."
    ctx._scan_interface(iface)
    return (f"Network scan started on interface {iface}. "
            "Results will appear in inventory as machines are discovered.")


@register("scan_ip")
def _scan_ip(args, ctx=None):
    ip = args.get("ip", "")
    if not ctx:
        return "Cannot scan: no tool context available."
    from src.gui.app import _do_scan_ip
    info = _do_scan_ip(ip)
    if info is None:
        return f"No device detected at {ip}"
    from src import event_bus
    from src.machines import store as _store
    machine = _store.get(ip)
    if machine:
        event_bus.submit({"type": "scan_ip_result", "machine": machine})
    lines = [f"Scan result for {ip}:"]
    lines.append(f"  Device type: {info['device_type']}")
    if info.get("os"):
        lines.append(f"  OS: {info['os']}")
    if info.get("hostname"):
        lines.append(f"  Hostname: {info['hostname']}")
    if info.get("domain"):
        lines.append(f"  Domain: {info['domain']}")
    if info.get("model"):
        lines.append(f"  Model: {info['model']}")
    if info.get("ttl"):
        lines.append(f"  TTL: {info['ttl']}")
    return "\n".join(lines)


@register("stop_scan")
def _stop_scan(args, ctx=None):
    if not ctx:
        return "Cannot stop: no tool context available."
    ctx._scan_stop()
    return "Active scan stopped."


@register("port_scan")
def _port_scan(args, ctx=None):
    method = args.get("method", "tcp").lower()
    ip = args.get("ip", "")
    if not ctx:
        return "Cannot scan: no tool context available."
    if method == "udp":
        return _do_udp_scan(ip, ctx)
    return _do_tcp_scan(ip, ctx)


def _do_tcp_scan(ip, ctx):
    from src.gui.app import _do_tcp_scan_common, _TCP_SCAN_PORTS
    from src.machines import store, machine_db
    import threading
    open_ports = _do_tcp_scan_common(ip)
    machine = store.get(ip)
    if machine and open_ports:
        for p in open_ports:
            machine_db.save_tcp_port(machine.id, p)
    threading.Thread(target=ctx._run_tcpscan, args=(ip, "connect", True), daemon=True).start()
    if not open_ports:
        return f"No common TCP ports open on {ip} (scanned {len(_TCP_SCAN_PORTS)} ports). Full scan running in background."
    ports_str = ', '.join(str(p) for p in open_ports)
    return f"TCP ports open on {ip}: {ports_str}\nFull scan of remaining 65535 ports running in background."


def _do_udp_scan(ip, ctx):
    from src.gui.app import _do_udp_scan_common, _UDP_SCAN_PORTS
    from src.machines import store, machine_db
    import threading
    open_ports = _do_udp_scan_common(ip)
    machine = store.get(ip)
    if machine and open_ports:
        for p in open_ports:
            machine_db.save_udp_port(machine.id, p)
    threading.Thread(target=ctx._run_udpscan, args=(ip, True), daemon=True).start()
    if not open_ports:
        return f"No common UDP ports open on {ip} (scanned {len(_UDP_SCAN_PORTS)} ports). Full scan running in background."
    ports_str = ', '.join(str(p) for p in open_ports)
    return f"UDP ports open on {ip}: {ports_str}\nFull scan of remaining 65535 ports running in background."


@register("ping")
def _ping(args, ctx=None):
    ip = args.get("ip", "")
    if not ctx:
        return "Cannot ping: no tool context available."
    from src.gui.app import _do_ping
    result = _do_ping(ip)
    if result is None:
        return f"{ip}: no response"
    rtt_ms, ttl = result
    ttl_part = f"  ttl={ttl}" if ttl is not None else ""
    return f"{ip}: time={rtt_ms:.1f}ms{ttl_part}"


@register("nslookup")
def _nslookup(args, ctx=None):
    host = args.get("host", "")
    if not ctx:
        return "Cannot lookup: no tool context available."
    from src.gui.app import _do_nslookup
    return _do_nslookup(host)


@register("port_inspector")
def _port_inspector(args, ctx=None):
    ip = args.get("ip", "")
    port = int(args.get("port", 80))
    if not ctx:
        return "Cannot inspect port: no tool context available."
    from src.gui.app import _do_port_inspection
    from src.machines import store, machine_db
    results = _do_port_inspection(ip, port)
    machine = store.get(ip)
    if machine:
        for label, text in results:
            machine_db.save_banner(machine.id, port, text, label)
    if not results:
        return f"No responses on {ip}:{port}"
    lines = [f"Port inspector results for {ip}:{port}:"]
    for label, text in results:
        truncated = text[:200] + "..." if len(text) > 200 else text
        lines.append(f"  [{label}]: {truncated}")
    return "\n".join(lines)


@register("bannergrab")
def _bannergrab(args, ctx=None):
    ip = args.get("ip", "")
    port = int(args.get("port", 0))
    if not ip or not port:
        return "Missing ip or port."
    from src.gui.app import _do_bannergrab
    text = _do_bannergrab(ip, port)
    if text is None:
        return f"Bannergrab {ip}:{port} failed (connection error or timeout)"
    if not text:
        return f"No response on {ip}:{port}"
    return text[:500]


@register("nmap")
def _nmap(args, ctx=None):
    import os
    import re
    import shlex
    import shutil
    import subprocess
    from src.info import get as info_get
    from src.machines import store, machine_db
    from src import settings

    if not settings.get("agent_nmap", False):
        return "nmap is disabled. Enable it in Settings > Safety."

    target = args.get("target", "").strip()
    arguments = args.get("arguments", "").strip()

    if not target:
        return "Error: no target specified."

    nmap_bin = info_get("nmap_path", "") or shutil.which("nmap")
    if not nmap_bin:
        return "Error: nmap is not available on this system."

    try:
        arg_list = shlex.split(arguments)
    except ValueError as e:
        return f"Error parsing nmap arguments: {e}"

    cmd = [nmap_bin] + arg_list + [target]
    env = os.environ.copy()
    env["LANG"] = "C"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "Error: nmap scan timed out."
    except FileNotFoundError:
        return f"Error: nmap binary not found at '{nmap_bin}'."
    except Exception as e:
        return f"Error running nmap: {e}"

    output = (proc.stdout + proc.stderr).strip()
    if not output:
        return "(nmap produced no output)"

    machine = store.get(target)
    if machine:
        saved = []
        for line in output.splitlines():
            m = re.match(r"(\d+)/(tcp|udp)\s+open", line)
            if m:
                port = int(m.group(1))
                proto = m.group(2)
                if proto == "udp":
                    if machine_db.save_udp_port(machine.id, port):
                        saved.append(f"{port}/udp")
                else:
                    if machine_db.save_tcp_port(machine.id, port):
                        saved.append(f"{port}/tcp")
        if saved:
            output += f"\n\n[automatically saved to machine #{machine.id}: {', '.join(saved)}]"

    return output


@register("delete_credential")
def _delete_credential(args, ctx=None):
    from src.machines.credential_db import load_credentials, delete_credential
    username = args.get("username", "")
    for c in load_credentials():
        if c["username"] == username:
            delete_credential(c["id"])
            return f"Credential '{username}' deleted."
    return f"Credential '{username}' not found."


@register("delete_machine")
def _delete_machine(args, ctx=None):
    from src.machines import store, machine_db
    target = args.get("target", "")
    for m in store.get_all():
        if str(m.id) == target or m.ip == target:
            machine_db.delete_machine_db(m.id)
            store.remove(m.ip)
            return f"Machine #{m.id} ({m.ip}) deleted."
    return f"Machine '{target}' not found."


@register("delete_domain")
def _delete_domain(args, ctx=None):
    from src.machines import domain_db
    domain = args.get("domain", "")
    if domain_db.exists(domain):
        domain_db.delete_domain(domain)
        return f"Domain '{domain}' deleted."
    return f"Domain '{domain}' not found."


@register("delete_password")
def _delete_password(args, ctx=None):
    from src.machines.credential_db import delete_password, load_passwords
    pwd = args.get("password", "")
    if pwd in load_passwords():
        delete_password(pwd)
        return f"Password deleted."
    return f"Password not found."


@register("webfetch")
def _webfetch(args, ctx=None):
    from src.llm.web import fetch_url, fetch_raw
    from urllib.parse import urlparse
    url = args.get("url", "")
    fmt = args.get("format", "markdown")
    method = args.get("method", "GET").upper()
    body = args.get("body") or None
    content_type = args.get("content_type") or None
    antibot = bool(args.get("antibot", False))
    headers = args.get("headers")
    if isinstance(headers, dict):
        headers = {str(k): str(v) for k, v in headers.items()}
    else:
        headers = None

    if fmt == "raw":
        try:
            status, resp_headers, resp_body, ct = fetch_raw(url, method=method, body=body, content_type=content_type, headers=headers, antibot=antibot)
        except Exception as e:
            return f"Error fetching URL: {e}"
        lines = [f"HTTP {status}"]
        for k, v in resp_headers.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        if isinstance(resp_body, str) and resp_body.startswith("[non-text"):
            return "\n".join(lines) + resp_body
        body_lines = resp_body.split("\n")
        preview = "\n".join(body_lines[:60])
        byte_len = len(resp_body.encode("utf-8"))
        from src.elwand_paths import cache_dir
        import time as _time
        ts = int(_time.time())
        filename = f"tool_{ts}_webfetch_raw.raw"
        path = os.path.join(str(cache_dir()), filename)
        try:
            with open(path, "w") as f:
                f.write(resp_body)
        except (PermissionError, OSError):
            pass
        lines.append(preview)
        lines.append(f"\n... output truncated ({len(body_lines)} lines, {byte_len} bytes). To read the rest: read_cache(\"{filename}\")")
        result = "\n".join(lines)
        if not result.startswith("Error"):
            try:
                parsed = urlparse(url)
                host = parsed.hostname
                path = parsed.path or "/"
                from src.machines import store, machine_db, domain_db
                machine = store.get(host)
                if machine:
                    machine_db.save_directory(machine.id, path)
                elif domain_db.exists(host):
                    domain_db.save_directory(host, path)
            except Exception:
                pass
        return result

    result = fetch_url(
        url,
        format=fmt,
        offset=int(args.get("offset", 1)),
        limit=int(args.get("limit", 0)) or None,
        method=method,
        body=body,
        content_type=content_type,
        headers=headers,
        antibot=antibot,
    )
    if not result.startswith("Error"):
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            path = parsed.path or "/"
            from src.machines import store, machine_db, domain_db
            machine = store.get(host)
            if machine:
                machine_db.save_directory(machine.id, path)
            elif domain_db.exists(host):
                domain_db.save_directory(host, path)
        except Exception:
            pass
    return result


@register("websearch")
def _websearch(args, ctx=None):
    from src.llm.web import web_search
    return web_search(
        args.get("query", ""),
        num_results=args.get("num_results", 20),
    )


@register("list_repo")
def _list_repo(args, ctx=None):
    owner = args.get("owner", "").strip()
    repo = args.get("repo", "").strip()
    path = args.get("path", "").strip() or ""
    if not owner or not repo:
        return "Missing owner or repo."
    import requests
    url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    if path:
        url += f"/{path}"
    headers = {"Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        return f"GitHub API error: {e}"
    if resp.status_code == 404:
        return f"Repo or path not found: {owner}/{repo}/{path}".rstrip("/")
    if resp.status_code == 403:
        return f"GitHub API rate limited (60 req/hour unauthenticated). Wait and retry."
    if resp.status_code != 200:
        return f"GitHub API returned {resp.status_code}: {resp.text[:300]}"
    try:
        data = resp.json()
    except Exception:
        return f"Invalid JSON from GitHub API."
    if not isinstance(data, list):
        return f"Not a directory: {data.get('name', path)} is a file ({data.get('size', 0)} bytes). Use webfetch with: {data.get('download_url', '')}"
    lines = [f"Contents of {owner}/{repo}/{path}:".rstrip("/").rstrip(":") + ":"]
    dirs = []
    files = []
    for item in data:
        name = item.get("name", "?")
        if item.get("type") == "dir":
            dirs.append(f"  [DIR]  {name}/")
        else:
            size = item.get("size", 0)
            dl = item.get("download_url", "")
            if size >= 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            if dl:
                files.append(f"  [{size_str}] {name} — {dl}")
            else:
                files.append(f"  [{size_str}] {name}")
    lines.extend(dirs)
    lines.extend(files)
    if not dirs and not files:
        lines.append("  (empty)")
    return "\n".join(lines)


@register("add_person")
def _add_person(args, ctx=None):
    from src.machines.people_db import save_person
    pid = save_person(
        first_name=args.get("first_name", ""),
        last_name=args.get("last_name", ""),
        company=args.get("company", ""),
        domain=args.get("domain", ""),
        username=args.get("username", ""),
        role=args.get("role", ""),
        linkedin_url=args.get("linkedin_url", ""),
        source=args.get("source", "agent"),
        interests=args.get("interests", ""),
    )
    name = f"{args.get('first_name','')} {args.get('last_name','')}".strip() or f"#{pid}"
    return f"Person '{name}' added as #{pid}."


@register("delete_person")
def _delete_person(args, ctx=None):
    from src.machines.people_db import load_person, delete_person
    pid = args.get("person_id")
    if not pid:
        return "Missing person_id."
    p = load_person(int(pid))
    if not p:
        return f"Person #{pid} not found."
    delete_person(int(pid))
    name = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
    return f"Person '{name}' (#{pid}) deleted."


@register("dicma_generate_users")
def _dicma_generate_users(args, ctx=None):
    from src.tools.dicma import engine as dicma
    from src.elwand_paths import lst_dir
    full_name = args.get("full_name", "")
    if not full_name:
        return "Missing full_name."
    out_name = args.get("output_name", "dicma_users.txt")
    out_path = os.path.join(str(lst_dir()), out_name)
    dicma.LIGHT_MODE = False
    dicma.OUTPUT_FILE_BULEAN = True
    dicma.VERBOSE = False
    dicma.process_input_user(full_name, out_path)
    return f"Usernames generated for '{full_name}' → saved to {out_path}"


@register("dicma_find_related")
def _dicma_find_related(args, ctx=None):
    from src.tools.dicma import engine as dicma
    from src.elwand_paths import lst_dir
    from src.llm.config import load as llm_load, get_provider, get_active_model
    words_str = args.get("words", "")
    if not words_str:
        return "Missing words."
    words = [w.strip() for w in words_str.split(",") if w.strip()]
    n1 = int(args.get("n1", 50))
    n2 = int(args.get("n2", 0))
    n3 = int(args.get("n3", 0))
    out_name = args.get("output_name", "dicma_related.txt")
    out_path = os.path.join(str(lst_dir()), out_name)
    config = llm_load()
    pid = config.get("active_provider", "")
    provider = get_provider(config)
    model = get_active_model(config)
    api_key = provider.get("api_key", "")
    base_url = provider.get("base_url", "")
    if not base_url or not model:
        return "No active LLM config. Configure in Settings → Models."
    if not api_key and pid == "opencode":
        api_key = "public"
    if not api_key:
        return "No active LLM config. Configure in Settings → Models."
    from openai import OpenAI
    if pid == "opencode":
        from src.llm.client import _OPENCODE_UA, _STAINLESS_HEADER_KEYS
        default_headers = {"User-Agent": _OPENCODE_UA}
        for k in _STAINLESS_HEADER_KEYS:
            default_headers[k] = ""
        client = OpenAI(api_key=api_key, base_url=base_url,
                        default_headers=default_headers)
    else:
        client = OpenAI(api_key=api_key, base_url=base_url)
    expanded = dicma.ml_expand_words(client, model, words, n1, n2, n3)
    result = [w for w in expanded if w not in set(words)]
    dicma.save_list_to_file(result, out_path)
    return (f"Found {len(result)} related words from {len(words)} seed(s). "
            f"Saved to {out_path}")


@register("dicma_generate_passwords")
def _dicma_generate_passwords(args, ctx=None):
    from src.tools.dicma import engine as dicma
    from src.elwand_paths import lst_dir
    words_str = args.get("words", "")
    if not words_str:
        return "Missing words."
    words = [w.strip() for w in words_str.split(",") if w.strip()]
    mode = args.get("mode", "normal")
    out_name = args.get("output_name", "dicma_passwords.txt")
    out_path = os.path.join(str(lst_dir()), out_name)
    light = mode == "light"
    full = mode == "full"
    dicma.LIGHT_MODE = light
    dicma.FULL_MODE = full
    dicma.OUTPUT_FILE_BULEAN = True
    dicma.VERBOSE = False
    dicma._NO_MULTIPROC = True
    dicma.process_passwd(words, out_path)
    return f"Passwords generated ({mode} mode) from {len(words)} word(s) → saved to {out_path}"


@register("dicma_generate_rules")
def _dicma_generate_rules(args, ctx=None):
    from src.tools.dicma import engine as dicma
    from src.elwand_paths import lst_dir, rules_dir
    mode = args.get("mode", "normal")
    dict_name = args.get("dictionary", "")
    out_name = args.get("output_name", "dicma_rules.rule")
    out_path = os.path.join(str(rules_dir()), out_name)
    light = mode == "light"
    full = mode == "full"
    if dict_name:
        dict_path = os.path.join(str(lst_dir()), dict_name)
        if not os.path.isfile(dict_path):
            return f"Dictionary not found: {dict_name}"
        suffixes, prefixes, numbers, symbols = dicma.extract_patterns(dict_path)
        all_suf = list(dict.fromkeys(suffixes + numbers + symbols))
        all_pre = list(dict.fromkeys(prefixes + numbers + symbols))
    else:
        all_suf = list(dict.fromkeys(
            dicma.BASIC_SUFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
        all_pre = list(dict.fromkeys(
            dicma.BASIC_PREFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
    rules = dicma.generate_rules(all_suf, all_pre, light=light, full=full)
    dicma.save_list_to_file(rules, out_path)
    return f"{len(rules)} rules generated ({mode} mode) → saved to {out_path}"


@register("hashcat_crack")
def _hashcat_crack(args, ctx=None):
    if not ctx:
        return "Cannot crack: no tool context available."
    hash_val = args.get("hash_value", "")
    wordlist_name = args.get("wordlist", "")
    if not hash_val or not wordlist_name:
        return "Missing hash_value or wordlist."
    from src.machines.credential_db import load_hashes
    from src.elwand_paths import hashcat_db, lst_dir
    mode = None
    htype = ""
    for h in load_hashes():
        stored_hash = h.get("hash", "")
        if stored_hash == hash_val or (
                len(hash_val) >= 16 and stored_hash.startswith(hash_val)):
            htype = h.get("type", "")
            mode = h.get("hascat_mode", "")
            hash_val = stored_hash
            break
    if not mode and htype:
        try:
            import sqlite3
            conn = sqlite3.connect(str(hashcat_db()))
            row = conn.execute(
                'SELECT "Hash-Mode" FROM DefaultMode WHERE "Hash-Name" = ?',
                (htype,)).fetchone()
            conn.close()
            if row and row[0] and row[0] != -1:
                mode = str(row[0])
        except Exception:
            pass
    if not mode:
        return (f"Could not determine hashcat mode for '{hash_val[:30]}...'. "
                f"Add it via 'add_hash' first.")
    wl_path = os.path.join(str(lst_dir()), wordlist_name)
    if not os.path.isfile(wl_path):
        return f"Wordlist not found: {wordlist_name}"
    from src.tools.hashcat import HashcatEngine
    from src.machines.credential_db import save_password as _sp
    engine = HashcatEngine(
        mode=mode, hash_value=hash_val, wordlist=wl_path,
        on_output=lambda text, color=None: None,
        on_progress=lambda done, total, recovered: None,
        on_cracked=lambda hv, plain, sp=_sp: (
            ctx.console.after(0, lambda: ctx.console.success(
                f"Cracked: {plain}")),
            sp(plain)
        ),
        on_done=lambda cracked: ctx.console.after(0, lambda: ctx.console.info(
            f"Hashcat done. {len(cracked)} cracked.") if cracked
            else ctx.console.info("Hashcat done. No passwords found.")),
    )
    engine.start()
    return (f"Hashcat started: mode={mode} wordlist={wordlist_name} "
            f"hash='{hash_val[:30]}...'. Cracked passwords will be saved "
            f"to inventory automatically.")


@register("bruteforce_start")
def _bruteforce_start(args, ctx=None):
    if not ctx:
        return "Cannot start bruteforce: no tool context available."
    proto = args.get("protocol", "")
    target = args.get("target", "")
    port = args.get("port", 0)
    if not proto or not target:
        return "Missing protocol or target."
    ctx._cmd_use_bruteforce([proto, target, str(port)])
    return f"Bruteforce ({proto}) started against {target}."


@register("fuzz_start")
def _fuzz_start(args, ctx=None):
    if not ctx:
        return "Cannot start fuzzer: no tool context available."
    method = args.get("method", "")
    target = args.get("target", "")
    wordlist = args.get("wordlist", "")
    port = args.get("port", 80)
    scheme = args.get("scheme", "http")
    skip_codes = args.get("skip_codes", [404]) or []
    hide_size = args.get("hide_size")
    workers = int(args.get("workers", 50))
    if hide_size and len(hide_size) == 2:
        hide_size = tuple(hide_size)
    else:
        hide_size = None
    if scheme not in ("http", "https"):
        scheme = "http"
    if not method or not target or not wordlist:
        return "Missing method, target, or wordlist."
    from src.elwand_paths import lst_dir
    wl_path = os.path.join(str(lst_dir()), wordlist)
    if not os.path.isfile(wl_path):
        return f"Wordlist not found: {wordlist}"
    resolved_ip = ctx._resolve_to_ip(target)
    from src.machines import store, machine_db
    machine = store.get(resolved_ip or target)
    display_target = resolved_ip or target
    url_template = None
    if method == "directory":
        url_template = f"{scheme}://{display_target}:{port}/FUZZ"

    import random, string, ssl, urllib.request
    word = ''.join(random.choices(string.ascii_lowercase, k=10))
    if method == "directory":
        url = url_template.replace("FUZZ", word)
        req = urllib.request.Request(
            url, headers={"User-Agent": "Elwand/1.0"})
    elif method == "vhost":
        ip = resolved_ip or target
        req = urllib.request.Request(
            f"{scheme}://{ip}/",
            headers={"User-Agent": "Elwand/1.0",
                     "Host": f"{word}.{target}"})
    else:
        req = urllib.request.Request(
            f"{scheme}://{word}.{target}/",
            headers={"User-Agent": "Elwand/1.0"})
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        resp = urllib.request.urlopen(req, timeout=5, context=ssl_ctx)
        body = resp.read(10240)
        status = resp.status
    except urllib.request.HTTPError as e:
        body = e.read(10240)
        status = e.code
    except Exception:
        status = None
    from src.tools.fuzz.engine import SHOW_CODES as ENGINE_CODES
    show_codes = ENGINE_CODES - set(skip_codes)
    wildcard_hit = status is not None and status in show_codes
    if wildcard_hit and hide_size:
        lo, hi = hide_size
        if lo <= len(body) <= hi:
            wildcard_hit = False
    if wildcard_hit:
        return (
            f"WILDCARD DETECTED — random {method} request responded with "
            f"status {status}, {len(body)} bytes. "
            f"Server may have a catch-all response. Fuzzing aborted. "
            f"Adjust skip_codes or hide_size filter if the wildcard response "
            f"is expected."
        )

    from src.machines import domain_db
    def _on_found(word, display):
        if method == "directory":
            if machine:
                machine_db.save_directory(machine.id, f"/{word}")
        elif method == "vhost":
            domain_db.save_subdomain(target, f"{word}.{target}", "vhost")
        else:
            domain_db.save_subdomain(target, f"{word}.{target}", "dns")
    from src.tools.fuzz import FuzzEngine
    engine = FuzzEngine(
        target=target,
        wordlist_path=wl_path,
        method=method,
        target_ip=resolved_ip,
        url_template=url_template,
        workers=workers,
        show_codes=show_codes,
        on_found=_on_found,
        scheme=scheme,
        hide_size_range=hide_size,
    )
    engine.start()
    return f"Fuzzing ({method}) started against {target} with {wordlist}. Results will be saved to directories and subdomains. Use check_fuzz_results to retrieve them."


@register("listener")
def _listener(args, ctx=None):
    if not ctx:
        return "Cannot manage listener: no tool context available."
    action = args.get("action", "")
    service = args.get("service", "")
    if service not in ("shells-listener", "mdns-listener"):
        return f"Unknown service: {service}"
    if action == "start":
        ctx._cmd_start([service])
    elif action == "stop":
        ctx._cmd_stop([service])
    else:
        return f"Unknown action: {action}. Use 'start' or 'stop'."
    return f"{service} {action}ed."


def _list_files_common(directory_func, empty_msg, type_label):
    try:
        d = str(directory_func())
        files = sorted(
            f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))
        )
    except OSError:
        return f"Could not read directory."
    if not files:
        return empty_msg
    result = f"{type_label} in {d}:\n"
    for f in files:
        path = os.path.join(d, f)
        size = os.path.getsize(path)
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.0f} KB"
        else:
            size_str = f"{size} B"
        result += f"  {f} ({size_str})\n"
    return result


@register("list_files")
def _list_files(args, ctx=None):
    ft = args.get("file_type", "")
    from src.elwand_paths import lst_dir, rules_dir, pocs_dir, cache_dir
    if ft == "dictionary":
        return _list_files_common(lst_dir, "No dictionary files found.", "Dictionary files")
    if ft == "rule":
        return _list_files_common(rules_dir, "No rule files found.", "Rule files")
    if ft == "poc":
        return _list_files_common(pocs_dir, "No POC files found.", "POC files")
    if ft == "cache":
        return _list_files_common(cache_dir, "No cached files.", "Cached files")
    return f"Unknown file_type: {ft}. Use dictionary, rule, poc, or cache."


def _resolve_poc_path(filename):
    from src.elwand_paths import pocs_dir
    base = str(pocs_dir())
    resolved = os.path.normpath(os.path.join(base, filename))
    if not resolved.startswith(os.path.normpath(base) + os.sep) and resolved != os.path.normpath(base):
        return None
    return resolved


def _resolve_report_path(filename):
    from src.elwand_paths import reports_dir
    base = str(reports_dir())
    resolved = os.path.normpath(os.path.join(base, filename))
    if not resolved.startswith(os.path.normpath(base) + os.sep) and resolved != os.path.normpath(base):
        return None
    return resolved


def _read_text_file(path, label, args, default_limit=200):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (PermissionError, OSError) as e:
        return f"Error reading {label}: {e}"

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    regex = args.get("regex", "").strip()

    if regex:
        import re
        try:
            pattern = re.compile(regex, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"
        ctx_before = max(0, int(args.get("context_before", 2)))
        ctx_after = max(0, int(args.get("context_after", 10)))
        matches = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not matches:
            return f"{label} ({total_lines} lines, 0 matches for '{regex}')"
        result = [f"{label} ({total_lines} lines, {len(matches)} matches for '{regex}'):"]
        shown_until = -1
        shown_count = 0
        for m in matches:
            start = max(0, m - ctx_before)
            end = min(total_lines, m + ctx_after + 1)
            if start <= shown_until:
                start = shown_until + 1
            if start >= end:
                continue
            shown_count += 1
            result.append("---")
            for j in range(start, end):
                marker = ">" if j == m else " "
                result.append(f"{marker} Line {j+1}: {lines[j].rstrip()}")
            shown_until = end - 1
        result.append(f"---\n({shown_count} match groups, {len(matches)} total matches)")
        return "\n".join(result)

    offset = int(args.get("offset", 1))
    limit = int(args.get("limit", default_limit))
    if offset < 1:
        offset = 1
    if offset > total_lines:
        offset = total_lines
    start = offset - 1
    end = start + limit
    sliced = lines[start:end]
    result = "".join(sliced)
    header = f"{label} ({total_lines} lines"
    if len(sliced) < total_lines:
        header += f", showing lines {offset}-{min(end, total_lines)}"
    header += "):\n"
    return header + result


@register("read_cache")
def _read_cache(args, ctx=None):
    filename = args.get("filename", "").strip()
    if not filename:
        return "Missing filename."
    path = _resolve_cache_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"Cached file '{filename}' not found."
    return _read_text_file(path, f"cache/{filename}", args)


@register("read_evidence")
def _read_evidence(args, ctx=None):
    name = args.get("name", "").strip()
    filename = args.get("filename", "").strip()
    if not name or not filename:
        return "Missing name or filename."
    path = _resolve_evidence_path(name, filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"File '{filename}' not found in evidence session '{name}'."
    return _read_text_file(path, f"evidence/{name}/{filename}", args)


@register("delete_file")
def _delete_file(args, ctx=None):
    from src.elwand_paths import lst_dir, rules_dir, pocs_dir, cache_dir
    ftype = args.get("file_type", "")
    fname = args.get("filename", "")
    if not ftype or not fname:
        return "Missing file_type or filename."
    if ftype == "rule":
        base = str(rules_dir())
    elif ftype == "poc":
        base = str(pocs_dir())
    elif ftype == "cache":
        base = str(cache_dir())
    else:
        base = str(lst_dir())
    base = os.path.normpath(base)
    path = os.path.normpath(os.path.join(base, fname))
    if not path.startswith(base + os.sep):
        return f"Invalid filename: {fname}"
    if not os.path.isfile(path):
        return f"File not found: {fname}"
    os.remove(path)
    return f"{ftype.capitalize()} '{fname}' deleted."


@register("delete_evidence")
def _delete_evidence(args, ctx=None):
    import shutil
    from src.elwand_paths import evidence_dir
    name = args.get("name", "")
    if not name:
        return "Missing evidence name."
    base = str(evidence_dir())
    if name == "all":
        if os.path.isdir(base):
            shutil.rmtree(base)
            os.makedirs(base, exist_ok=True)
        return "All evidence deleted."
    path = _resolve_evidence_path(name, "")
    if not path or not os.path.isdir(path):
        return f"Evidence session '{name}' not found."
    shutil.rmtree(path)
    return f"Evidence '{name}' deleted."


@register("delete_shell")
def _delete_shell(args, ctx=None):
    from src.shells import shell_db
    sid = args.get("shell_id", "")
    if not sid:
        return "Missing shell_id."
    if sid == "all":
        shells = shell_db.get_all()
        count = len(shells)
        for s in shells:
            shell_db.close_session(s["id"])
        return f"{count} shell session(s) deleted."
    try:
        shell_db.close_session(int(sid))
        return f"Shell session #{sid} deleted."
    except Exception:
        return f"Shell session #{sid} not found."


@register("shell_exec")
def _shell_exec(args, ctx=None):
    sid = int(args.get("shell_id", 0))
    cmd = args.get("command", "")
    if not sid or not cmd:
        return "Missing shell_id or command."
    from src.shells import shell_db, send_command, send_raw
    s = shell_db.get_session(sid)
    if not s:
        return f"Shell session #{sid} not found."
    if s.get("status") != "connected":
        return f"Shell #{sid} is not connected (status: {s.get('status', '?')})."
    from src.gui.views.shell_list import is_agent_allowed
    if not is_agent_allowed(sid):
        return (f"Agent access is disabled for shell #{sid}. "
                "Enable the 'Agent' toggle in that shell's view first.")
    shell_db.enable_agent_buffer(sid)
    shell_db.drain_agent_output(sid)
    shell_db.touch_agent(sid, cmd)
    if not send_command(sid, cmd):
        return f"Failed to send command to shell #{sid}."
    import time, re
    prefix = f"Shell #{sid} [{cmd[:80]}]: "
    all_out = []
    for _ in range(20):
        if ctx and getattr(ctx, "_agent_stop_event", None) and ctx._agent_stop_event.is_set():
            send_raw(sid, "\x03")
            time.sleep(0.3)
            out = shell_db.drain_agent_output(sid)
            if out:
                all_out.append(out)
            combined = "".join(all_out)
            return _fmt_shell(f"{prefix}stopped by user", combined) if combined else f"{prefix}stopped by user before output arrived"
        time.sleep(0.1)
        out = shell_db.drain_agent_output(sid)
        if out:
            all_out.append(out)
    if not all_out:
        return f"{prefix}no immediate output [running] -- use shell_wait or shell_interrupt"
    combined = "".join(all_out)
    clean = re.sub(r'\x1b\][^\x07]*\x07', '', combined)
    clean = re.sub(r'\x1b\[[?0-9;]*[a-zA-Z]', '', clean)
    if re.search(r'(?i)(?:password|passphrase).*[:：]', clean):
        send_raw(sid, "\x03")
        time.sleep(0.5)
        out = shell_db.drain_agent_output(sid)
        if out:
            all_out.append(out)
        combined = "".join(all_out)
        return _fmt_shell(f"{prefix}password prompt detected, interrupted", combined)
    if re.search(r'(?:^|\n)[^\n]*[$#>]\s*$', clean):
        return _fmt_shell(f"{prefix}[finished]", combined)
    return _fmt_shell(f"{prefix}[running] -- use shell_wait for more output, shell_interrupt to stop", combined)


@register("shell_wait")
def _shell_wait(args, ctx=None):
    sid = int(args.get("shell_id", 0))
    if not sid:
        return "Missing shell_id."
    from src.shells import shell_db, send_raw
    s = shell_db.get_session(sid)
    if not s:
        return f"Shell session #{sid} not found."
    if s.get("status") != "connected":
        return f"Shell #{sid} is not connected."
    from src.gui.views.shell_list import is_agent_allowed
    if not is_agent_allowed(sid):
        return (f"Agent access is disabled for shell #{sid}. "
                "Enable the 'Agent' toggle in that shell's view first.")
    import time, re
    prefix = f"Shell #{sid}: "
    all_out = []
    stale = 0
    for _ in range(100):
        if ctx and getattr(ctx, "_agent_stop_event", None) and ctx._agent_stop_event.is_set():
            send_raw(sid, "\x03")
            time.sleep(0.3)
            out = shell_db.drain_agent_output(sid)
            if out:
                all_out.append(out)
            combined = "".join(all_out)
            return _fmt_shell(f"{prefix}stopped by user", combined) if combined else f"{prefix}stopped by user, no output"
        time.sleep(0.1)
        out = shell_db.drain_agent_output(sid)
        if out:
            all_out.append(out)
            stale = 0
        else:
            stale += 1
        if all_out:
            combined = "".join(all_out)
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', combined)
            clean = re.sub(r'\x1b\[[?0-9;]*[a-zA-Z]', '', clean)
            if re.search(r'(?:^|\n)[^\n]*[$#>]\s*$', clean):
                return _fmt_shell(f"{prefix}[finished]", combined)
        if stale > 20:
            if all_out:
                combined = "".join(all_out)
                return _fmt_shell(f"{prefix}[paused] -- output stopped, may be waiting for input or finished", combined)
            else:
                return f"{prefix}[idle] -- no output, no command may be running"
    combined = "".join(all_out)
    return _fmt_shell(f"{prefix}[running]", combined) if combined else f"{prefix}[running] still no output after 10s"


@register("shell_interrupt")
def _shell_interrupt(args, ctx=None):
    sid = int(args.get("shell_id", 0))
    if not sid:
        return "Missing shell_id."
    from src.shells import shell_db, send_raw
    s = shell_db.get_session(sid)
    if not s:
        return f"Shell session #{sid} not found."
    if s.get("status") != "connected":
        return f"Shell #{sid} is not connected."
    from src.gui.views.shell_list import is_agent_allowed
    if not is_agent_allowed(sid):
        return (f"Agent access is disabled for shell #{sid}. "
                "Enable the 'Agent' toggle in that shell's view first.")
    import time, re
    prefix = f"Shell #{sid}: "
    send_raw(sid, "\x03")
    all_out = []
    for _ in range(20):
        time.sleep(0.1)
        if ctx and getattr(ctx, "_agent_stop_event", None) and ctx._agent_stop_event.is_set():
            out = shell_db.drain_agent_output(sid)
            if out:
                all_out.append(out)
            combined = "".join(all_out)
            return _fmt_shell(f"{prefix}interrupted, also stopped by user", combined) if combined else f"{prefix}interrupted, also stopped by user"
        out = shell_db.drain_agent_output(sid)
        if out:
            all_out.append(out)
        combined = "".join(all_out)
        if combined:
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', combined)
            clean = re.sub(r'\x1b\[[?0-9;]*[a-zA-Z]', '', clean)
            if re.search(r'(?:^|\n)[^\n]*[$#>]\s*$', clean):
                return _fmt_shell(f"{prefix}[interrupted]", combined)
    combined = "".join(all_out)
    return _fmt_shell(f"{prefix}[interrupted]", combined) if combined else f"{prefix}[interrupted] no output after Ctrl+C"


@register("poc_write")
def _poc_write(args, ctx=None):
    filename = args.get("filename", "").strip()
    content = args.get("content", "")
    if not filename:
        return "Missing filename."
    if not content:
        return "Missing content."
    if not filename.endswith(".py"):
        return "Filename must end with .py"
    path = _resolve_poc_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    try:
        with open(path, "w") as f:
            f.write(content)
    except (PermissionError, OSError) as e:
        return f"Error writing {filename}: {e}"
    return f"POC '{filename}' written ({len(content)} chars)."


@register("poc_read")
def _poc_read(args, ctx=None):
    filename = args.get("filename", "").strip()
    if not filename:
        return "Missing filename."
    path = _resolve_poc_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"POC '{filename}' not found."
    try:
        with open(path, "r") as f:
            content = f.read()
    except (PermissionError, OSError) as e:
        return f"Error reading {filename}: {e}"
    offset = int(args.get("offset", 1))
    limit = int(args.get("limit", 2000))
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    if offset < 1:
        offset = 1
    if offset > total_lines:
        offset = total_lines
    start = offset - 1
    end = start + limit
    sliced = lines[start:end]
    result = "".join(sliced)
    header = f"POC '{filename}' ({total_lines} lines"
    if len(sliced) < total_lines:
        header += f", showing lines {offset}-{min(end, total_lines)}"
    header += "):\n"
    result = header + result
    if len(content) > 50000:
        result = result[:50000] + "\n... (truncated at 50000 chars)"
    return result


@register("poc_edit")
def _poc_edit(args, ctx=None):
    filename = args.get("filename", "").strip()
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    replace_all = args.get("replace_all", False)
    new_name = args.get("new_filename", "").strip() or None
    if not filename:
        return "Missing filename."
    if old_string == new_string and not new_name:
        return "No changes to apply: old_string and new_string are identical."
    if not old_string and not new_name:
        return "old_string must not be empty. Use poc_write to create or overwrite a file."
    path = _resolve_poc_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"POC '{filename}' not found."
    try:
        with open(path, "r") as f:
            content = f.read()
    except (PermissionError, OSError) as e:
        return f"Error reading {filename}: {e}"
    if old_string and old_string != new_string:
        occurrences = content.count(old_string)
        if occurrences == 0:
            return "Could not find old_string in the file. It must match exactly, including whitespace and indentation."
        if occurrences > 1 and not replace_all:
            return f"Found {occurrences} exact matches for old_string. Provide more surrounding context to make it unique, or set replace_all to true."
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        try:
            with open(path, "w") as f:
                f.write(new_content)
        except (PermissionError, OSError) as e:
            return f"Error writing {filename}: {e}"
        plural = "s" if occurrences > 1 else ""
        edit_msg = f": {occurrences} replacement{plural} made"
    else:
        edit_msg = ""

    if new_name:
        if not new_name.endswith(".py"):
            return "New filename must end with .py"
        new_path = _resolve_poc_path(new_name)
        if not new_path:
            return f"Invalid new filename: {new_name}"
        if os.path.exists(new_path):
            return f"A POC named '{new_name}' already exists."
        try:
            os.rename(path, new_path)
        except (PermissionError, OSError) as e:
            return f"Error renaming to {new_name}: {e}"
        return f"POC '{filename}' renamed to '{new_name}'{edit_msg}."

    return f"POC '{filename}' edited{edit_msg}." if edit_msg else f"No changes applied to '{filename}'."


@register("poc_exec")
def _poc_exec(args, ctx=None):
    filename = args.get("filename", "").strip()
    if not filename:
        return "Missing filename."
    from src import settings
    if not settings.get("agent_exec_pocs", False):
        return "POC execution is disabled. Enable it in Settings > Safety."
    path = _resolve_poc_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"POC '{filename}' not found."
    import subprocess
    try:
        proc = subprocess.run(
            ["python3", path],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return f"POC '{filename}' timed out after 30 seconds."
    except FileNotFoundError:
        return "python3 is not available on this system."
    except Exception as e:
        return f"Error executing POC: {e}"
    output = proc.stdout
    if proc.stderr:
        output += "\n" + proc.stderr
    if not output.strip():
        return f"POC '{filename}' executed (exit {proc.returncode}) with no output."
    lines = output.splitlines()
    if len(lines) > 10:
        output = "\n".join(lines[-10:])
        return (f"POC '{filename}' (exit {proc.returncode})"
                f"[{len(lines)} lines total, last 10]:\n{output}")
    return f"POC '{filename}' (exit {proc.returncode}):\n{output.strip()}"


@register("report_write")
def _report_write(args, ctx=None):
    filename = args.get("filename", "").strip()
    content = args.get("content", "")
    if not filename:
        return "Missing filename."
    if not content:
        return "Missing content."
    if not filename.endswith(".md"):
        return "Filename must end with .md"
    path = _resolve_report_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    try:
        with open(path, "w") as f:
            f.write(content)
    except (PermissionError, OSError) as e:
        return f"Error writing {filename}: {e}"
    return f"Report '{filename}' written ({len(content)} chars)."


@register("report_read")
def _report_read(args, ctx=None):
    filename = args.get("filename", "").strip()
    if not filename:
        return "Missing filename."
    path = _resolve_report_path(filename)
    if not path:
        return f"Invalid filename: {filename}"
    if not os.path.isfile(path):
        return f"Report '{filename}' not found."
    try:
        with open(path, "r") as f:
            content = f.read()
    except (PermissionError, OSError) as e:
        return f"Error reading {filename}: {e}"

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    regex = args.get("regex", "").strip()

    if regex:
        import re
        try:
            pattern = re.compile(regex, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"
        ctx_before = max(0, int(args.get("context_before", 2)))
        ctx_after = max(0, int(args.get("context_after", 10)))
        matches = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not matches:
            return f"reports/{filename} ({total_lines} lines, 0 matches for '{regex}')"
        result = [f"reports/{filename} ({total_lines} lines, {len(matches)} matches for '{regex}'):"]
        shown_until = -1
        shown_count = 0
        for m in matches:
            start = max(0, m - ctx_before)
            end = min(total_lines, m + ctx_after + 1)
            if start <= shown_until:
                start = shown_until + 1
            if start >= end:
                continue
            shown_count += 1
            result.append("---")
            for j in range(start, end):
                marker = ">" if j == m else " "
                result.append(f"{marker} Line {j+1}: {lines[j].rstrip()}")
            shown_until = end - 1
        result.append(f"---\n({shown_count} match groups, {len(matches)} total matches)")
        result = "\n".join(result)
    else:
        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 150))
        if offset < 1:
            offset = 1
        if offset > total_lines:
            offset = total_lines
        start = offset - 1
        end = start + limit
        sliced = lines[start:end]
        result = "".join(sliced)
        header = f"reports/{filename} ({total_lines} lines"
        if len(sliced) < total_lines:
            header += f", showing lines {offset}-{min(end, total_lines)}"
        header += "):\n"
        result = header + result

    if len(result) > 5000:
        result = result[:5000] + "\n... (truncated at 5000 chars)"
    return result


def _resolve_target(ctx, target):
    import re
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
        return target
    if re.match(r"^\d+$", target):
        mid = int(target)
        from src.machines import store
        for m in store.get_all():
            if m.id == mid:
                return m.ip
    return None


def _find_credential(username):
    from src.machines import credential_db
    for c in credential_db.load_credentials():
        if c.get("username") == username:
            return c.get("password") or "", c.get("hash_nt") or ""
    return None, None


def _wait_connect(thread, timeout=15):
    import threading
    result = {}
    event = threading.Event()

    orig_on_connected = thread._on_connected
    orig_on_error = thread._on_error

    def on_connected(sid):
        result["ok"] = True
        result["sid"] = sid
        if orig_on_connected:
            orig_on_connected(sid)
        event.set()

    def on_error(msg):
        result["ok"] = False
        result["error"] = msg
        if orig_on_error:
            orig_on_error(msg)
        event.set()

    thread._on_connected = on_connected
    thread._on_error = on_error
    thread.start()
    if not event.wait(timeout=timeout):
        return f"Connection timed out after {timeout}s"
    if result.get("ok"):
        return f"Session #{result['sid']} connected successfully"
    return f"Connection failed: {result.get('error', 'unknown error')}"


@register("connect")
def _connect(args, ctx=None):
    if not ctx:
        return "Cannot connect: no tool context available."
    protocol = args.get("protocol", "").lower()
    host = args.get("host", "")
    username = args.get("username", "")
    port = int(args.get("port", 0))
    if not host or not username:
        return "Missing host or username."
    ip = _resolve_target(ctx, host)
    if not ip:
        return f"Could not resolve target: {host}"

    if protocol == "ssh":
        if not port:
            port = 22
        password, _ = _find_credential(username)
        if password is None:
            return f"No credential found for username: {username}"
        from src.shells.ssh_shell import SSHConnectionThread
        t = SSHConnectionThread(ip, port, username, password)
        return f"SSH {ip}:{port} as {username}: {_wait_connect(t)}"

    if protocol == "sftp":
        if not port:
            port = 22
        password, _ = _find_credential(username)
        if password is None:
            return f"No credential found for username: {username}"
        from src.shells.sftp_shell import SFTPConnectionThread
        t = SFTPConnectionThread(ip, port, username, password)
        return f"SFTP {ip}:{port} as {username}: {_wait_connect(t)}"

    if protocol == "ftp":
        if not port:
            port = 21
        password = ""
        if username.lower() != "anonymous":
            password, _ = _find_credential(username)
            if password is None:
                return f"No credential found for username: {username}"
        from src.shells.ftp_shell import FTPConnectionThread
        t = FTPConnectionThread(ip, port, username, password)
        return f"FTP {ip}:{port} as {username}: {_wait_connect(t)}"

    if protocol == "winrm":
        if not port:
            port = 5985
        _, hash_nt = _find_credential(username)
        if hash_nt is None:
            hash_nt = ""
        from src.shells.winrm_shell import WinRMConnectionThread
        t = WinRMConnectionThread(ip, port, username, "", hash_nt=hash_nt)
        return f"WinRM {ip}:{port} as {username}: {_wait_connect(t, timeout=15)}"

    return f"Unknown protocol: {protocol}. Use ssh, sftp, ftp, or winrm."
