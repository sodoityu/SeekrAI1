"""
chat_agents.py — Registry of agentic Claude chat handlers for SeekrAI.

To add a new agent:
1. Write a _is_<name>() detection function below.
2. Add a system prompt constant (or point to a skill file name).
3. Append an entry to AGENT_REGISTRY (order = priority; first match wins).

Skills can also be auto-discovered from a configured skills folder:
  - Drop a <name>/SKILL.md into the configured skills directory.
  - The YAML frontmatter must include 'trigger' keywords for auto-matching.
  - Call resolve_agent(question, skills_dir=<path>) to include discovered skills.

The server's _call_claude_for_chat() calls resolve_agent(question) and uses
call_claude_with_tools() with the returned agent's system prompt.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# Default skills directory: SeekrAI1/skills/ next to this file.
_DEFAULT_SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")

# ---------------------------------------------------------------------------
# Skill file loader
# ---------------------------------------------------------------------------

_SKILL_CACHE: dict = {}


def _skill_paths(skill_name: str, skills_dir: str | None = None) -> list[str]:
    """Return candidate paths to check for a skill, preferred first."""
    candidates = []
    if skills_dir:
        candidates.append(os.path.join(skills_dir, skill_name, "SKILL.md"))
    candidates.append(os.path.join(_DEFAULT_SKILLS_DIR, skill_name, "SKILL.md"))
    candidates.append(os.path.expanduser(f"~/.claude/skills/{skill_name}/SKILL.md"))
    return candidates


def load_skill(skill_name: str, skills_dir: str | None = None) -> str:
    """Load a skill's SKILL.md, strip YAML frontmatter, cache per (name, dir)."""
    cache_key = (skill_name, skills_dir)
    if cache_key in _SKILL_CACHE:
        return _SKILL_CACHE[cache_key]
    for path in _skill_paths(skill_name, skills_dir):
        try:
            content = open(path).read()
            if content.startswith("---"):
                end = content.find("\n---", 3)
                if end != -1:
                    content = content[end + 4:].lstrip()
            _SKILL_CACHE[cache_key] = content
            logger.info(f"Loaded skill '{skill_name}' from {path} ({len(content)} chars)")
            return content
        except FileNotFoundError:
            continue
    logger.warning(f"Skill not found: {skill_name}")
    return ""


