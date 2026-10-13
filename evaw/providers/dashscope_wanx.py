"""DashScope 通义万相 — China-reachable Live Gen (T2I + I2I with structure_ref).

T2I (default model wan2.2-t2i-plus):
  POST .../text2image/image-synthesis

I2I (when Knowledge structure_ref.png exists):
  1) Upload local ref to DashScope temp OSS → oss://...
  2) POST wanx-v1 text2image with input.ref_img + ref_mode=repaint
  3) On I2I failure → fall back to T2I (same prompt, no ref)

Env:
  DASHSCOPE_API_KEY              required for real calls
  EVAW_DASHSCOPE_MODEL           T2I default wan2.2-t2i-plus
  EVAW_DASHSCOPE_I2I_MODEL       I2I default wanx-v1 (supports ref_img)
  EVAW_DASHSCOPE_I2I             default true; set 0 to force T2I only
  EVAW_DASHSCOPE_REF_STRENGTH    base default 0.85; structure-sensitive auto-locks ≥0.95
  EVAW_DASHSCOPE_REF_MODE        default repaint
  EVAW_DASHSCOPE_SIZE            default 1024*1024
  EVAW_DASHSCOPE_STYLE           wanx-v1 only; default <photography>
  EVAW_DASHSCOPE_BASE_URL        default https://dashscope.aliyuncs.com/api/v1
  EVAW_DASHSCOPE_POLL_SEC        default 2
  EVAW_DASHSCOPE_TIMEOUT_SEC     default 180
  EVAW_DASHSCOPE_PROMPT_EXTEND   default false
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from ..knowledge import load_structure_constraints
from ..schema import GeneratedAsset, new_id
from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult
from .prompt import (
    STRUCTURE_LOCK_NEGATIVE_PROMPT,
    build_ecommerce_prompt,
    build_structure_lock_prompt,
    is_structure_sensitive_gen,
)

DEFAULT_BASE = os.environ.get(
    "EVAW_DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"
).rstrip("/")
DEFAULT_MODEL = os.environ.get("EVAW_DASHSCOPE_MODEL", "wan2.2-t2i-plus")
DEFAULT_I2I_MODEL = os.environ.get("EVAW_DASHSCOPE_I2I_MODEL", "wanx-v1")
DEFAULT_SIZE = os.environ.get("EVAW_DASHSCOPE_SIZE", "1024*1024")
DEFAULT_STYLE = os.environ.get("EVAW_DASHSCOPE_STYLE", "<photography>")
DEFAULT_POLL = float(os.environ.get("EVAW_DASHSCOPE_POLL_SEC", "2"))
DEFAULT_TIMEOUT = float(os.environ.get("EVAW_DASHSCOPE_TIMEOUT_SEC", "180"))
DEFAULT_PROMPT_EXTEND = (
    os.environ.get("EVAW_DASHSCOPE_PROMPT_EXTEND", "false").strip().lower()
    in ("1", "true", "yes", "on")
)
DEFAULT_REF_STRENGTH = float(os.environ.get("EVAW_DASHSCOPE_REF_STRENGTH", "0.85"))
DEFAULT_REF_MODE = os.environ.get("EVAW_DASHSCOPE_REF_MODE", "repaint").strip() or "repaint"


def _i2i_enabled() -> bool:
    v = (os.environ.get("EVAW_DASHSCOPE_I2I") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


# Product default: structure-sensitive I2I locks strength at least this high
STRUCTURE_SENSITIVE_REF_STRENGTH = 0.95


def _resolve_ref_strength(*, structure_sensitive: bool, configured: float) -> float:
    """PM rule: structure-sensitive SKUs auto-lock ≥0.95 (override weaker env)."""
    strength = max(0.0, min(1.0, float(configured)))
    if not structure_sensitive:
        return strength
    # Bump weaker env / constructor values up to the product floor
    return max(strength, STRUCTURE_SENSITIVE_REF_STRENGTH)


def _build_prompt(
    req: ProviderGenerateRequest,
    *,
    structure_sensitive: bool,
    use_i2i: bool,
    constraints,
) -> str:
    """I2I + structure-sensitive → short lock prompt; else full ecommerce prompt."""
    if use_i2i and structure_sensitive:
        return build_structure_lock_prompt(req, constraints=constraints, max_chars=220)
    return build_ecommerce_prompt(req, lang="zh", max_chars=480, constraints=constraints)


class DashScopeWanxProvider(GenerationProvider):
    """通义万相文生图 / 参考图生图（国内可达）。"""

    name = "dashscope_wanx"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        i2i_model: str = DEFAULT_I2I_MODEL,
        size: str = DEFAULT_SIZE,
        style: str = DEFAULT_STYLE,
        base_url: str = DEFAULT_BASE,
        poll_sec: float = DEFAULT_POLL,
        timeout_sec: float = DEFAULT_TIMEOUT,
        prompt_extend: bool = DEFAULT_PROMPT_EXTEND,
        ref_strength: float = DEFAULT_REF_STRENGTH,
        ref_mode: str = DEFAULT_REF_MODE,
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model
        self.i2i_model = i2i_model
        self.size = size
        self.style = style
        self.base_url = base_url.rstrip("/")
        self.poll_sec = poll_sec
        self.timeout_sec = timeout_sec
        self.prompt_extend = prompt_extend
        self.ref_strength = max(0.0, min(1.0, float(ref_strength)))
        self.ref_mode = ref_mode

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        if not self.api_key:
            return ProviderGenerateResult(
                error_code="DASHSCOPE_NO_KEY",
                error_message=(
                    "DASHSCOPE_API_KEY not set. "
                    "Add it to .env.local (阿里云百炼控制台 → API-KEY)."
                ),
            )

        run_dir = req.artifacts_dir / req.task.task_id / req.result_id
        run_dir.mkdir(parents=True, exist_ok=True)

        constraints = load_structure_constraints(
            req.task.sku_id, platform=req.task.platform.value
        )
        ref_path = constraints.structure_image
        structure_sensitive = is_structure_sensitive_gen(req, constraints=constraints)

        # Product rule: structure_ref present → force I2I (kill-switch still honored
        # unless structure-sensitive, in which case we warn and still force).
        i2i_kill = not _i2i_enabled()
        has_ref = bool(ref_path and ref_path.is_file())
        if has_ref and (not i2i_kill or structure_sensitive):
            use_i2i = True
            if i2i_kill and structure_sensitive:
                print(
                    "[gen:dashscope] WARN EVAW_DASHSCOPE_I2I=0 ignored: "
                    "structure-sensitive + structure_ref → force I2I"
                )
        else:
            use_i2i = False

        # Lock ref strength / mode for structure-sensitive (PM rule — no hand-tune)
        ref_strength = _resolve_ref_strength(
            structure_sensitive=structure_sensitive, configured=self.ref_strength
        )
        ref_mode = "repaint" if structure_sensitive else self.ref_mode
        negative_prompt = (
            STRUCTURE_LOCK_NEGATIVE_PROMPT if (use_i2i and structure_sensitive) else None
        )
        prompt = _build_prompt(
            req,
            structure_sensitive=structure_sensitive,
            use_i2i=use_i2i,
            constraints=constraints,
        )

        mode = "t2i"
        model_used = self.model
        ref_oss: Optional[str] = None
        i2i_error: Optional[str] = None

        if use_i2i:
            try:
                ref_oss = self._upload_temp_oss(ref_path, model=self.i2i_model)
                mode = "i2i"
                model_used = self.i2i_model
                print(
                    f"[gen:dashscope] mode=i2i model={model_used} "
                    f"ref={ref_path.name} strength={ref_strength} "
                    f"ref_mode={ref_mode} structure_sensitive={structure_sensitive}"
                )
                print(f"[gen:dashscope] prompt={prompt}")
                if negative_prompt:
                    print(f"[gen:dashscope] negative_prompt={negative_prompt}")
            except Exception as e:
                i2i_error = str(e)
                use_i2i = False
                mode = "t2i"
                model_used = self.model
                # Rebuild long prompt for T2I fallback
                prompt = _build_prompt(
                    req,
                    structure_sensitive=False,
                    use_i2i=False,
                    constraints=constraints,
                )
                negative_prompt = None
                print(
                    f"[gen:dashscope] mode=t2i (i2i upload failed: {i2i_error}); "
                    f"falling back to T2I model={model_used}"
                )
        else:
            reason = "i2i disabled" if i2i_kill else "no structure_ref"
            print(
                f"[gen:dashscope] mode=t2i model={model_used} ({reason}) "
                f"structure_sensitive={structure_sensitive}"
            )

        assets: list[GeneratedAsset] = []
        task_ids: list[str] = []
        modes_used: list[str] = []

        for i in range(req.candidate_count):
            idx = i + 1
            # Structure-lock I2I: keep prompt short; do not append lifestyle "变体" copy
            if mode == "i2i" and structure_sensitive:
                variation = prompt
            else:
                variation = f"{prompt} 变体 {idx}/{req.candidate_count}。"
            cand_mode = mode
            cand_model = model_used
            try:
                if cand_mode == "i2i" and ref_oss:
                    try:
                        task_id = self._submit_i2i(
                            variation,
                            ref_oss,
                            ref_strength=ref_strength,
                            ref_mode=ref_mode,
                            negative_prompt=negative_prompt,
                        )
                    except Exception as e:
                        # Per-candidate I2I failure → T2I for this candidate
                        print(
                            f"[gen:dashscope] cand_{idx} i2i failed ({e}); "
                            "falling back to t2i"
                        )
                        i2i_error = i2i_error or str(e)
                        cand_mode = "t2i"
                        cand_model = self.model
                        task_id = self._submit_t2i(variation, model=cand_model)
                else:
                    task_id = self._submit_t2i(variation, model=cand_model)
                task_ids.append(task_id)
                modes_used.append(cand_mode)
                urls = self._poll_urls(task_id)
            except Exception as e:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="DASHSCOPE_HTTP_ERROR",
                    error_message=str(e),
                    provider_meta={
                        "kind": self.name,
                        "partial": len(assets),
                        "model": cand_model,
                        "mode": cand_mode,
                        "task_ids": task_ids,
                        "modes_used": modes_used,
                        "external_api": True,
                        "i2i_error": i2i_error,
                    },
                )

            if not urls:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="DASHSCOPE_NO_IMAGE",
                    error_message=f"Task {task_id} succeeded but returned no image URL",
                    provider_meta={
                        "kind": self.name,
                        "model": cand_model,
                        "mode": cand_mode,
                        "task_ids": task_ids,
                        "modes_used": modes_used,
                        "external_api": True,
                    },
                )

            path = run_dir / f"cand_{idx}.png"
            try:
                self._download(urls[0], path)
            except Exception as e:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="DASHSCOPE_SAVE_ERROR",
                    error_message=str(e),
                    provider_meta={
                        "kind": self.name,
                        "model": cand_model,
                        "mode": cand_mode,
                        "task_ids": task_ids,
                        "modes_used": modes_used,
                        "external_api": True,
                    },
                )

            uri = path.resolve().as_uri()
            assets.append(
                GeneratedAsset(
                    asset_id=new_id("asset"),
                    task_id=req.task.task_id,
                    generation_result_id=req.result_id,
                    asset_type=req.task.asset_type.value,
                    uri=uri,
                    platform_target=req.task.platform.value,
                    mode=req.mode,
                    knowledge_snapshot_id=req.snapshot_id,
                    strategy_version=req.strategy_version,
                    version=f"v{idx}",
                )
            )

        primary_mode = (
            "i2i"
            if modes_used and all(m == "i2i" for m in modes_used)
            else ("mixed" if "i2i" in modes_used and "t2i" in modes_used else "t2i")
        )
        manifest = {
            "provider": self.name,
            "mode": primary_mode,
            "modes_used": modes_used,
            "model": model_used if primary_mode == "i2i" else self.model,
            "t2i_model": self.model,
            "i2i_model": self.i2i_model,
            "size": self.size,
            "style": self.style,
            "ref_strength": ref_strength if primary_mode != "t2i" else None,
            "ref_mode": ref_mode if primary_mode != "t2i" else None,
            "structure_sensitive": structure_sensitive,
            "structure_lock": bool(mode == "i2i" and structure_sensitive),
            "negative_prompt": negative_prompt,
            "structure_ref": str(ref_path) if ref_path else None,
            "structure_constraints": {
                "must_show": constraints.must_show,
                "must_not": constraints.must_not,
                "materials": constraints.materials,
                "platform_notes": constraints.platform_notes,
            },
            "task_id": req.task.task_id,
            "generation_result_id": req.result_id,
            "knowledge_snapshot_id": req.snapshot_id,
            "strategy_version": req.strategy_version,
            "candidate_count": len(assets),
            "prompt": prompt,
            "dashscope_task_ids": task_ids,
            "i2i_error": i2i_error,
            "assets": [
                {"asset_id": a.asset_id, "uri": a.uri, "version": a.version}
                for a in assets
            ],
        }
        (run_dir / "candidates.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[gen:dashscope] done mode={primary_mode} "
            f"candidates={len(assets)} dir={run_dir}"
        )

        return ProviderGenerateResult(
            assets=assets,
            provider_meta={
                "kind": self.name,
                "wrote_files": True,
                "artifacts_dir": str(run_dir),
                "model": manifest["model"],
                "mode": primary_mode,
                "modes_used": modes_used,
                "external_api": True,
                "dashscope_task_ids": task_ids,
                "structure_ref": str(ref_path) if ref_path else None,
                "structure_sensitive": structure_sensitive,
                "ref_strength": ref_strength if primary_mode != "t2i" else None,
                "ref_mode": ref_mode if primary_mode != "t2i" else None,
                "negative_prompt": negative_prompt,
                "i2i_error": i2i_error,
            },
        )

    def _headers(self, *, oss_resolve: bool = False) -> dict:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "evaw-live-gen/0.2-dashscope",
        }
        if oss_resolve:
            h["X-DashScope-OssResourceResolve"] = "enable"
        return h

    def _upload_temp_oss(self, file_path: Path, *, model: str) -> str:
        """Upload local structure_ref to DashScope temp OSS; return oss:// URL."""
        policy_url = (
            f"{self.base_url}/uploads?"
            + urllib.parse.urlencode({"action": "getPolicy", "model": model})
        )
        policy_resp = self._request("GET", policy_url, headers=self._headers())
        data = policy_resp.get("data") or {}
        if not data.get("upload_host") or not data.get("upload_dir"):
            raise RuntimeError(
                f"DashScope getPolicy missing fields: keys={list(policy_resp.keys())}"
            )

        # Unique name: forbid_overwrite is typically true
        suffix = file_path.suffix or ".png"
        remote_name = f"evaw_{uuid.uuid4().hex}{suffix}"
        key = f"{data['upload_dir'].rstrip('/')}/{remote_name}"

        fields = {
            "OSSAccessKeyId": str(data["oss_access_key_id"]),
            "Signature": str(data["signature"]),
            "policy": str(data["policy"]),
            "x-oss-object-acl": str(data.get("x_oss_object_acl") or "private"),
            "x-oss-forbid-overwrite": str(
                data.get("x_oss_forbid_overwrite") or "true"
            ),
            "key": key,
            "success_action_status": "200",
        }
        content_type = mimetypes.guess_type(str(file_path))[0] or "image/png"
        body, content_type_header = _encode_multipart(
            fields, {"file": (remote_name, file_path.read_bytes(), content_type)}
        )
        upload_req = urllib.request.Request(
            data["upload_host"],
            data=body,
            headers={
                "Content-Type": content_type_header,
                "User-Agent": "evaw-live-gen/0.2-dashscope",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(upload_req, timeout=120) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"OSS upload HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OSS upload HTTP {e.code}: {err_body}") from e

        return f"oss://{key}"

    def _submit_t2i(self, prompt: str, *, model: Optional[str] = None) -> str:
        model = model or self.model
        url = f"{self.base_url}/services/aigc/text2image/image-synthesis"
        is_v1 = model.strip().lower() in ("wanx-v1", "wanx")
        max_chars = 800 if is_v1 else 500
        params: dict = {
            "size": self.size,
            "n": 1,
            "watermark": False,
            "prompt_extend": self.prompt_extend,
        }
        if is_v1:
            params["style"] = self.style
            params.pop("watermark", None)
            params.pop("prompt_extend", None)
        body = {
            "model": model,
            "input": {"prompt": prompt[:max_chars]},
            "parameters": params,
        }
        headers = {**self._headers(), "X-DashScope-Async": "enable"}
        data = self._request("POST", url, headers=headers, body=body)
        return self._extract_task_id(data)

    def _submit_i2i(
        self,
        prompt: str,
        ref_oss_url: str,
        *,
        ref_strength: Optional[float] = None,
        ref_mode: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> str:
        """wanx-v1 reference-image generation (content-preserving repaint)."""
        url = f"{self.base_url}/services/aigc/text2image/image-synthesis"
        max_chars = 800
        strength = (
            self.ref_strength if ref_strength is None else max(0.0, min(1.0, float(ref_strength)))
        )
        mode = (ref_mode or self.ref_mode or "repaint").strip() or "repaint"
        input_body: dict = {
            "prompt": prompt[:max_chars],
            "ref_img": ref_oss_url,
        }
        if negative_prompt:
            input_body["negative_prompt"] = negative_prompt[:500]
        body = {
            "model": self.i2i_model,
            "input": input_body,
            "parameters": {
                "style": self.style,
                "size": self.size,
                "n": 1,
                "ref_strength": strength,
                "ref_mode": mode,
            },
        }
        headers = {
            **self._headers(oss_resolve=True),
            "X-DashScope-Async": "enable",
        }
        data = self._request("POST", url, headers=headers, body=body)
        return self._extract_task_id(data)

    def _extract_task_id(self, data: dict) -> str:
        if data.get("code") and not (data.get("output") or {}).get("task_id"):
            raise RuntimeError(
                f"DashScope submit error code={data.get('code')} "
                f"message={data.get('message')}"
            )
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(
                f"No task_id in DashScope response keys={list(data.keys())}"
            )
        return task_id

    def _poll_urls(self, task_id: str) -> list[str]:
        url = f"{self.base_url}/tasks/{task_id}"
        deadline = time.monotonic() + self.timeout_sec
        last_status = "UNKNOWN"
        while time.monotonic() < deadline:
            data = self._request("GET", url, headers=self._headers())
            output = data.get("output") or {}
            status = output.get("task_status") or data.get("task_status") or "UNKNOWN"
            last_status = status
            if status == "SUCCEEDED":
                results = output.get("results") or []
                urls = [
                    r["url"] for r in results if isinstance(r, dict) and r.get("url")
                ]
                return urls
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                raise RuntimeError(
                    f"DashScope task {task_id} status={status} "
                    f"code={output.get('code') or data.get('code')} "
                    f"message={output.get('message') or data.get('message')}"
                )
            time.sleep(self.poll_sec)
        raise RuntimeError(
            f"DashScope task {task_id} timed out after {self.timeout_sec}s "
            f"(last_status={last_status})"
        )

    def _download(self, image_url: str, path: Path) -> None:
        request = urllib.request.Request(
            image_url,
            headers={"User-Agent": "evaw-live-gen/0.2-dashscope"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=60) as resp:
            path.write_bytes(resp.read())

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        body: Optional[dict] = None,
    ) -> dict:
        raw = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=raw, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {err_body}") from e


def _encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----EVAW{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        lines.append(value.encode("utf-8"))
        lines.append(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode()
        )
        lines.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        lines.append(content)
        lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    return b"".join(lines), f"multipart/form-data; boundary={boundary}"
