"""Network diagnostic tools for the FastMCP server.

Mounted under namespace "network" → tool names become:
  network_ping, network_dns_lookup, network_http_probe, network_port_check
"""
from __future__ import annotations
import socket
import subprocess
import time
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

network_mcp = FastMCP("NetworkTools")


# ── Tools ──────────────────────────────────────────────────────────────────────

@network_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=False),
    tags={"network", "diagnostic"},
)
async def ping(
    host: Annotated[str, "Hostname or IP address to ping"],
    count: Annotated[int, "Number of ICMP packets to send (default: 4, max: 20)"] = 4,
    ctx: Context = None,
) -> dict:
    """Send ICMP ping packets to a host and report reachability."""
    count = max(1, min(count, 20))
    if ctx:
        await ctx.info(f"Pinging {host} ({count} packets)")
    result = subprocess.run(
        ["ping", "-c", str(count), "-W", "3", host],
        capture_output=True, text=True, timeout=30,
    )
    output = (result.stdout + result.stderr).strip()
    reachable = result.returncode == 0
    return {
        "host": host,
        "count": count,
        "reachable": reachable,
        "output": output,
    }


@network_mcp.tool(
    name="dns_lookup",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=True),
    tags={"network", "diagnostic"},
)
async def dns_lookup(
    host: Annotated[str, "Hostname to resolve"],
    ctx: Context = None,
) -> dict:
    """Resolve a hostname to its IP addresses (IPv4 and IPv6)."""
    if ctx:
        await ctx.info(f"DNS lookup: {host}")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ToolError(f"DNS resolution failed for '{host}': {e}")

    seen: set[str] = set()
    addresses = []
    for family, _, _, _, sockaddr in addr_infos:
        ip = sockaddr[0]
        if ip not in seen:
            seen.add(ip)
            addresses.append({
                "ip": ip,
                "type": "IPv6" if family == socket.AF_INET6 else "IPv4",
            })
    return {"host": host, "addresses": addresses}


@network_mcp.tool(
    name="http_probe",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=False),
    tags={"network", "diagnostic"},
)
async def http_probe(
    url: Annotated[str, "URL to probe (http:// or https:// prefix optional)"],
    method: Annotated[str, "HTTP method (default: GET)"] = "GET",
    timeout: Annotated[int, "Request timeout in seconds (default: 10)"] = 10,
    ctx: Context = None,
) -> dict:
    """Probe an HTTP/HTTPS endpoint and return its status code and latency."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    method = method.upper()
    if ctx:
        await ctx.info(f"HTTP {method} {url}")
    req = Request(url, method=method)
    req.add_header("User-Agent", "MCP-Terminal-Assistant/2.0")
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return {
                "url": url,
                "method": method,
                "status": resp.status,
                "reason": resp.reason,
                "latency_ms": latency_ms,
                "server": resp.headers.get("Server", ""),
                "content_type": resp.headers.get("Content-Type", ""),
            }
    except HTTPError as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "url": url,
            "method": method,
            "status": e.code,
            "reason": e.reason,
            "latency_ms": latency_ms,
            "server": e.headers.get("Server", ""),
            "content_type": e.headers.get("Content-Type", ""),
        }
    except URLError as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        raise ToolError(f"HTTP probe failed for {url}: {e.reason} ({latency_ms:.0f}ms)")


@network_mcp.tool(
    name="port_check",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=False),
    tags={"network", "diagnostic"},
)
async def port_check(
    host: Annotated[str, "Hostname or IP address"],
    port: Annotated[int, "TCP port number to check"],
    timeout: Annotated[int, "Connection timeout in seconds (default: 5)"] = 5,
    ctx: Context = None,
) -> dict:
    """Check if a TCP port is open on a remote host."""
    if ctx:
        await ctx.info(f"Checking TCP port {port} on {host}")
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            status = "open"
    except (socket.timeout, TimeoutError):
        status = "filtered/timeout"
    except ConnectionRefusedError:
        status = "closed"
    except OSError as e:
        status = f"error: {e}"
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    return {"host": host, "port": port, "status": status, "latency_ms": latency_ms}