def _parse_skill_frontmatter(text: str) -> dict:
    """
    Parse minimal YAML-like frontmatter between --- delimiters.
    Returns dict with 'name', 'description', 'trigger' keys (all str).
    Only handles simple key: value and multiline block scalars (>).
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end].strip()
    result: dict = {}
    key = None
    block_lines: list[str] = []

    def flush_block():
        if key and block_lines:
            result[key] = " ".join(block_lines).strip()

    for line in fm_text.splitlines():
        if line and not line[0].isspace():
            flush_block()
            block_lines = []
            if ":" in line:
                k, _, v = line.partition(":")
                key = k.strip()
                v = v.strip()
                if v and v != ">":
                    result[key] = v
                # if v == ">" or v == "": block mode, collected via block_lines
        elif line.startswith("  ") and key:
            block_lines.append(line.strip())

    flush_block()
    return result


def scan_skills_folder(skills_dir: str) -> list[dict]:
    """
    Scan skills_dir for <name>/SKILL.md files.
    Returns list of dicts: {name, description, trigger_text, trigger_keywords, path}.
    """
    skills = []
    if not skills_dir or not os.path.isdir(skills_dir):
        return skills
    for entry in sorted(os.scandir(skills_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        md_path = os.path.join(entry.path, "SKILL.md")
        if not os.path.exists(md_path):
            continue
        try:
            raw = open(md_path).read()
        except OSError:
            continue
        fm = _parse_skill_frontmatter(raw)
        name = fm.get("name") or entry.name
        trigger_text = fm.get("trigger", "")
        # Extract keyword section before "DO NOT TRIGGER"
        trigger_positive = re.split(r"DO NOT TRIGGER", trigger_text, flags=re.IGNORECASE)[0]
        # Pull meaningful words (4+ chars, skip common stop words)
        _STOP = {"when", "user", "asks", "asks", "also", "that", "with", "this",
                 "from", "have", "will", "uses", "used", "make", "into", "about",
                 "asks", "their", "using", "invokes", "mention", "mentions"}
        keywords = [
            w.lower().strip(",.;:'\"()") for w in trigger_positive.split()
            if len(w) >= 4 and w.lower().strip(",.;:'\"()") not in _STOP
        ]
        skills.append({
            "name": name,
            "description": fm.get("description", ""),
            "trigger_text": trigger_text,
            "trigger_keywords": list(dict.fromkeys(keywords)),  # deduplicate, preserve order
            "path": md_path,
            "skills_dir": skills_dir,
        })
    return skills


def _make_dynamic_detect(skill_name: str, keywords: list[str]):
    """Return a detection function that matches if any keyword appears in the question."""
    kws = [k.lower() for k in keywords if k]
    slug = skill_name.lower().replace("-", " ")

    def _detect(question: str) -> bool:
        q = question.lower()
        # Always match if the skill name is mentioned directly
        if skill_name.lower() in q or slug in q:
            return True
        return any(kw in q for kw in kws)

    return _detect


# ---------------------------------------------------------------------------
# Detection functions (built-in agents)
# ---------------------------------------------------------------------------

def _is_must_gather(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in [
        'must-gather', 'must gather', 'mustgather',
        'omc ', 'omc\t', ' omc', 'inspect bundle',
        'mcs-expertise', 'mcs expertise',
    ])


def _is_rhobs(question: str) -> bool:
    q = question.lower()
    # Explicit RHOBS keyword
    if any(k in q for k in ['rhobs', 'osdctl rhobs']):
        return any(k in q for k in ['log', 'error', 'search', 'query', 'find'])
    # HCP-specific log queries (oc logs doesn't work on HCP — implies RHOBS)
    has_hcp  = any(k in q for k in ['hcp', 'hosted control plane', 'management cluster', 'hypershift'])
    has_log  = any(k in q for k in ['log', 'logs'])
    has_comp = any(k in q for k in ['oauth', 'upgrade', 'machine-approver', 'machineapprover',
                                     'mhc', 'machinehealthcheck', 'drain', 'csr', 'node'])
    return has_hcp and has_log and has_comp


def _is_cluster_investigation(question: str) -> bool:
    q = question.lower()
    strong_signals = [
        'have a check', 'please investigate', 'please diagnose',
        'run oc', 'run kubectl', 'i had login', 'logged in to',
        'logged into', "i'm logged in", 'i am logged in',
    ]
    if any(s in q for s in strong_signals):
        return True
    has_cluster = any(s in q for s in ['cluster', 'node', 'namespace', 'pod'])
    has_intent  = any(s in q for s in ['check', 'investigate', 'diagnose', 'troubleshoot', 'look into'])
    return has_cluster and has_intent


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SRE_INVESTIGATOR_SYSTEM_PROMPT = """You are an expert Red Hat SRE with deep knowledge of OpenShift, ROSA (Classic and HCP), Kubernetes, and AWS infrastructure.

You have access to a `run_command` tool that executes oc/kubectl/rosa CLI commands on the locally logged-in cluster. When the user reports a cluster issue, PROACTIVELY INVESTIGATE by running relevant commands — do not just give general advice. Chain multiple commands as needed to narrow down the root cause.

Investigation patterns by issue type:

NODES / SCHEDULING:
  oc get nodes -o wide
  oc describe node <node-name>
  oc get pods --all-namespaces --field-selector=status.phase!=Running
  oc adm top nodes

PODS / WORKLOADS:
  oc get pods -n <namespace> -o wide
  oc describe pod <pod-name> -n <namespace>
  oc logs <pod-name> -n <namespace> --tail=100
  oc get events -n <namespace> --sort-by=.lastTimestamp

NETWORKING:
  oc get svc -n <namespace>
  oc get route -n <namespace>
  oc get networkpolicies -n <namespace>
  oc get ingresscontroller -n openshift-ingress-operator -o yaml

