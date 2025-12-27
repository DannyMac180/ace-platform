# ACE Platform API Reference

This document provides a complete reference for the ACE Platform REST API.

**Base URL:** `https://your-ace-platform.fly.dev`

**Interactive Docs:** `/docs` (Swagger UI) | `/redoc` (ReDoc)

## Authentication

Most endpoints require JWT authentication. Include the access token in the Authorization header:

```
Authorization: Bearer <access_token>
```

---

## Authentication Endpoints

### Register

Create a new user account.

```http
POST /auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:** `201 Created`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
- `409 Conflict` - Email already registered

---

### Login

Authenticate and get tokens.

```http
POST /auth/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
- `401 Unauthorized` - Invalid credentials

---

### Refresh Token

Get a new access token using a refresh token.

```http
POST /auth/refresh
```

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
- `401 Unauthorized` - Invalid or expired refresh token

---

### Get Current User

Get the authenticated user's information.

```http
GET /auth/me
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_active": true,
  "email_verified": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Playbook Endpoints

### List Playbooks

Get paginated list of user's playbooks.

```http
GET /playbooks
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (min: 1) |
| `page_size` | int | 20 | Items per page (1-100) |
| `status_filter` | string | - | Filter by status: `active`, `archived`, `draft` |

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Coding Agent",
      "description": "Best practices for software development",
      "status": "active",
      "source": "user_created",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T15:45:00Z",
      "version_count": 3,
      "outcome_count": 15
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### Create Playbook

Create a new playbook. Requires active subscription.

```http
POST /playbooks
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "name": "My Playbook",
  "description": "A playbook for task automation",
  "initial_content": "# Guidelines\n\n- Follow best practices\n- Document everything"
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My Playbook",
  "description": "A playbook for task automation",
  "status": "active",
  "source": "user_created",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "current_version": {
    "id": "661f9511-f3ac-52e5-b827-557766551111",
    "version_number": 1,
    "content": "# Guidelines\n\n- Follow best practices\n- Document everything",
    "bullet_count": 2,
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

**Errors:**
- `402 Payment Required` - Playbook limit reached for subscription tier

---

### Get Playbook

Get a specific playbook by ID.

```http
GET /playbooks/{playbook_id}
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My Playbook",
  "description": "A playbook for task automation",
  "status": "active",
  "source": "user_created",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T15:45:00Z",
  "current_version": {
    "id": "661f9511-f3ac-52e5-b827-557766551111",
    "version_number": 3,
    "content": "# Guidelines\n\n- Follow best practices...",
    "bullet_count": 15,
    "created_at": "2024-01-20T15:45:00Z"
  }
}
```

**Errors:**
- `404 Not Found` - Playbook not found

---

### Update Playbook

Update playbook metadata. Requires active subscription.

```http
PUT /playbooks/{playbook_id}
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "name": "Updated Playbook Name",
  "description": "Updated description",
  "status": "archived"
}
```

**Response:** `200 OK` - Returns updated playbook

---

### Delete Playbook

Delete a playbook and all associated data. Requires active subscription.

```http
DELETE /playbooks/{playbook_id}
Authorization: Bearer <access_token>
```

**Response:** `204 No Content`

---

### List Playbook Outcomes

Get outcomes for a specific playbook.

```http
GET /playbooks/{playbook_id}/outcomes
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (1-100) |
| `status_filter` | string | - | Filter: `success`, `failure`, `partial` |
| `processed` | bool | - | Filter by processed state |

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": "772e9622-g4bd-63f6-c938-668877662222",
      "task_description": "Refactored authentication module",
      "outcome_status": "success",
      "notes": "Used dependency injection pattern",
      "reasoning_trace": null,
      "created_at": "2024-01-18T14:30:00Z",
      "processed_at": "2024-01-19T10:00:00Z",
      "evolution_job_id": "883fa733-h5ce-74g7-d049-779988773333"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### List Playbook Evolutions

Get evolution job history for a playbook.

