# RCA #4 — Fix Plan

**Date:** 2026-02-17
**Source:** `.spec/report/pomodoro-timer-rca-4-log-review.md`
**Predecessor fixes:** RCA #1 (6 fixes), RCA #2 (5 fixes), RCA #3 (6 fixes)

---

## Review Summary

7 issues identified in RCA #4. Disposition:

| # | Issue | Verdict |
|---|-------|---------|
| 1 | Coding agent guesses wrong file paths | **Not valid** — project structure varies across projects |
| 2 | Redundant `ls` after every feature | **Fix** |
| 3 | Sub-agents redundantly read prompt files | **Not fixable** — structural, by design |
| 4 | GitHub agent checks `$GITHUB_REPO` repeatedly | **Not valid** — runtime env check is intentional for security |
| 5 | Audio verification is code-inspection only | **Acceptable gap** for now |
| 6 | Excessive Playwright snapshots | **Acceptable overhead** (~3% waste) |
| 7 | No regression testing between features | **Fix** |

**Fixes to implement: 2**

---

## Fix 1: Drop Redundant `ls` Ritual

**Issue:** The coding agent runs `ls` on both project root and screenshots directory after completing every feature (~10 wasted tool calls across 5 features). This information is already known from the Edit/Write calls it just made.

**Severity:** Low (waste, not errors)

**Root Cause:** The coding agent's "Output Checklist" section (lines 267-277 of `coding_agent_prompt.md`) asks it to verify it has `files_changed` and `screenshot_evidence` before reporting back. The agent interprets this as needing to `ls` the directories to confirm files exist, even though it just created/edited them.

**Fix:**

| File | Change |
|------|--------|
| `prompts/coding_agent_prompt.md` | Add explicit instruction to NOT run `ls` for file verification |

Add to the **Output Checklist** section (after line 276):

```markdown
**Do NOT run `ls` to verify files you just created or edited.** You already know the file paths from your Write/Edit tool calls. Listing directories at the end of a task is unnecessary overhead.
```

---

## Fix 2: Parallel Regression Testing Gate (Option A)

**Issue:** The orchestrator's verification gate (lines 50-58, 112-119 of `orchestrator_prompt.md`) requires testing existing features before new work, but in practice the coding agent only checks if the app loads — it doesn't re-test previous features' key interactions. No regressions are caught.

**Severity:** Medium (risk — nothing broke in this session, but regressions would go undetected)

**Root Cause:** The orchestrator prompt says "Test 1-2 completed features" (line 115) but doesn't specify *what* to test or *how*. The delegation to the coding agent is vague, so the agent defaults to a shallow "navigate and screenshot" check.

**Fix — Option A (gate pattern with parallel regression agents):**

The orchestrator should track the key interaction for each completed feature and delegate regression tests to **two coding agents in parallel**, wait for both to PASS, then proceed to the next feature.

| File | Change |
|------|--------|
| `prompts/orchestrator_prompt.md` | Rewrite verification gate section with parallel regression testing |

### Changes to `orchestrator_prompt.md`:

**Replace the Verification Gate section (lines 50-58) with:**

```markdown
### Verification Gate (MANDATORY)

Before ANY new feature work (when 2+ features are completed):

1. Split completed features into two groups
2. Delegate each group to a **separate coding agent** in parallel using the Task tool:
   - Regression Agent A: Test features [group 1] — provide specific interactions per feature
   - Regression Agent B: Test features [group 2] — provide specific interactions per feature
3. Wait for BOTH agents to respond
4. If ANY test FAILs: Fix regressions first (do NOT proceed to new work)
5. If ALL PASS: Proceed to implementation

When only 1 feature is completed, use a single coding agent for regression testing.

**You MUST pass specific test instructions per feature, not just "test existing features".** Example:

```
Regression test these features:
- Feature "Timer Display" (NEX-155): Navigate to app, verify 25:00 is shown, take screenshot
- Feature "Timer Controls" (NEX-156): Click Start, wait 2s, verify timer is counting down, click Pause, verify timer stopped, take screenshot
```

**Port isolation:** Regression Agent A uses port 3001, Regression Agent B uses port 3002. The implementation coding agent uses port 3000.

**Port cleanup:** Each regression agent MUST kill its assigned port before finishing — whether tests PASS or FAIL: `python kill_port.py 3001` / `python kill_port.py 3002`. Leftover dev servers cause port conflicts for subsequent regression gates.

**Regression failure flow:** When a regression test fails:
1. Ask linear agent to move the failing feature's issue back to **In Progress** (no longer Done)
2. Ask coding agent to fix the regression
3. Re-run verification gate to confirm the fix
4. Commit the fix via github agent
5. Mark the issue Done again via linear agent
6. Only then proceed to new feature work

**This gate prevents broken code from accumulating.**
```

**Replace Step 3: Verification Test (lines 112-119) with:**

```markdown
**Step 3: Verification Test (MANDATORY)**

If completed features exist, run the verification gate:
- Build a test plan: for each completed feature, write 1-2 specific interactions to verify (click X, check Y)
- If 2+ features completed: split into 2 groups and delegate to 2 coding agents in parallel (ports 3001/3002)
- If 1 feature completed: delegate to 1 coding agent (port 3001)
- Wait for all results
- If any FAIL: stop and fix regression before proceeding

⚠️ **If FAIL: Stop here. Ask coding agent to fix the regression.**
```

### Changes to `prompts/coding_agent_prompt.md`:

**Update the Dev Server port section (lines 177-193) to support regression testing ports:**

Add after line 189:

```markdown
**Regression testing mode:** When the orchestrator assigns you a specific port (e.g., 3001 or 3002) for regression testing, use that port instead of 3000. This allows parallel regression testing without port conflicts.

**Port cleanup after regression testing:** Whether tests PASS or FAIL, always kill your assigned port before reporting results: `python kill_port.py <port>`. Do NOT leave dev servers running on regression ports.
```

### Changes to `agents/definitions.py` (if needed):

Verify the orchestrator can spawn multiple coding agents in parallel via the Task tool. No agent definition changes should be needed — the Task tool already supports parallel sub-agent launches.

---

## Validation

After implementing these fixes, the next agent run should show:
1. **Fix 1:** Zero `ls` commands at the end of feature implementation (was 10 per 5 features)
2. **Fix 2:** Regression test delegations visible in logs before each new feature (single agent from feature 2, parallel agents from feature 3+), with specific test instructions per feature and distinct ports