STORAGE:
  oc get pvc -n <namespace>
  oc get pv
  oc describe pvc <pvc-name> -n <namespace>

CLUSTER HEALTH:
  oc get clusteroperators
  oc get clusterversion
  oc get mcp
  oc get nodes

ROSA:
  rosa list clusters
  rosa describe cluster -c <cluster-name>
  rosa list machinepools -c <cluster-name>

After investigating, provide a clear root cause analysis and recommended remediation steps.
Use HTML formatting (<p>, <ul>, <li>, <code>, <strong>) for your response — no markdown."""


RHOBS_INVESTIGATOR_SYSTEM_PROMPT = """You are an expert Red Hat SRE. The user wants you to search RHOBS (Red Hat Observability Service) logs using the `osdctl rhobs` CLI.

WORKFLOW:
1. First, run `osdctl rhobs logs --help` to see all available flags (cluster-id, namespace, start, end, query, etc.).
2. If needed, run `osdctl rhobs --help` to discover subcommands.
3. Extract from the user's question:
   - Cluster ID (UUID or cluster name) — ask if missing and not in case context.
   - Time range: convert natural language ("between 10am and 11am JST", "last 30 minutes") to RFC3339 UTC timestamps.
   - Error keywords / log query string.
4. Build and run the osdctl rhobs logs command with the correct flags.
5. Parse the output and summarize: key error messages, timestamps, affected components.

TIME CONVERSION RULES:
- JST = UTC+9 (subtract 9 hours to convert to UTC).
- "last N minutes" → compute UTC start time accordingly.
- Always use RFC3339 format: YYYY-MM-DDTHH:MM:SSZ

TYPICAL COMMAND PATTERNS (verify flags with --help first):
  osdctl rhobs logs --cluster-id <uuid> --start 2026-01-15T01:00:00Z --end 2026-01-15T02:00:00Z
  osdctl rhobs logs --cluster-id <uuid> --query '{namespace="openshift-ingress"}' --start ...

If the cluster ID is not in the question, check if the case context mentions one, or ask the user to provide it.
Provide a concise root-cause summary after reviewing the logs.
Use HTML formatting (<p>, <ul>, <li>, <code>, <strong>) for your final answer — no markdown."""


# ---------------------------------------------------------------------------
# Agent registry — ordered by priority (first match wins).
#
# Each entry:
#   name        : str  — label used in logs
#   detect      : callable(question: str) -> bool
#   skill       : str | None  — skill file name (loaded via load_skill())
#   preamble    : str  — prepended before skill content
#   system      : str | None  — inline system prompt (used if skill missing)
#   max_tokens  : int
# ---------------------------------------------------------------------------

MUST_GATHER_PREAMBLE = """You are investigating a must-gather/inspect bundle directly in a chat session.

STRICT RULES FOR THIS SESSION:
- If the user provides a must-gather path, run `omc use <path>` IMMEDIATELY as your FIRST command — no questions first.
- Do NOT ask for case names, folder names, or offer to create any directory structure.
- Do NOT ask the user to share file contents — use omc commands to read everything yourself.
- Do NOT say you cannot access local files — you CAN run omc commands via the run_command tool.
- Investigate step by step: omc use <path> → omc get nodes → omc get co → drill into any problems found.
- If a case number is mentioned, note it in your response header but do not let it delay the investigation.

START IMMEDIATELY with omc commands when the user provides a path. Report findings in HTML format (<p>, <ul>, <li>, <code>, <strong>).

