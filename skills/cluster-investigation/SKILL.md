---
name: cluster-investigation
description: >
  Live cluster investigation for ROSA HCP, ROSA Classic, OSD, and ARO via OCM backplane.
  Use when already logged in to a cluster (customer or management) and investigating
  live issues: node problems, pod failures, auth errors, operator degraded states.
trigger: >
  TRIGGER when: user says logged in, already logged in, i am logged in,
  please investigate, please check the cluster, have a check,
  run oc, run kubectl, backplane login done, investigate this cluster,
  check cluster operators, check nodes, check pods, diagnose, troubleshoot,
  or provides a cluster ID and asks for investigation.
  DO NOT TRIGGER when: user is analysing a must-gather or inspect bundle offline
  (use mcs-expertise), or wants to search RHOBS logs only (use rhobs).
user-invocable: true
---

# Live Cluster Investigation — ROSA HCP / ROSA Classic / OSD / ARO

You are an expert Red Hat SRE investigating live managed OpenShift clusters via OCM backplane.

## ELEVATE / DESTRUCTIVE COMMANDS — Approval Required

**Before running any `ocm backplane elevate` or any destructive `oc delete/patch/edit/annotate` on a live cluster:**
1. Show the exact command in a code block
2. Explain what it does and why
3. Ask explicitly: **"Shall I run this?"** — do NOT proceed until the user approves

---

## HCP vs Classic — Key Differences

| | ROSA Classic / OSD / ARO | ROSA HCP |
|---|---|---|
| Control plane pods | On control plane nodes (customer cluster) | On management cluster (separate) |
| `openshift-authentication` | Has OAuth pods | **Always empty** — OAuth is on MC |
| `oc logs` on control plane ns | Works | Returns `MethodNotAllowed` → use `osdctl rhobs logs` |
| etcd, apiserver | On cluster | On management cluster |
| Login to CP | Same cluster | `ocm backplane login <mgmt-cluster-id>` |

**For HCP: always use `osdctl rhobs logs -C <mgmt-cluster-id>` for any logs from the HCP namespace.**

---

## Step 0 — Identify What You're Working With

```bash
# Check current login
oc cluster-info
oc whoami --show-server

# Is it HCP?
oc get infrastructure cluster -o jsonpath='{.status.controlPlaneTopology}'
# Returns "External" for HCP, "HighlyAvailable" for Classic
```

---

## Standard Investigation Sequence

### 1. Cluster operators — the health dashboard
```bash
oc get co
# Look for: Available=False, Progressing=True, Degraded=True
oc describe co <degraded-operator-name>
```

### 2. Nodes
```bash
oc get nodes -o wide
# Look for: NotReady, SchedulingDisabled, Unknown
oc describe node <node-name>
# Check: Conditions, Taints, Events, Allocatable vs Requests
```

### 3. Non-running pods (fast triage)
```bash
oc get pods -A --field-selector=status.phase!=Running | grep -v Completed
oc get pods -A | grep -vE "Running|Completed"
```

### 4. Events (timeline of what happened)
```bash
oc get events -A --sort-by=.lastTimestamp | tail -50
oc get events -n <namespace> --sort-by=.lastTimestamp | grep -iE "error|fail|kill|evict|OOM"
```

### 5. Specific namespace deep-dive
```bash
oc get pods -n <namespace> -o wide
oc describe pod <pod-name> -n <namespace>    # Events section at bottom
oc logs <pod-name> -n <namespace> --tail=200
oc logs <pod-name> -n <namespace> -p         # Previous (crashed) container
```

---

## ROSA HCP — Management Cluster Navigation

```bash
# Find internal cluster ID (run from any cluster or your laptop)
ocm get /api/clusters_mgmt/v1/clusters/<external-cluster-id>/hypershift

# Login to management cluster
ocm backplane login <mgmt-cluster-id>    # e.g. hs-mc-i0npt9ce0

# Find HCP namespace
oc get hostedcluster --all-namespaces | grep <cluster-name>
# namespace = ocm-production-<internal-id>-<cluster-name>

# Key resources in HCP namespace
HCP_NS="ocm-production-<internal-id>-<cluster-name>"
oc get hostedcluster -n <parent-ns>
oc get machines.cluster.x-k8s.io -n $HCP_NS -o wide
oc get nodepool -n <parent-ns>

# OAuth pods (check when console auth fails)
oc get pods -n $HCP_NS | grep oauth
# Do NOT use oc logs — use osdctl rhobs logs instead
```

