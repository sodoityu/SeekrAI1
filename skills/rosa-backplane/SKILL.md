---
name: rosa-backplane
description: >
  ROSA / OSD / ARO live cluster investigation via OCM backplane.
  Handles login (customer cluster + management cluster), elevated oc debug,
  and RHOBS log retrieval via osdctl. Use when investigating live managed
  OpenShift clusters through backplane access.
trigger: >
  TRIGGER when: user invokes /rosa-backplane, or asks to check/investigate
  a live ROSA, OSD, or ARO cluster node, pod, or log — especially when
  backplane login, oc debug node, elevated access, or osdctl rhobs is needed.
  DO NOT TRIGGER when: user is working with must-gather/inspect bundles offline
  (use /mcs-expertise instead).
user-invocable: true
---

# ROSA Backplane — Live Cluster Investigation

You are an SRE support engineer investigating live ROSA / OSD / ARO clusters
via OCM backplane. Follow this workflow precisely for every investigation.

---

## Step 0 — Check Current Login

Before doing anything, check if already logged in to the target cluster:

```bash
ocm backplane status
```

If the output shows the correct cluster ID/name → skip to Step 2.
If not logged in or wrong cluster → proceed to Step 1.

---

## Step 1 — Login to Cluster

**Ask the user for the cluster ID** if not already provided:

> "Please provide the OCM cluster ID (e.g. 2abc123xyz...) to log in."

Then login:

```bash
ocm backplane login <cluster-id>
```

Verify success:

```bash
ocm backplane status
oc get nodes
```

### Login to Management Cluster (HCP / HyperShift)

For ROSA HCP or ARO HCP, the hosted control plane runs on a **management cluster**.
To access it:

```bash
ocm backplane login <cluster-id> --manager
```

Use the management cluster context when investigating:
- Hosted control plane pods (kas, etcd, oauth, etc.)
- OVN control plane (ovnkube-control-plane)
- Any namespace matching the pattern `ocm-production-*` or `ocm-staging-*`
- HyperShift operator components

---

## Step 2 — Running oc Commands

Use standard `oc` commands for all read operations:

```bash
oc get nodes -o wide
oc get pods -A | grep -v Running
oc describe node <node-name>
oc get events -A --sort-by='.lastTimestamp' | tail -30
```

### If You Get a Permission Error

If any `oc` command returns:

```
Error from server (Forbidden): ...
```

**STOP and ask the user before elevating:**

> "I need elevated (backplane-cluster-admin) access to run this command.
> The reason I will provide is: '<brief reason>'.
> Is it OK to proceed with elevation? (yes/no)"

Only after user confirms, run:

```bash
ocm backplane elevate '<reason>' -- <oc-subcommand-without-oc> [args]
```

**Important syntax note:**
- Do NOT include `oc` in the command after `--`
- Example for `oc debug node/ip-10-x-x-x.ec2.internal`:
  ```bash
  ocm backplane elevate 'Investigating node hang - case XXXXX' -- \
    debug node/ip-10-x-x-x.ec2.internal --quiet -- chroot /host <command>
  ```
- Example for `oc get pods -A`:
  ```bash
  ocm backplane elevate 'reason' -- get pods -A
  ```

### Node Debug Pattern (Elevated)

For any node-level investigation (journals, mounts, processes):

```bash
ocm backplane elevate '<reason>' -- \
  debug node/<node-name> --quiet -- chroot /host bash -c '
  <commands here>
'
```

---

## Step 3 — Checking Logs on Management Cluster (RHOBS)

For **ROSA HCP / ARO HCP**, pod logs from the management cluster side
(control plane components) are stored in **RHOBS** (Red Hat Observability).
You cannot use `oc logs` directly — use `osdctl rhobs logs` instead.

### Syntax

```bash
osdctl rhobs logs \
  -C <management-cluster-name> \
  -n <hcp-namespace> \
  <pod-name> \
  --since <duration>
```

### Parameters

| Flag | Description | Example |
|------|-------------|---------|
| `-C` | Management cluster name | `hs-mc-xxxxx` |
| `-n` | HCP namespace on mgmt cluster | `ocm-production-xxxxxxxx` |
| `<pod>` | Pod name | `ovnkube-control-plane-76c9c8c5dd-fqtxs` |
| `--since` | How far back | `2h`, `30m`, `1d` |
| `-c` | Container name (optional) | `ovnkube-master` |

### Finding the Management Cluster Name and HCP Namespace

```bash
# After logging in with --manager:
oc get hostedcluster -A
oc get hostedcontrolplane -A

# The namespace is typically:
# ocm-production-<cluster-id-hash>   (prod)
# ocm-staging-<cluster-id-hash>      (staging)
```

### Common RHOBS Log Commands

```bash
# OVN control plane logs
osdctl rhobs logs -C hs-mc-xxxxx -n $HCP_NAMESPACE \
  ovnkube-control-plane-<hash> --since 2h

# Kube API server logs
osdctl rhobs logs -C hs-mc-xxxxx -n $HCP_NAMESPACE \
  kube-apiserver-<hash> -c kube-apiserver --since 1h

# etcd logs
osdctl rhobs logs -C hs-mc-xxxxx -n $HCP_NAMESPACE \
  etcd-0 --since 1h

# Cluster version operator logs
osdctl rhobs logs -C hs-mc-xxxxx -n $HCP_NAMESPACE \
  cluster-version-operator-<hash> --since 30m
```

---

## Step 4 — Node Investigation Checklist

When a node hang or unresponsive node is reported, collect this data
**before any reboot** (data is lost after reboot):

```bash
ocm backplane elevate '<reason>' -- \
  debug node/<node-name> --quiet -- chroot /host bash -c '

echo "=== 1. Boot list ==="
journalctl --list-boots

echo ""
echo "=== 2. NFS/EFS timeout count (current boot) ==="
journalctl -k -b 0 | grep -c "not responding, timed out"

echo ""
echo "=== 3. First and last NFS timeout ==="
journalctl -k -b 0 | grep "not responding, timed out" | head -1
journalctl -k -b 0 | grep "not responding, timed out" | tail -1

echo ""
echo "=== 4. Active NFS/EFS mounts ==="
mount | grep "127.0.0.1"

echo ""
echo "=== 5. Stunnel / EFS mount helper processes ==="
ps aux | grep -E "stunnel|amazon-efs" | grep -v grep

echo ""
echo "=== 6. D-state processes (stuck on I/O) ==="
ps aux | awk '"'"'$8 == "D" {print}'"'"'

echo ""
echo "=== 7. OOM kills (current boot) ==="
journalctl -k -b 0 | grep -E "oom.kill|Out of memory|Killed process" | tail -20

echo ""
echo "=== 8. Last 50 kubelet errors ==="
journalctl -u kubelet -b 0 --no-pager | grep -i "error\|fail\|timeout" | tail -50

echo ""
echo "=== 9. EFS watchdog log ==="
cat /var/log/amazon/efs/amazon-efs-utils.log 2>/dev/null | tail -100

echo ""
echo "=== 10. Recent kernel messages ==="
journalctl -k -b 0 --no-pager | tail -100
'
```

---

## Key Rules

- **Always check `ocm backplane status` first** — do not re-login if already on the right cluster
- **Always ask user before elevating** — state the reason you will provide, then wait for confirmation
- **Never use `oc` prefix after `--` in `ocm backplane elevate`** — use the subcommand directly
- **For HCP node logs use osdctl rhobs** — `oc logs` will not work for mgmt cluster side pods
- **Journal logs are lost after reboot** — collect before any node restart
- **`--manager` flag switches context to the management cluster** — remember to switch back for customer cluster work