```http
GET /playbooks/{playbook_id}/evolutions
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (1-100) |
| `status_filter` | string | - | Filter: `queued`, `running`, `completed`, `failed` |

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": "883fa733-h5ce-74g7-d049-779988773333",
      "status": "completed",
      "from_version_id": "661f9511-f3ac-52e5-b827-557766551111",
      "to_version_id": "994gb844-i6df-85h8-e150-880099884444",
      "outcomes_processed": 5,
      "error_message": null,
      "created_at": "2024-01-19T09:55:00Z",
      "started_at": "2024-01-19T09:56:00Z",
      "completed_at": "2024-01-19T10:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

## Billing Endpoints

### Get Subscription

Get current subscription information.

```http
GET /billing/subscription
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "tier": "starter",
  "status": "active",
  "current_period_start": "2024-01-01T00:00:00Z",
  "current_period_end": "2024-02-01T00:00:00Z",
  "limits": {
    "monthly_requests": 1000,
    "monthly_tokens": 500000,
    "monthly_cost_usd": "10.00",
    "max_playbooks": 10,
    "max_evolutions_per_day": 20,
    "can_use_premium_models": false,
    "can_export_data": false,
    "priority_support": false
  },
  "stripe_customer_id": "cus_abc123",
  "stripe_subscription_id": null
}
```

---

### Get Billing Usage

Get usage for current billing period.

```http
GET /billing/usage
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "period_start": "2024-01-01T00:00:00Z",
  "period_end": "2024-02-01T00:00:00Z",
  "requests_used": 150,
  "requests_limit": 1000,
  "requests_remaining": 850,
  "tokens_used": 75000,
  "tokens_limit": 500000,
  "tokens_remaining": 425000,
  "cost_usd": "1.50",
  "cost_limit_usd": "10.00",
  "cost_remaining_usd": "8.50",
  "is_within_limits": true,
  "limit_exceeded": null
}
```

---

### Subscribe

Subscribe to a plan.

```http
POST /billing/subscribe
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "tier": "starter",
  "payment_method_id": "pm_card_visa"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Checkout session created for starter tier",
  "subscription": null,
  "checkout_url": "https://checkout.stripe.com/..."
}
```

---

### Create Billing Portal

Get URL to Stripe billing portal.

```http
POST /billing/portal
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
{
  "url": "https://billing.stripe.com/session/..."
}
```

---

## Usage Endpoints

### Get Usage Summary

Get aggregated usage for a time period.

```http
GET /usage/summary
Authorization: Bearer <access_token>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | datetime | 30 days ago | Start of period |
| `end_date` | datetime | now | End of period |

**Response:** `200 OK`
```json
{
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "total_requests": 150,
  "total_prompt_tokens": 50000,
  "total_completion_tokens": 25000,
  "total_tokens": 75000,
  "total_cost_usd": "1.50"
}
```

---

### Get Daily Usage

Get usage broken down by day.

```http
GET /usage/daily
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "date": "2024-01-15T00:00:00Z",
    "request_count": 10,
    "prompt_tokens": 5000,
    "completion_tokens": 2500,
    "total_tokens": 7500,
    "cost_usd": "0.15"
  }
]
```

---

### Get Usage by Playbook

Get usage grouped by playbook.

```http
GET /usage/by-playbook
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
    "playbook_name": "Coding Agent",
    "request_count": 50,
    "total_tokens": 25000,
    "cost_usd": "0.50"
  }
]
```

---

### Get Usage by Operation

Get usage grouped by operation type.

```http
GET /usage/by-operation
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "operation": "evolution_generator",
    "request_count": 30,
    "total_tokens": 40000,
    "cost_usd": "0.80"
  },
  {
    "operation": "evolution_reflector",
    "request_count": 30,
    "total_tokens": 20000,
    "cost_usd": "0.40"
  }
]
```

---

### Get Usage by Model

Get usage grouped by LLM model.

```http
GET /usage/by-model
Authorization: Bearer <access_token>
```

**Response:** `200 OK`
```json
[
  {
    "model": "gpt-4o",
    "request_count": 20,
    "total_tokens": 30000,
    "cost_usd": "0.90"
  },
  {
    "model": "gpt-4o-mini",
    "request_count": 130,
    "total_tokens": 45000,
    "cost_usd": "0.60"
  }
]
```

---

## Health Endpoints

### Health Check

Basic health check endpoint.

```http
GET /health
```

**Response:** `200 OK`
```json
{
  "status": "healthy"
}
```

---

### Readiness Check

Readiness check including database connectivity.

```http
GET /ready
```

**Response:** `200 OK`
```json
{
  "status": "ready",
  "database": "connected"
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common HTTP Status Codes

| Code | Description |
|------|-------------|
| `400` | Bad Request - Invalid input |
| `401` | Unauthorized - Missing or invalid token |
| `402` | Payment Required - Subscription limit reached |
| `403` | Forbidden - Insufficient permissions |
| `404` | Not Found - Resource doesn't exist |
| `409` | Conflict - Resource already exists |
| `422` | Unprocessable Entity - Validation error |
| `500` | Internal Server Error |

---

## Rate Limiting

Rate limits are based on your subscription tier:

| Tier | Requests/Minute |
|------|-----------------|
| Free | 60 |
| Starter | 120 |
| Professional | 300 |
| Enterprise | Custom |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Maximum requests per minute
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Unix timestamp when limit resets
