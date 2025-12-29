#!/usr/bin/env python3
"""Load testing script for ACE Platform MCP server.

This script tests the MCP server's ability to handle concurrent connections
and measures performance metrics including response times and throughput.

Usage:
    # Run with default settings (10 concurrent users, 100 total requests)
    python scripts/load_test_mcp.py

    # Run with custom settings
    python scripts/load_test_mcp.py --users 50 --requests 500 --host http://localhost:8001

    # Run specific test
    python scripts/load_test_mcp.py --test list_playbooks

Requirements:
    pip install httpx asyncio

Environment:
    API_KEY: API key for authentication (or use --api-key flag)
    MCP_HOST: MCP server URL (or use --host flag)
"""

import argparse
import asyncio
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx


@dataclass
class TestResult:
    """Result of a single test request."""

    success: bool
    duration_ms: float
    status_code: int | None = None
    error: str | None = None


@dataclass
class LoadTestResults:
    """Aggregated results from load test."""

    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_duration_s: float
    response_times_ms: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def requests_per_second(self) -> float:
        """Calculate throughput."""
        if self.total_duration_s == 0:
            return 0.0
        return self.total_requests / self.total_duration_s

    @property
    def avg_response_time_ms(self) -> float:
        """Calculate average response time."""
        if not self.response_times_ms:
            return 0.0
        return statistics.mean(self.response_times_ms)

    @property
    def p50_response_time_ms(self) -> float:
        """Calculate 50th percentile (median) response time."""
        if not self.response_times_ms:
            return 0.0
        return statistics.median(self.response_times_ms)

    @property
    def p95_response_time_ms(self) -> float:
        """Calculate 95th percentile response time."""
        if len(self.response_times_ms) < 2:
            return self.avg_response_time_ms
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    @property
    def p99_response_time_ms(self) -> float:
        """Calculate 99th percentile response time."""
        if len(self.response_times_ms) < 2:
            return self.avg_response_time_ms
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx]

    def print_report(self) -> None:
        """Print formatted test report."""
        print(f"\n{'=' * 60}")
        print(f"Load Test Results: {self.test_name}")
        print(f"{'=' * 60}")
        print(f"Total Requests:     {self.total_requests}")
        print(f"Successful:         {self.successful_requests}")
        print(f"Failed:             {self.failed_requests}")
        print(f"Success Rate:       {self.success_rate:.1f}%")
        print(f"Total Duration:     {self.total_duration_s:.2f}s")
        print(f"Requests/second:    {self.requests_per_second:.1f}")
        print("\nResponse Times:")
        print(f"  Average:          {self.avg_response_time_ms:.1f}ms")
        print(f"  Median (p50):     {self.p50_response_time_ms:.1f}ms")
        print(f"  95th percentile:  {self.p95_response_time_ms:.1f}ms")
        print(f"  99th percentile:  {self.p99_response_time_ms:.1f}ms")
        if self.response_times_ms:
            print(f"  Min:              {min(self.response_times_ms):.1f}ms")
            print(f"  Max:              {max(self.response_times_ms):.1f}ms")
        print(f"{'=' * 60}\n")


