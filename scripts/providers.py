#!/usr/bin/env python3
"""
Run an evidence provider from the registry.

    run_provider(provider_id, request, registry_path="connectors/registry.yaml",
                 config_path="pm.config.yaml", cache_dir=".cache/providers",
                 return_meta=False)

`request` follows schemas/provider-io.schema.json (input). Only `kind: script`
providers run here (command split with shlex, request JSON on stdin, output
JSON on stdout, cwd = repo root, 60 s timeout). The environment variable
PM_CONFIG is set to the absolute config path for the provider.

Return shape: the output dict (provider-io output schema, rows capped at
data.max_rows_returned with the caveat "rows truncated to N"). Because the
output schema forbids extra keys, cache hits are reported on a second path:
with return_meta=True the function returns (output, {"cached": bool}).

Cache: JSON {cached_at, output} files under cache_dir, keyed by sha256 of
provider id + query_id + sorted params, valid for data.cache_ttl_hours.
Only ok outputs are cached. Relative paths are resolved against the repo root.

Every failure raises ProviderError with a one-line message. A provider that
answers {"ok": false, "error": ...} is turned into a ProviderError too.
"""

import sys
import json
import shlex
import hashlib
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple, Union

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVIDER_TIMEOUT_SECONDS = 60


class ProviderError(Exception):
    """A provider could not be run or returned an unusable answer."""


def resolve_path(path: Union[str, Path]) -> Path:
    """Absolute paths stay as they are; relative ones are relative to the repo root."""
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def _load_yaml(path: Union[str, Path], label: str) -> Dict[str, Any]:
    p = resolve_path(path)
    try:
        with open(p, "r") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ProviderError(f"{label} not found: {p}")
    except (OSError, yaml.YAMLError) as e:
        raise ProviderError(f"Cannot read {label} {p}: {e}")
    if not isinstance(data, dict):
        raise ProviderError(f"{label} {p} must be a mapping")
    return data


def _load_schema(name: str) -> Dict[str, Any]:
    path = REPO_ROOT / "schemas" / f"{name}.schema.json"
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ProviderError(f"Cannot load schema {path}: {e}")


def _validator(def_name: str) -> Draft202012Validator:
    schema = _load_schema("provider-io")
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{def_name}"})


def load_registry(path: Union[str, Path] = "connectors/registry.yaml") -> Dict[str, Any]:
    """Load and schema-validate a registry file."""
    registry = _load_yaml(path, "Registry")
    errors = list(Draft202012Validator(_load_schema("registry")).iter_errors(registry))
    if errors:
        raise ProviderError(f"Registry {path} is invalid: {errors[0].message}")
    return registry


def load_config(path: Union[str, Path] = "pm.config.yaml") -> Dict[str, Any]:
    """Load a pm config file and check the data section this module needs."""
    config = _load_yaml(path, "Config")
    data = config.get("data")
    if not isinstance(data, dict):
        raise ProviderError(f"Config {path} is missing the data section")
    for key in ("cache_ttl_hours", "max_rows_returned"):
        if not isinstance(data.get(key), int) or isinstance(data.get(key), bool):
            raise ProviderError(f"Config {path}: data.{key} must be an integer")
    return config


def _cache_key(provider_id: str, request: Dict[str, Any]) -> str:
    text = provider_id + "\n" + request["query_id"] + "\n" + json.dumps(
        request["params"], sort_keys=True, default=str
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_cache(cache_file: Path, ttl_hours: int):
    """Return the cached output if it exists and is fresh, else None."""
    try:
        with open(cache_file, "r") as f:
            entry = json.load(f)
        cached_at = datetime.fromisoformat(entry["cached_at"])
        output = entry["output"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(output, dict):
        return None
    if datetime.now(timezone.utc) - cached_at < timedelta(hours=ttl_hours):
        return output
    return None


def _write_cache(cache_file: Path, output: Dict[str, Any]) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump({"cached_at": datetime.now(timezone.utc).isoformat(), "output": output}, f)
    except OSError:
        pass  # a cache that cannot be written only costs a re-run


def _command_args(command: str, provider_id: str):
    try:
        args = shlex.split(command)
    except ValueError as e:
        raise ProviderError(f"provider '{provider_id}' has an invalid command: {e}")
    if not args:
        raise ProviderError(f"provider '{provider_id}' has an empty command")
    if args[0] in ("python", "python3"):
        args[0] = sys.executable
    return args


def _execute(provider: Dict[str, Any], request: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    provider_id = provider["id"]
    args = _command_args(provider["command"], provider_id)
    env = dict(os.environ)
    env["PM_CONFIG"] = str(config_path)
    try:
        result = subprocess.run(
            args,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ProviderError(f"provider '{provider_id}' timed out after {PROVIDER_TIMEOUT_SECONDS}s")
    except OSError as e:
        raise ProviderError(f"provider '{provider_id}' could not be started: {e}")

    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        detail = f": {lines[-1]}" if lines else ""
        raise ProviderError(f"provider '{provider_id}' exited with code {result.returncode}{detail}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ProviderError(f"provider '{provider_id}' returned invalid JSON")

    errors = list(_validator("output").iter_errors(output))
    if errors:
        raise ProviderError(f"provider '{provider_id}' output is invalid: {errors[0].message}")

    if not output["ok"]:
        raise ProviderError(f"provider '{provider_id}' refused the request: {output['error']}")
    return output


def run_provider(
    provider_id: str,
    request: Dict[str, Any],
    registry_path: Union[str, Path] = "connectors/registry.yaml",
    config_path: Union[str, Path] = "pm.config.yaml",
    cache_dir: Union[str, Path] = ".cache/providers",
    return_meta: bool = False,
) -> Union[Dict[str, Any], Tuple[Dict[str, Any], Dict[str, bool]]]:
    """Run a script provider (see module docstring). Raises ProviderError."""
    registry = load_registry(registry_path)
    config = load_config(config_path)

    provider = next((p for p in registry["providers"] if p["id"] == provider_id), None)
    if provider is None:
        raise ProviderError(f"unknown provider '{provider_id}'")
    if not provider["enabled"]:
        raise ProviderError(f"provider '{provider_id}' is disabled")
    if provider["kind"] == "mcp":
        raise ProviderError("mcp providers are called by the agent, not by scripts")

    errors = list(_validator("input").iter_errors(request))
    if errors:
        raise ProviderError(f"request is invalid: {errors[0].message}")

    data = config["data"]
    cache_file = resolve_path(cache_dir) / f"{_cache_key(provider_id, request)}.json"

    cached = _read_cache(cache_file, data["cache_ttl_hours"])
    if cached is not None:
        return (cached, {"cached": True}) if return_meta else cached

    output = _execute(provider, request, resolve_path(config_path))

    max_rows = data["max_rows_returned"]
    if len(output["rows"]) > max_rows:
        output["rows"] = output["rows"][:max_rows]
        output["caveats"] = list(output["caveats"]) + [f"rows truncated to {max_rows}"]

    _write_cache(cache_file, output)
    return (output, {"cached": False}) if return_meta else output
