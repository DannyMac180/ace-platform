---
sidebar_position: 1
---

# Creating Playbooks

Learn how to create effective playbooks that improve over time, whether you are
working solo or inside a shared team workspace.

## Creating a New Playbook

### From the Dashboard

1. Log in to [app.aceagent.io](https://app.aceagent.io)
2. Click **New Playbook** in the sidebar
3. Fill in the details:
   - **Name** - Clear, descriptive name
   - **Description** - Brief summary of the playbook's purpose
   - **Content** (optional) - The playbook instructions in Markdown
4. Click **Create Playbook**

In a personal workspace, the new playbook is immediately available in your own
library. In a team workspace, the playbook still starts as your draft, and you
can later move it through the team review lifecycle when it is ready to share.

### Via MCP

```
Use the ace create_playbook tool with:
- name: "Code Review Assistant"
- initial_content: "# Code Review Assistant..."
```

## Playbook Structure

Playbooks use the **ACE bullet format**—structured instructions that can be tracked and evolved over time.

### Basic Structure

<div style={{background: 'var(--ifm-color-emphasis-100)', padding: '1.5rem', borderRadius: '8px', marginBottom: '1rem'}}>

#### Playbook Title

A brief description of what this playbook is for.

**STRATEGIES & INSIGHTS**

`[strategy-name] helpful=0 harmful=0 ::` Actionable instruction content here.

`[another-strategy] helpful=0 harmful=0 ::` Another instruction.

**COMMON MISTAKES TO AVOID**

`[mistake-name] helpful=0 harmful=0 ::` Description of what to avoid.

**OTHERS**

`[misc-instruction] helpful=0 harmful=0 ::` Any other instructions.

</div>

### ACE Bullet Format

Each instruction follows this format:

```
[semantic-slug] helpful=N harmful=N :: Instruction content
```

- **`[semantic-slug]`** - A unique identifier for the instruction (lowercase, hyphens)
- **`helpful=N`** - Score tracking how often this instruction helped (starts at 0)
- **`harmful=N`** - Score tracking how often this instruction caused issues (starts at 0)
- **`::`** - Separator between metadata and content
- **Instruction content** - The actual guidance

### Common Sections

| Section | Purpose |
|---------|---------|
| `STRATEGIES & INSIGHTS` | High-level approaches and wisdom |
| `FORMULAS & CALCULATIONS` | Mathematical formulas and calculation methods |
| `CODE SNIPPETS & TEMPLATES` | Reusable patterns and examples |
| `COMMON MISTAKES TO AVOID` | Anti-patterns and pitfalls |
| `PROBLEM-SOLVING HEURISTICS` | Debugging and troubleshooting tips |
| `CONTEXT CLUES & INDICATORS` | When to apply certain approaches |
| `OTHERS` | Miscellaneous instructions |

### Example Playbook

<div style={{background: 'var(--ifm-color-emphasis-100)', padding: '1.5rem', borderRadius: '8px', marginBottom: '1rem'}}>

#### Code Review Assistant

Reviews pull requests for code quality and security issues.

**STRATEGIES & INSIGHTS**

`[read-before-changing] helpful=5 harmful=0 ::` Read and understand existing code before suggesting changes. Look for patterns and conventions to preserve.

`[simple-first] helpful=4 harmful=0 ::` Start with the simplest solution that works. Avoid premature optimization.

**COMMON MISTAKES TO AVOID**

`[silent-catch] helpful=5 harmful=0 ::` Don't catch and silently ignore exceptions. Either handle them meaningfully or let them propagate.

`[hardcoded-values] helpful=4 harmful=0 ::` Avoid hardcoding values that might change (URLs, API keys, timeouts). Use configuration.

**OTHERS**

`[document-why] helpful=2 harmful=0 ::` Document the "why" not the "what". Code shows what it does; comments should explain why.

</div>

## Editing Playbooks

### From Dashboard

1. Navigate to the playbook
2. Click the **Edit** button
3. Make your changes
4. Click **Save**

Each edit creates a new version you can review later.

## Team Review Lifecycle

If your workspace has team playbook workflows enabled, each playbook also has a
separate **review state** that controls whether it is still a private draft or
ready to be shared more broadly.

| Review state | What it means | Typical next step |
|--------------|---------------|-------------------|
| `draft` | Working copy owned by an individual member | Submit it for review |
| `proposed` | Waiting for reviewer approval | Approve it, return it to draft, or archive it |
| `approved` | Accepted as a reusable team playbook | Discover it in the shared registry |
| `archived` | Removed from active team circulation | Return it to draft if it should be edited again |

Use the review action buttons on the playbook detail page to move between these
states. The exact available actions depend on the current state:

- From `draft`, you can **Submit for Review** or **Archive**.
- From `proposed`, you can **Approve**, **Return to Draft**, or **Archive**.
- From `approved`, you can **Return to Draft** or **Archive**.
- From `archived`, you can **Return to Draft**.

See [Team Playbook Review & Registry](/docs/user-guides/team-playbook-review)
for the full lifecycle, review history, and reuse flow.

## Organizing Playbooks

### Naming Conventions

Use clear, descriptive names:

- `code-review-typescript` - Language-specific
- `incident-response-p0` - Priority-based
- `onboarding-backend` - Team/area based

For team workspaces, keep names stable enough that other members can recognize
approved playbooks in the shared registry without opening each one first.

## Troubleshooting

### Playbook Too Long

- Break into smaller, focused playbooks
- Use references to other playbooks
- Remove redundant examples

### Inconsistent Results

- Add more specific constraints
- Include negative examples (what NOT to do)
- Define exact output formats

### Evolution Not Improving

- Record more detailed outcomes
- Include reasoning traces
- Provide both success and failure outcomes

## Next Steps

- [Review team playbooks and reuse approved ones](/docs/user-guides/team-playbook-review)
- [Understand evolution](/docs/user-guides/understanding-evolution)
- [Record outcomes](/docs/developer-guides/recording-outcomes)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
