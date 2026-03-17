---
name: self-review
description:
  Trigger structured Codex review on the current PR, remediate findings, rerun
  review, and stop only when no actionable review feedback remains and checks
  are green.
---

# Self-Review

## Goals

- Request structured Codex review automatically on the current PR head.
- Keep the ticket in `In Progress` while review findings or failing checks exist.
- Resolve findings, push updates, and rerun review until no actionable feedback
  remains.
- Return control only when the PR is ready to move to `Human Review`.

## Steps

1. Confirm the current branch has an open PR and the branch is pushed.
2. Post a top-level PR issue comment containing `@codex review`.
3. Record the request time, PR number, and current head SHA in the Linear
   workpad.
4. Run `python3 .codex/skills/land/land_watch.py` from the PR branch.
5. Interpret the watcher result:
   - Exit `0`: checks are green and no actionable review feedback remains.
   - Exit `2`: review feedback exists. Acknowledge it, fix the issue, commit,
     push, post a `[codex] Changes since last review:` update, request
     `@codex review` again, and rerun the watcher.
   - Exit `3`: checks failed. Fix the failure, commit, push, request
     `@codex review` again if code changed, and rerun the watcher.
   - Exit `4`: the PR head changed unexpectedly. Refresh local branch state and
     rerun the watcher.
   - Exit `5`: merge conflicts exist. Resolve with the `pull` skill, push, and
     restart the loop.
6. Treat all Codex review comments, human issue comments, inline review
   comments, and blocking review states as actionable until acknowledged and
   resolved or explicitly pushed back on.
7. Update the Linear workpad after every review cycle with:
   - review request timestamp,
   - findings summary,
   - remediation commit(s),
   - rerun status,
   - clean-review result when the loop exits successfully.

## Commands

```sh
pr_number=$(gh pr view --json number -q .number)
head_sha=$(gh pr view --json headRefOid -q .headRefOid)

gh api repos/{owner}/{repo}/issues/"$pr_number"/comments \
  -f body='@codex review'

python3 .codex/skills/land/land_watch.py
```
