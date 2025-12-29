# Token Economics and Pricing Guide

This document provides a detailed analysis of token usage and costs in the ACE Platform, along with pricing recommendations for subscription tiers.

## Table of Contents

- [Overview](#overview)
- [Token Usage in Evolution](#token-usage-in-evolution)
- [Model Pricing](#model-pricing)
- [Cost Calculations](#cost-calculations)
- [Usage Tracking](#usage-tracking)
- [Pricing Tier Recommendations](#pricing-tier-recommendations)
- [Cost Optimization Strategies](#cost-optimization-strategies)
- [Monitoring and Alerts](#monitoring-and-alerts)

---

## Overview

The ACE Platform uses OpenAI's LLM models for playbook evolution. Token usage occurs primarily during the evolution process, where the Curator agent analyzes outcomes and updates playbooks.

### Key Token-Consuming Operations

| Operation | Description | Typical Token Usage |
|-----------|-------------|---------------------|
| `evolution_curator` | Curator agent analyzing outcomes and updating playbook | 2,000-8,000 tokens |
| `evolution_reflector` | Reflector agent creating outcome summaries (when used) | 500-2,000 tokens |

### Token Flow

```
Outcomes → Aggregated Reflection → Curator → Evolved Playbook
              (minimal tokens)     (primary cost)
```

---

## Token Usage in Evolution

### Evolution Process

Each evolution job processes unprocessed outcomes and updates the playbook:

1. **Outcome Aggregation** (local, no LLM cost)
   - Collects unprocessed outcomes
   - Creates aggregated reflection summary

2. **Curator Agent** (LLM call)
   - Receives: current playbook + reflection + outcome context
   - Returns: evolved playbook + operations applied
   - Token usage tracked in `EvolutionJob.token_totals`

### Typical Evolution Token Usage

Based on the platform configuration:

| Factor | Value | Impact on Tokens |
|--------|-------|------------------|
| `EVOLUTION_MAX_TOKENS` | 4,096 (default) | Max completion tokens per call |
| `EVOLUTION_PLAYBOOK_TOKEN_BUDGET` | 80,000 (default) | Max playbook content size |
| Outcomes per evolution | 5-20 typically | ~100-500 tokens per outcome in context |

**Estimated tokens per evolution:**

| Playbook Size | Outcomes | Input Tokens | Output Tokens | Total |
|--------------|----------|--------------|---------------|-------|
| Small (1KB) | 5 | ~1,000 | ~1,500 | ~2,500 |
| Medium (5KB) | 10 | ~2,500 | ~2,000 | ~4,500 |
| Large (20KB) | 20 | ~6,000 | ~3,000 | ~9,000 |

---

## Model Pricing

### Supported Models and Costs

Prices are per 1 million tokens (as of December 2024):

| Model | Input ($/1M) | Output ($/1M) | Best For |
|-------|--------------|---------------|----------|
| **gpt-4o** | $2.50 | $10.00 | Default, balanced cost/quality |
| **gpt-4o-mini** | $0.15 | $0.60 | Cost-sensitive workloads |
| **gpt-4-turbo** | $10.00 | $30.00 | Complex reasoning |
| **gpt-4** | $30.00 | $60.00 | Legacy, highest quality |
| **gpt-3.5-turbo** | $0.50 | $1.50 | Simple tasks, lowest cost |
| **o1** | $15.00 | $60.00 | Advanced reasoning |
| **o1-mini** | $3.00 | $12.00 | Reasoning at lower cost |

### Configuration

Set the evolution model in environment variables:

```bash
# Default model for Curator agent
EVOLUTION_CURATOR_MODEL=gpt-4o

# Default model for Reflector agent (when used)
EVOLUTION_REFLECTOR_MODEL=gpt-4o

# For cost optimization, consider:
EVOLUTION_CURATOR_MODEL=gpt-4o-mini
```

---

## Cost Calculations

### Per-Evolution Cost Examples

Using **gpt-4o** (default):

| Scenario | Input Tokens | Output Tokens | Cost |
|----------|--------------|---------------|------|
| Small evolution | 1,000 | 1,500 | $0.0175 |
| Medium evolution | 2,500 | 2,000 | $0.0263 |
| Large evolution | 6,000 | 3,000 | $0.0450 |

Using **gpt-4o-mini** (cost-optimized):

| Scenario | Input Tokens | Output Tokens | Cost |
|----------|--------------|---------------|------|
| Small evolution | 1,000 | 1,500 | $0.0011 |
| Medium evolution | 2,500 | 2,000 | $0.0016 |
| Large evolution | 6,000 | 3,000 | $0.0027 |

### Monthly Cost Projections

Assuming 10 evolutions per playbook per month:

| Playbooks | Evolutions/Month | gpt-4o Cost | gpt-4o-mini Cost |
|-----------|------------------|-------------|------------------|
| 1 | 10 | $0.26 | $0.02 |
| 5 | 50 | $1.32 | $0.08 |
| 20 | 200 | $5.26 | $0.32 |
| 50 | 500 | $13.15 | $0.80 |
| 100 | 1,000 | $26.30 | $1.60 |

---

## Usage Tracking

### Database Records

All LLM usage is logged to the `usage_records` table:

```sql
SELECT
    operation,
    model,
    SUM(prompt_tokens) as total_input,
    SUM(completion_tokens) as total_output,
    SUM(cost_usd) as total_cost
FROM usage_records
WHERE user_id = 'your-user-id'
  AND created_at > NOW() - INTERVAL '30 days'
GROUP BY operation, model;
```

### API Endpoints

**Get usage summary:**
```bash
GET /usage/summary
Authorization: Bearer <token>
```

**Get daily breakdown:**
```bash
GET /usage/daily
Authorization: Bearer <token>
```

**Get usage by playbook:**
```bash
GET /usage/by-playbook
Authorization: Bearer <token>
```

### Prometheus Metrics

The platform exposes usage metrics:

```
# Total tokens used by model
ace_tokens_total{model="gpt-4o", type="prompt"}
ace_tokens_total{model="gpt-4o", type="completion"}

# Total cost by model
ace_cost_usd_total{model="gpt-4o"}

# Evolution job metrics
ace_evolution_duration_seconds_bucket{status="completed"}
```

---

## Pricing Tier Recommendations

Based on the cost analysis, here are recommended subscription tiers:

### Free Tier

| Feature | Limit | Estimated OpenAI Cost |
|---------|-------|----------------------|
| Playbooks | 1 | - |
| Evolutions/month | 10 | ~$0.26 (gpt-4o) |
| Outcomes/month | 100 | - |
| Model | gpt-4o-mini | ~$0.02 |

**Platform margin:** Absorb cost for user acquisition.

### Starter Tier ($9/month)

| Feature | Limit | Estimated OpenAI Cost |
|---------|-------|----------------------|
| Playbooks | 5 | - |
| Evolutions/month | 50 | ~$1.32 (gpt-4o) |
| Outcomes/month | 500 | - |
| Model | gpt-4o | - |
| API access | Yes | - |

**Platform margin:** ~85% ($7.68)

### Professional Tier ($29/month)

| Feature | Limit | Estimated OpenAI Cost |
|---------|-------|----------------------|
| Playbooks | 20 | - |
| Evolutions/month | 200 | ~$5.26 (gpt-4o) |
| Outcomes/month | 2,000 | - |
| Model | gpt-4o | - |
| API access | Yes | - |
| Priority support | Yes | - |

**Platform margin:** ~82% ($23.74)

### Enterprise Tier (Custom)

| Feature | Limit | Pricing |
|---------|-------|---------|
| Playbooks | Unlimited | Based on usage |
| Evolutions | Unlimited | Pass-through + margin |
| Outcomes | Unlimited | - |
| Model | Choice | - |
| Dedicated support | Yes | - |
| SLA | 99.9% | - |

**Pricing model:** Base fee + usage-based pricing at 1.5x OpenAI cost.

---

## Cost Optimization Strategies

### 1. Model Selection

Choose the right model for your use case:

```bash
# For cost-sensitive workloads
EVOLUTION_CURATOR_MODEL=gpt-4o-mini

# For highest quality (when needed)
EVOLUTION_CURATOR_MODEL=gpt-4o
```

**Savings:** gpt-4o-mini is ~94% cheaper than gpt-4o.

### 2. Evolution Thresholds

Adjust when evolutions trigger:

```bash
# Require more outcomes before evolution (default: 5)
EVOLUTION_OUTCOME_THRESHOLD=10

# Increase time between auto-evolutions (default: 24 hours)
EVOLUTION_TIME_THRESHOLD_HOURS=48
```

**Impact:** Fewer evolutions = lower costs, but slower playbook improvement.

### 3. Playbook Token Budget

Limit playbook size to reduce input tokens:

```bash
# Reduce from 80,000 (default) if playbooks are small
EVOLUTION_PLAYBOOK_TOKEN_BUDGET=40000
```

### 4. Batch Outcomes

Process more outcomes per evolution rather than triggering frequently:

```bash
# Process 20 outcomes at once instead of 5
EVOLUTION_OUTCOME_THRESHOLD=20
```

**Impact:** Slightly higher per-evolution cost but fewer total evolutions.

### 5. Manual vs Automatic Evolution

For cost control, disable automatic evolution:

```bash
# In settings, use manual triggers only
```

Then trigger manually via API or MCP when ready:

```bash
POST /playbooks/{id}/evolve
```

---

## Monitoring and Alerts

### Set Up Cost Alerts

Monitor usage with Prometheus alerting:

```yaml
# prometheus-alerts.yml
groups:
  - name: ace-cost-alerts
    rules:
      - alert: HighTokenUsage
        expr: increase(ace_tokens_total[1h]) > 100000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: High token usage detected

      - alert: DailyCostExceeded
        expr: increase(ace_cost_usd_total[24h]) > 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: Daily cost exceeded $10
```

### Usage Dashboard

Create a Grafana dashboard to track:

1. **Token usage over time** - Identify trends
2. **Cost by playbook** - Find expensive playbooks
3. **Evolution frequency** - Track automation rate
4. **Cost per evolution** - Monitor efficiency

### Rate Limiting

Implement rate limits to prevent runaway costs:

```bash
# Maximum evolutions per playbook per day
RATE_LIMIT_EVOLUTIONS_PER_PLAYBOOK=10

# Maximum total evolutions per user per day
RATE_LIMIT_EVOLUTIONS_PER_USER=50
```

---

## Appendix: Cost Calculation Formula

The platform calculates costs using:

```python
def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    input_price, output_price = MODEL_PRICING.get(model, DEFAULT_PRICING)

    # Prices are per 1M tokens
    input_cost = (Decimal(prompt_tokens) * input_price) / Decimal("1000000")
    output_cost = (Decimal(completion_tokens) * output_price) / Decimal("1000000")

    return input_cost + output_cost
```

**Example:**
- Model: gpt-4o
- Input: 2,500 tokens
- Output: 2,000 tokens
- Cost: (2,500 * $2.50 / 1M) + (2,000 * $10.00 / 1M) = $0.00625 + $0.02 = **$0.02625**