---
"""

AGENT_REGISTRY = [
    {
        "name": "must-gather",
        "detect": _is_must_gather,
        "skill": "mcs-expertise",
        "preamble": MUST_GATHER_PREAMBLE,
        "system": None,
        "max_tokens": 4000,
    },
    {
        "name": "rhobs",
        "detect": _is_rhobs,
        "skill": "rhobs",                          # loads skills/rhobs/SKILL.md
        "preamble": "",
        "system": RHOBS_INVESTIGATOR_SYSTEM_PROMPT, # fallback if skill file missing
        "max_tokens": 4000,
    },
    {
        "name": "cluster-investigation",
        "detect": _is_cluster_investigation,
        "skill": "cluster-investigation",           # loads skills/cluster-investigation/SKILL.md
        "preamble": "",
        "system": SRE_INVESTIGATOR_SYSTEM_PROMPT,   # fallback if skill file missing
        "max_tokens": 4000,
    },
]

# Names already covered by built-in AGENT_REGISTRY (avoid double-registering from skills folder)
_BUILTIN_SKILL_NAMES = {"mcs-expertise", "must-gather", "rhobs", "cluster-investigation", "rosa-backplane"}


def _build_dynamic_registry(skills_dir: str | None) -> list[dict]:
    """
    Scan skills_dir and return extra agent entries for skills not already in AGENT_REGISTRY.
    These are appended after the built-in registry when resolving agents.
    """
    if not skills_dir:
        return []
    extra = []
    for skill in scan_skills_folder(skills_dir):
        if skill["name"] in _BUILTIN_SKILL_NAMES:
            continue
        detect_fn = _make_dynamic_detect(skill["name"], skill["trigger_keywords"])
        extra.append({
            "name": skill["name"],
            "detect": detect_fn,
            "skill": skill["name"],
            "preamble": "",
            "system": None,
            "max_tokens": 4000,
            "_skills_dir": skills_dir,
        })
        logger.info(f"Dynamic skill registered: {skill['name']} ({len(skill['trigger_keywords'])} keywords)")
    return extra


def resolve_agent(question: str, skills_dir: str | None = None) -> dict | None:
    """
    Return the first matching agent for this question, or None for plain chat.
    skills_dir: if provided, also checks dynamically discovered skills from that folder.
    """
    for agent in AGENT_REGISTRY:
        if agent["detect"](question):
            logger.info(f"Built-in agent resolved: {agent['name']}")
            return agent
    for agent in _build_dynamic_registry(skills_dir):
        if agent["detect"](question):
            logger.info(f"Dynamic agent resolved: {agent['name']}")
            return agent
    return None


def list_skills(skills_dir: str | None = None) -> list[dict]:
    """
    Return a list of all available skills (built-in + discovered).
    Each entry: {name, description, source}.
    Used by the settings UI to show what skills are loaded.
    """
    result = []
    seen = set()
    # Built-in skills (from AGENT_REGISTRY)
    for agent in AGENT_REGISTRY:
        if agent.get("skill"):
            name = agent["skill"]
            if name not in seen:
                seen.add(name)
                result.append({"name": name, "description": (agent.get("system") or "")[:80] or "(built-in)", "source": "built-in"})
        elif not agent.get("skill"):
            name = agent["name"]
            if name not in seen:
                seen.add(name)
                result.append({"name": name, "description": "(built-in inline prompt)", "source": "built-in"})
    # Discovered skills from skills_dir
    if skills_dir:
        for skill in scan_skills_folder(skills_dir):
            if skill["name"] not in seen:
                seen.add(skill["name"])
                result.append({"name": skill["name"], "description": skill["description"][:120], "source": skills_dir})
    return result


def build_agent_system(agent: dict, case_number: str = "", extra_ctx: str = "",
                       skills_dir: str | None = None) -> str | None:
    """
    Return the system prompt for an agent:
    - Prepends agent['preamble'] if set.
    - Loads the skill file (checks skills_dir first, then defaults).
    - Falls back to agent['system'] if no skill or skill file missing.
    - Returns None if nothing is available (caller falls back to plain chat).
    """
    skill_content = ""
    if agent.get("skill"):
        effective_dir = agent.get("_skills_dir") or skills_dir
        skill_content = load_skill(agent["skill"], effective_dir)

    body = agent.get("preamble", "") + skill_content
    if not body:
        body = agent.get("system", "")
    if not body:
        return None

    parts = []
    if case_number:
        parts.append(f"You are investigating SFDC case {case_number}.")
    parts.append(body)
    if extra_ctx:
        parts.append(extra_ctx)
    return "\n\n".join(parts)
