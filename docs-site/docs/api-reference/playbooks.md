---
sidebar_position: 3
---

# Playbooks API

Create, read, update, and delete playbooks.

## List Playbooks

Get all playbooks for the authenticated user.

```
GET /api/playbooks
```

**Required scope:** `playbooks:read`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Items per page (max 100) |
| `offset` | integer | 0 | Skip N items |

### Response

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Code Review Assistant",
      "description": "Reviews pull requests for quality and security",
      "current_version": 3,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T14:22:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Example

```bash
curl https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Create Playbook

Create a new playbook.

```
POST /api/playbooks
```

**Required scope:** `playbooks:write`

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Playbook name (max 100 chars) |
| `description` | string | No | Brief description (max 500 chars) |
| `content` | string | Yes | Markdown content (max 100KB) |

### Example Request

```bash
curl -X POST https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Assistant",
    "description": "Reviews PRs for quality and security",
    "content": "# Code Review Assistant\n\n## Role\nYou are an expert code reviewer..."
  }'
```

### Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Code Review Assistant",
  "description": "Reviews PRs for quality and security",
  "current_version": 1,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

## Get Playbook

Get a playbook by ID.

```
GET /api/playbooks/{playbook_id}
```

**Required scope:** `playbooks:read`

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `playbook_id` | string | Playbook UUID |

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `version` | integer | Specific version (default: current) |
| `section` | string | Filter to section by heading |

### Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Code Review Assistant",
  "description": "Reviews PRs for quality and security",
  "content": "# Code Review Assistant\n\n## Role\nYou are an expert code reviewer...",
  "current_version": 3,
  "version": 3,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T14:22:00Z"
}
```

### Example: Get Specific Version

```bash
curl "https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000?version=2" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Example: Get Specific Section

```bash
curl "https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000?section=Security" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Returns only content under the "Security" heading.

## Update Playbook

Update a playbook's content (creates a new version).

```
PUT /api/playbooks/{playbook_id}
```

**Required scope:** `playbooks:write`

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | New name |
| `description` | string | No | New description |
| `content` | string | No | New content (creates new version) |
| `change_summary` | string | No | Description of changes |

### Example Request

```bash
curl -X PUT https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Code Review Assistant\n\n## Updated content...",
    "change_summary": "Added input validation checklist"
  }'
```

### Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Code Review Assistant",
  "description": "Reviews PRs for quality and security",
  "current_version": 4,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-21T09:15:00Z"
}
```

## Delete Playbook

Delete a playbook and all its versions.

```
DELETE /api/playbooks/{playbook_id}
```

**Required scope:** `playbooks:write`

### Example

```bash
curl -X DELETE https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Response

```json
{
  "message": "Playbook deleted successfully"
}
```

:::warning
Deleting a playbook also deletes all versions and associated outcomes. This cannot be undone.
:::

## List Versions

Get all versions of a playbook.

```
GET /api/playbooks/{playbook_id}/versions
```

**Required scope:** `playbooks:read`

### Response

```json
{
  "items": [
    {
      "version_number": 3,
      "change_summary": "Evolution: Added input validation guidelines",
      "is_evolution": true,
      "created_at": "2024-01-20T14:22:00Z"
    },
    {
      "version_number": 2,
      "change_summary": "Added security section",
      "is_evolution": false,
      "created_at": "2024-01-18T11:00:00Z"
    },
    {
      "version_number": 1,
      "change_summary": "Initial version",
      "is_evolution": false,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 3
}
```

## Get Version

Get a specific version of a playbook.

```
GET /api/playbooks/{playbook_id}/versions/{version_number}
```

**Required scope:** `playbooks:read`

### Response

```json
{
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "version_number": 2,
  "content": "# Code Review Assistant\n\n## Content at version 2...",
  "change_summary": "Added security section",
  "is_evolution": false,
  "created_at": "2024-01-18T11:00:00Z"
}
```

## Restore Version

Restore a previous version as the current version.

```
POST /api/playbooks/{playbook_id}/versions/{version_number}/restore
```

**Required scope:** `playbooks:write`

### Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "current_version": 5,
  "message": "Restored version 2 as new version 5"
}
```

## Error Responses

### 404 Not Found

```json
{
  "error": "not_found",
  "message": "Playbook not found"
}
```

### 422 Validation Error

```json
{
  "error": "validation_error",
  "message": "Validation failed",
  "details": {
    "name": "Name is required",
    "content": "Content exceeds maximum size of 100KB"
  }
}
```

### 403 Forbidden

```json
{
  "error": "forbidden",
  "message": "You don't have access to this playbook"
}
```

## Limits

| Resource | Limit |
|----------|-------|
| Playbooks per account | Plan-dependent |
| Content size | 100 KB |
| Name length | 100 characters |
| Description length | 500 characters |
| Versions per playbook | Plan-dependent |

## Next Steps

- [Outcomes API](/docs/api-reference/outcomes)
- [Evolution API](/docs/api-reference/evolution)
- [Creating Playbooks Guide](/docs/user-guides/creating-playbooks)
