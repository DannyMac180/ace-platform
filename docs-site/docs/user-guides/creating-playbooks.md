---
sidebar_position: 1
---

# Creating Playbooks

Learn how to create effective playbooks that improve over time.

## Creating a New Playbook

### From the Dashboard

1. Log in to [app.aceagent.io](https://app.aceagent.io)
2. Click **New Playbook** in the sidebar
3. Fill in the details:
   - **Name** - Clear, descriptive name
   - **Description** - Brief summary of the playbook's purpose
   - **Content** - The playbook instructions in Markdown
4. Click **Create Playbook**

### Via API

```bash
curl -X POST https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Assistant",
    "description": "Reviews pull requests for quality and security",
    "content": "# Code Review Assistant\n\n## Guidelines\n..."
  }'
```

### Via MCP

```
Use the ace create_playbook tool with:
- name: "Code Review Assistant"
- content: "# Code Review Assistant..."
```

## Playbook Structure

A well-structured playbook includes these sections:

### 1. Title and Role

```markdown
# Code Review Assistant

## Role
You are a senior software engineer with expertise in code review,
security best practices, and clean code principles.
```

### 2. Context

```markdown
## Context
You will be reviewing pull requests for a TypeScript/React codebase.
The team values:
- Type safety
- Test coverage
- Accessibility
- Performance
```

### 3. Guidelines

```markdown
## Guidelines

### Code Quality
- Check for proper error handling
- Verify edge cases are considered
- Look for potential race conditions
- Ensure consistent naming conventions

### Security
- Identify SQL injection risks
- Check for XSS vulnerabilities
- Verify authentication/authorization
- Look for exposed secrets
```

### 4. Output Format

```markdown
## Output Format

Structure your review as:

### Critical Issues
Must be fixed before merging.

### Suggestions
Recommended improvements.

### Questions
Areas needing clarification.

### Praise
What was done well.
```

### 5. Examples (Optional)

````markdown
## Examples

### Example Input
```typescript
function getUserData(id) {
  return db.query(`SELECT * FROM users WHERE id = ${id}`);
}
```

### Example Output
**Critical Issue:** SQL injection vulnerability.

Use parameterized queries instead:
```typescript
function getUserData(id: string) {
  return db.query('SELECT * FROM users WHERE id = $1', [id]);
}
```
````

## Best Practices

### Be Specific

❌ **Too vague:**
```markdown
Review the code carefully.
```

✅ **Specific:**
```markdown
Check for:
- Null/undefined handling
- Error boundaries
- Input validation
- Memory leaks in useEffect cleanup
```

### Include Constraints

```markdown
## Constraints
- Keep reviews concise (under 500 words)
- Focus on issues, not style preferences
- Don't suggest complete rewrites
- Assume good intent from the author
```

### Define Quality Criteria

```markdown
## Quality Criteria

A good review should:
- Be actionable (author knows what to do)
- Be specific (point to exact lines)
- Be educational (explain the "why")
- Be respectful (no condescension)
```

### Use Markdown Features

```markdown
## Checklist
- [ ] Error handling present
- [ ] Types are correct
- [ ] Tests are included
- [ ] Docs updated if needed

## Priority Levels
| Priority | Action Required |
|----------|-----------------|
| P0 | Block merge |
| P1 | Should fix |
| P2 | Consider fixing |
| P3 | Nice to have |
```

## Editing Playbooks

### From Dashboard

1. Navigate to the playbook
2. Click the **Edit** button
3. Make your changes
4. Click **Save**

Each edit creates a new version you can review later.

### Via API

```bash
curl -X PUT https://aceagent.io/api/playbooks/PLAYBOOK_ID \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Updated playbook content..."
  }'
```

## Organizing Playbooks

### Naming Conventions

Use clear, descriptive names:

- `code-review-typescript` - Language-specific
- `incident-response-p0` - Priority-based
- `onboarding-backend` - Team/area based

### Tags (Coming Soon)

Organize playbooks with tags:

- `#code-review`
- `#documentation`
- `#security`
- `#team-backend`

## Templates

Start with these templates for common use cases:

### Code Review

```markdown
# Code Review - [Language]

## Role
Expert code reviewer for [language/framework].

## Focus Areas
1. Correctness
2. Security
3. Performance
4. Maintainability

## Output
Structured feedback with priority levels.
```

### Documentation Writer

```markdown
# Documentation Writer

## Role
Technical writer creating clear, concise documentation.

## Guidelines
- Use active voice
- Keep sentences short
- Include code examples
- Define technical terms

## Output
Markdown-formatted documentation.
```

### Data Analysis

```markdown
# Data Analysis Assistant

## Role
Data analyst providing insights from datasets.

## Approach
1. Understand the data structure
2. Identify patterns and anomalies
3. Generate visualizations
4. Provide actionable insights

## Output
Analysis report with charts and recommendations.
```

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

- [Understand evolution](/docs/user-guides/understanding-evolution)
- [Record outcomes](/docs/developer-guides/recording-outcomes)
- [API reference](/docs/api-reference/playbooks)