class MCPLoadTester:
    """Load tester for MCP server."""

    def __init__(self, host: str, api_key: str, timeout: float = 30.0):
        """Initialize load tester.

        Args:
            host: MCP server URL (e.g., http://localhost:8001)
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def _make_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
    ) -> TestResult:
        """Make a single request and measure response time."""
        url = f"{self.host}{endpoint}"
        start = time.perf_counter()

        try:
            if method == "GET":
                response = await client.get(url, timeout=self.timeout)
            else:
                response = await client.post(url, json=json_data, timeout=self.timeout)

            duration_ms = (time.perf_counter() - start) * 1000

            return TestResult(
                success=response.status_code < 400,
                duration_ms=duration_ms,
                status_code=response.status_code,
            )
        except httpx.TimeoutException:
            duration_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                success=False,
                duration_ms=duration_ms,
                error="Timeout",
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    async def test_health(
        self,
        client: httpx.AsyncClient,
    ) -> TestResult:
        """Test health endpoint."""
        return await self._make_request(client, "GET", "/health")

    async def test_list_playbooks(
        self,
        client: httpx.AsyncClient,
    ) -> TestResult:
        """Test list_playbooks MCP tool via HTTP.

        Note: This simulates the MCP tool call. Actual MCP uses different transport.
        """
        # For HTTP-based testing, we use the REST API equivalent
        return await self._make_request(
            client,
            "GET",
            "/playbooks",
            # The actual MCP would use tool calls, but for load testing
            # we test the underlying API endpoints
        )

    async def run_concurrent_test(
        self,
        test_name: str,
        test_fn: Callable,
        num_users: int,
        requests_per_user: int,
    ) -> LoadTestResults:
        """Run concurrent load test.

        Args:
            test_name: Name of the test for reporting
            test_fn: Async function to call for each request
            num_users: Number of concurrent users (connections)
            requests_per_user: Number of requests per user

        Returns:
            LoadTestResults with aggregated metrics
        """
        total_requests = num_users * requests_per_user
        results: list[TestResult] = []

        print(f"\nRunning: {test_name}")
        print(f"  Concurrent users: {num_users}")
        print(f"  Requests per user: {requests_per_user}")
        print(f"  Total requests: {total_requests}")

        async def user_session(user_id: int) -> list[TestResult]:
            """Simulate a user making multiple requests."""
            user_results = []
            async with httpx.AsyncClient() as client:
                for _ in range(requests_per_user):
                    result = await test_fn(client)
                    user_results.append(result)
            return user_results

        start_time = time.perf_counter()

        # Run all users concurrently
        tasks = [user_session(i) for i in range(num_users)]
        user_results = await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time

        # Flatten results
        for user_result in user_results:
            results.extend(user_result)

        # Aggregate results
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        response_times = [r.duration_ms for r in results]

        return LoadTestResults(
            test_name=test_name,
            total_requests=len(results),
            successful_requests=successful,
            failed_requests=failed,
            total_duration_s=total_duration,
            response_times_ms=response_times,
        )

    async def run_ramp_up_test(
        self,
        test_fn: Callable,
        max_users: int,
        step_size: int = 10,
        requests_per_step: int = 50,
    ) -> list[LoadTestResults]:
        """Run ramp-up test to find breaking point.

        Gradually increases concurrent users to identify performance limits.

        Args:
            test_fn: Async function to call for each request
            max_users: Maximum number of concurrent users
            step_size: Number of users to add per step
            requests_per_step: Requests per user at each step

        Returns:
            List of LoadTestResults for each step
        """
        results = []
        current_users = step_size

        print(f"\n{'=' * 60}")
        print("Ramp-Up Test")
        print(f"{'=' * 60}")

        while current_users <= max_users:
            result = await self.run_concurrent_test(
                test_name=f"Ramp-up ({current_users} users)",
                test_fn=test_fn,
                num_users=current_users,
                requests_per_user=requests_per_step // current_users or 1,
            )
            results.append(result)
            result.print_report()

            # Check if we're hitting errors
            if result.success_rate < 95:
                print(f"Warning: Success rate dropped below 95% at {current_users} users")

            current_users += step_size

        return results


async def main():
    """Main entry point for load testing."""
    parser = argparse.ArgumentParser(description="Load test ACE Platform MCP server")
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "http://localhost:8001"),
        help="MCP server URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY", ""),
        help="API key for authentication",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=10,
        help="Number of concurrent users",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Total number of requests",
    )
    parser.add_argument(
        "--test",
        choices=["health", "list_playbooks", "ramp_up", "all"],
        default="all",
        help="Test to run",
    )
    parser.add_argument(
        "--ramp-max-users",
        type=int,
        default=50,
        help="Maximum users for ramp-up test",
    )

    args = parser.parse_args()

    if not args.api_key and args.test not in ["health", "ramp_up"]:
        print("Warning: No API key provided. Some tests may fail.")
        print("Set API_KEY environment variable or use --api-key flag.\n")

    tester = MCPLoadTester(
        host=args.host,
        api_key=args.api_key,
    )

    requests_per_user = max(1, args.requests // args.users)

    print(f"\n{'=' * 60}")
    print("ACE Platform MCP Server Load Test")
    print(f"{'=' * 60}")
    print(f"Host: {args.host}")
    print(f"Concurrent Users: {args.users}")
    print(f"Total Requests: {args.users * requests_per_user}")

    all_results: list[LoadTestResults] = []

    if args.test in ["health", "all"]:
        result = await tester.run_concurrent_test(
            test_name="Health Check",
            test_fn=tester.test_health,
            num_users=args.users,
            requests_per_user=requests_per_user,
        )
        result.print_report()
        all_results.append(result)

    if args.test in ["list_playbooks", "all"]:
        result = await tester.run_concurrent_test(
            test_name="List Playbooks (API)",
            test_fn=tester.test_list_playbooks,
            num_users=args.users,
            requests_per_user=requests_per_user,
        )
        result.print_report()
        all_results.append(result)

    if args.test in ["ramp_up", "all"]:
        ramp_results = await tester.run_ramp_up_test(
            test_fn=tester.test_health,
            max_users=args.ramp_max_users,
            step_size=10,
            requests_per_step=50,
        )
        all_results.extend(ramp_results)

    # Summary
    if len(all_results) > 1:
        print(f"\n{'=' * 60}")
        print("Summary")
        print(f"{'=' * 60}")
        for result in all_results:
            status = (
                "PASS"
                if result.success_rate >= 99
                else "WARN"
                if result.success_rate >= 95
                else "FAIL"
            )
            print(
                f"[{status}] {result.test_name}: "
                f"{result.success_rate:.1f}% success, "
                f"{result.requests_per_second:.1f} req/s, "
                f"p95={result.p95_response_time_ms:.0f}ms"
            )


if __name__ == "__main__":
    asyncio.run(main())
