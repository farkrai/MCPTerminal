"""Docker container and image management tools.

Mounted under namespace "docker" → tool names become:
  docker_ps, docker_logs, docker_inspect, docker_images,
  docker_start, docker_stop

All tools check for docker CLI availability at call time and raise a clear
ToolError if Docker is not installed or the daemon is not running, rather
than crashing at import time.
"""
from __future__ import annotations
import json
import shutil
import subprocess
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

docker_mcp = FastMCP("DockerTools")

_TIMEOUT = 15  # seconds for all docker CLI calls


def _require_docker() -> str:
    """Return path to docker binary or raise ToolError if not found."""
    path = shutil.which("docker")
    if not path:
        raise ToolError(
            "Docker CLI not found. Install Docker: https://docs.docker.com/get-docker/"
        )
    return path


def _run(args: list[str], timeout: int = _TIMEOUT) -> tuple[str, str, int]:
    """Run a docker subcommand. Returns (stdout, stderr, returncode)."""
    docker = _require_docker()
    try:
        r = subprocess.run(
            [docker] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        raise ToolError(f"Docker command timed out after {timeout}s: docker {' '.join(args)}")


def _check_daemon(stderr: str, returncode: int) -> None:
    if returncode != 0 and "Cannot connect" in stderr:
        raise ToolError("Docker daemon is not running. Start it with: sudo systemctl start docker")


# ── Tools ──────────────────────────────────────────────────────────────────────

@docker_mcp.tool(
    name="ps",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"docker", "read-only"},
)
async def ps(
    all_containers: Annotated[bool, "Include stopped containers (default: running only)"] = False,
    ctx: Context = None,
) -> list[dict]:
    """List Docker containers (running by default, all if all_containers=true)."""
    if ctx:
        await ctx.info("Listing docker containers")
    args = ["ps", "--format", "json"]
    if all_containers:
        args.append("-a")
    stdout, stderr, rc = _run(args)
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker ps failed: {stderr.strip()}")
    containers = []
    for line in stdout.strip().splitlines():
        if line.strip():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return containers


@docker_mcp.tool(
    name="logs",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"docker", "read-only"},
)
async def logs(
    container: Annotated[str, "Container name or ID"],
    lines: Annotated[int, "Number of tail lines to return"] = 50,
    ctx: Context = None,
) -> dict:
    """Fetch the last N lines of a container's stdout/stderr logs."""
    if ctx:
        await ctx.info(f"Fetching logs for container: {container}")
    stdout, stderr, rc = _run(["logs", "--tail", str(lines), container])
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker logs failed: {stderr.strip()}")
    return {"container": container, "lines": lines, "output": stdout or stderr}


@docker_mcp.tool(
    name="inspect",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"docker", "read-only"},
)
async def inspect(
    container: Annotated[str, "Container name or ID"],
    ctx: Context = None,
) -> dict:
    """Return detailed metadata for a container (ports, mounts, env, state)."""
    if ctx:
        await ctx.info(f"Inspecting container: {container}")
    stdout, stderr, rc = _run(["inspect", container])
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker inspect failed: {stderr.strip()}")
    data = json.loads(stdout)
    if not data:
        raise ToolError(f"No data returned for container: {container}")
    raw = data[0]
    return {
        "id": raw.get("Id", "")[:12],
        "name": raw.get("Name", "").lstrip("/"),
        "image": raw.get("Config", {}).get("Image", ""),
        "status": raw.get("State", {}).get("Status", ""),
        "ports": raw.get("NetworkSettings", {}).get("Ports", {}),
        "mounts": [m.get("Source") for m in raw.get("Mounts", [])],
        "env": raw.get("Config", {}).get("Env", []),
    }


@docker_mcp.tool(
    name="images",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"docker", "read-only"},
)
async def images(ctx: Context = None) -> list[dict]:
    """List locally available Docker images."""
    if ctx:
        await ctx.info("Listing docker images")
    stdout, stderr, rc = _run(["images", "--format", "json"])
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker images failed: {stderr.strip()}")
    result = []
    for line in stdout.strip().splitlines():
        if line.strip():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return result


@docker_mcp.tool(
    name="start",
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True),
    tags={"docker"},
)
async def start(
    container: Annotated[str, "Container name or ID to start"],
    dry_run: Annotated[bool, "Preview action without executing"] = False,
    ctx: Context = None,
) -> str:
    """Start a stopped Docker container."""
    if policy.dry_run_mode or dry_run:
        return f"[DRY RUN] Would start container: {container}"
    if ctx:
        await ctx.info(f"Starting container: {container}")
    stdout, stderr, rc = _run(["start", container])
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker start failed: {stderr.strip()}")
    return f"Started: {stdout.strip() or container}"


@docker_mcp.tool(
    name="stop",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True),
    tags={"docker", "destructive"},
)
async def stop(
    container: Annotated[str, "Container name or ID to stop"],
    dry_run: Annotated[bool, "Preview action without executing"] = False,
    ctx: Context = None,
) -> str:
    """Gracefully stop a running Docker container (SIGTERM, then SIGKILL after 10 s)."""
    if policy.dry_run_mode or dry_run:
        return f"[DRY RUN] Would stop container: {container}"
    if ctx:
        await ctx.warning(f"Stopping container: {container}")
    stdout, stderr, rc = _run(["stop", container])
    _check_daemon(stderr, rc)
    if rc != 0:
        raise ToolError(f"docker stop failed: {stderr.strip()}")
    return f"Stopped: {stdout.strip() or container}"
