"""
chat_agents.py — Registry of agentic Claude chat handlers for SeekrAI.

To add a new agent:
1. Write a _is_<name>() detection function below.
2. Add a system prompt constant (or point to a skill file name).
3. Append an entry to AGENT_REGISTRY (order = priority; first match wins).

The server's _call_claude_for_chat() calls resolve_agent(question) and uses
call_claude_with_tools() with the returned agent's system prompt.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill file loader
# ---------------------------------------------------------------------------

_SKILL_CACHE: dict = {}

def load_skill(skill_name: str) -> str:
    """Load ~/.claude/skills/<name>/SKILL.md, strip YAML frontmatter, cache."""
    if skill_name in _SKILL_CACHE:
        return _SKILL_CACHE[skill_name]
    path = os.path.expanduser(f"~/.claude/skills/{skill_name}/SKILL.md")
    try:
        content = open(path).read()
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                content = content[end + 4:].lstrip()
        _SKILL_CACHE[skill_name] = content
        logger.info(f"Loaded skill: {skill_name} ({len(content)} chars)")
        return content
    except FileNotFoundError:
        logger.warning(f"Skill not found: {path}")
        return ""


# ---------------------------------------------------------------------------
# Detection functions
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
    has_rhobs = any(k in q for k in ['rhobs', 'osdctl rhobs', 'rhobs logs', 'rhobs search'])
    has_log   = any(k in q for k in ['log', 'error', 'search', 'query', 'find'])
    return has_rhobs and has_log


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
#   skill       : str | None  — skill file name to load as system prompt
#   system      : str | None  — inline system prompt (used if skill missing/absent)
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
        "skill": "mcs-expertise",     # loads ~/.claude/skills/mcs-expertise/SKILL.md
        "preamble": MUST_GATHER_PREAMBLE,  # prepended before skill content
        "system": None,               # no inline fallback; falls back to plain chat if skill missing
        "max_tokens": 4000,
    },
    {
        "name": "rhobs",
        "detect": _is_rhobs,
        "skill": None,
        "preamble": "",
        "system": RHOBS_INVESTIGATOR_SYSTEM_PROMPT,
        "max_tokens": 4000,
    },
    {
        "name": "cluster-investigation",
        "detect": _is_cluster_investigation,
        "skill": None,
        "preamble": "",
        "system": SRE_INVESTIGATOR_SYSTEM_PROMPT,
        "max_tokens": 4000,
    },
]


def resolve_agent(question: str) -> dict | None:
    """Return the first matching agent for this question, or None for plain chat."""
    for agent in AGENT_REGISTRY:
        if agent["detect"](question):
            logger.info(f"Agent resolved: {agent['name']}")
            return agent
    return None


def build_agent_system(agent: dict, case_number: str = "", extra_ctx: str = "") -> str | None:
    """
    Return the system prompt for an agent:
    - Prepends agent['preamble'] if set (overrides default skill behaviour for chat context).
    - Then loads the skill file (if agent['skill'] is set).
    - Falls back to agent['system'] if no skill or skill file missing.
    - Returns None if nothing is available (caller falls back to plain chat).
    Prepends case number and optional extra context (SOP/KCS) when provided.
    """
    skill_content = ""
    if agent.get("skill"):
        skill_content = load_skill(agent["skill"])

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
