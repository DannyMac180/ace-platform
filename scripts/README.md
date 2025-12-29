# ACE Platform Scripts

Utility scripts for development, testing, and operations.

## Load Testing

### load_test_mcp.py

Load testing script for the ACE Platform MCP server and API endpoints.

#### Prerequisites

```bash
pip install httpx
```

#### Usage

```bash
# Basic test (10 concurrent users, 100 requests)
python scripts/load_test_mcp.py

# Custom concurrent users and requests
python scripts/load_test_mcp.py --users 50 --requests 500

# Test against production
python scripts/load_test_mcp.py --host https://your-ace-platform.fly.dev

# Run specific test
python scripts/load_test_mcp.py --test health
python scripts/load_test_mcp.py --test list_playbooks
python scripts/load_test_mcp.py --test ramp_up

# Ramp-up test to find breaking point
python scripts/load_test_mcp.py --test ramp_up --ramp-max-users 100
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `http://localhost:8001` | MCP server URL |
| `--api-key` | `$API_KEY` | API key for authentication |
| `--users` | `10` | Number of concurrent users |
| `--requests` | `100` | Total number of requests |
| `--test` | `all` | Test to run: `health`, `list_playbooks`, `ramp_up`, `all` |
| `--ramp-max-users` | `50` | Maximum users for ramp-up test |

#### Output Metrics

The script reports:

- **Success Rate**: Percentage of successful requests
- **Requests/second**: Throughput
- **Response Times**: Average, median (p50), p95, p99, min, max

#### Example Output

```
============================================================
Load Test Results: Health Check
============================================================
Total Requests:     100
Successful:         100
Failed:             0
Success Rate:       100.0%
Total Duration:     2.45s
Requests/second:    40.8

Response Times:
  Average:          24.5ms
  Median (p50):     22.1ms
  95th percentile:  38.7ms
  99th percentile:  45.2ms
  Min:              18.3ms
  Max:              52.1ms
============================================================
```

#### Interpreting Results

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Success Rate | > 99% | 95-99% | < 95% |
| p95 Response Time | < 100ms | 100-500ms | > 500ms |
| Requests/second | > 100 | 50-100 | < 50 |

#### Running Before Deployment

Before deploying to production, run load tests to ensure:

1. **Health check works under load**:
   ```bash
   python scripts/load_test_mcp.py --test health --users 50 --requests 500
   ```

2. **API endpoints handle concurrent users**:
   ```bash
   python scripts/load_test_mcp.py --test list_playbooks --users 20 --requests 200
   ```

3. **Find breaking point with ramp-up**:
   ```bash
   python scripts/load_test_mcp.py --test ramp_up --ramp-max-users 100
   ```