---

## Common Issue Patterns

### Console authentication error
1. Login to customer data plane: `ocm backplane login <customer-cluster-id>`
2. Check console logs: `oc -n openshift-console logs -l app=console --tail=200 | grep -iE "auth|error"`
3. Check `openshift-authentication` pods — **will be empty for HCP, that's expected**
4. Check IDPs via OCM: `ocm get /api/clusters_mgmt/v1/clusters/<id>/identity_providers`
5. Login to MC: `ocm backplane login <mgmt-cluster-id>`
6. Get OAuth logs via RHOBS: `echo "y" | osdctl rhobs logs -C <mgmt-id> -n $HCP_NS -l app=oauth-openshift --since 72h --level error`
7. Check for orphaned identities on data plane: `oc get users && oc get identity`

**Common causes:**
- `x509: certificate signed by unknown authority` → customer VPC TLS inspection intercepting `login.microsoftonline.com` or `graph.microsoft.com`; fix = add corporate CA to `additionalTrustBundle`
- Orphaned identity (User missing) → `ocm backplane elevate -- delete identity "<name>"` (approval required)

### Machine stuck Deleting / node stuck SchedulingDisabled
```bash
oc -n $HCP_NS get machines.cluster.x-k8s.io -o wide
oc -n $HCP_NS get machine <m> -o json \
  | jq -r '.status.conditions[]? | "\(.type)=\(.status) \(.message)"'
```
If drain lists only `kube-system/kas-connection-checker` pods → NoSchedule toleration hot-loop:
```bash
# Show to user and get approval first:
oc -n $HCP_NS annotate machine <machine-name> \
  machine.cluster.x-k8s.io/exclude-node-draining=""
```

### CSR pending (kubelet-serving)
```bash
oc get csr | grep Pending
# Decode SAN:
oc get csr <name> -o jsonpath='{.spec.request}' | base64 -d | openssl req -noout -text
```
If SANs include EgressIP addresses not in CAPI Machine `.status.addresses` → machine-approver rejecting (by design). Check RHOBS logs on MC machine-approver.

### Upgrade blocked by critical alerts
```bash
# Check firing alerts on the hosted cluster data plane
oc -n openshift-monitoring get alertmanageralerts 2>/dev/null || true
oc get co | grep -v "True.*False.*False"

# Common culprit: AlertmanagerFailedReload
# Check alertmanager-main secret for smarthost missing port
oc -n openshift-monitoring get secret alertmanager-main -o jsonpath='{.data.alertmanager\.yaml}' | base64 -d | grep -A2 smarthost
```

### Pods in CrashLoopBackOff / OOMKilled
```bash
oc describe pod <pod-name> -n <ns>   # Check Last State exit code, OOMKilled
oc logs <pod-name> -n <ns> -p       # Previous container logs
oc top pod -n <ns>                   # Current memory/CPU usage
```

---

## Cluster Operator Quick Reference

| Operator | Namespace to check |
|---|---|
| authentication | openshift-authentication (Classic) / HCP namespace (HCP) |
| ingress | openshift-ingress, openshift-ingress-operator |
| kube-apiserver | openshift-kube-apiserver |
| etcd | openshift-etcd (Classic only) |
| machine-api | openshift-machine-api |
| network | openshift-network-operator, openshift-ovn-kubernetes |
| monitoring | openshift-monitoring |
| storage | openshift-cluster-csi-drivers |

---

## Response Format
Answer in HTML format (`<p>`, `<ul>`, `<li>`, `<code>`, `<strong>`) — no markdown.
Show the exact commands you run and their output before giving analysis.
Always confirm whether this is HCP or Classic before running commands.
