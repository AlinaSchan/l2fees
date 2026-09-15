"""a tiny json-rpc client over urllib for one chain: fallback across its public endpoints."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

USER_AGENT = "l2fees/0.1 (+https://github.com/alinaschanz/l2fees)"


class RpcError(Exception):
    """the call itself failed (revert, unknown method, bad params) - the same answer would come from every node."""


class RpcUnavailable(Exception):
    """no endpoint gave a usable answer."""


class Rpc:
    def __init__(self, urls: tuple[str, ...] | list[str], timeout: float = 25.0):
        self.urls = list(urls)
        self.timeout = timeout

    def _post(self, url: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def call(self, method: str, params: list):
        """one call; an endpoint that is down, rate-limited or broken is skipped, a real error
        (a revert, a method the chain does not have) comes back as RpcError from the first endpoint that says so."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        last_problem: str | None = None
        for url in list(self.urls):
            try:
                body = self._post(url, payload)
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                last_problem = f"{url}: {exc}"
                continue
            if not isinstance(body, dict):
                last_problem = f"{url}: not a json-rpc answer"
                continue
            error = body.get("error")
            if error:
                message = str(error.get("message", error)) if isinstance(error, dict) else str(error)
                code = error.get("code") if isinstance(error, dict) else None
                if code in (3, -32601, -32602) or "revert" in message.lower() or "not supported" in message.lower():
                    raise RpcError(message)
                last_problem = f"{url}: {message}"
                continue
            if url != self.urls[0]:
                self.urls.remove(url)
                self.urls.insert(0, url)
            return body.get("result")
        raise RpcUnavailable(f"no rpc endpoint gave a usable answer ({last_problem})")

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)

    def eth_call(self, to: str, data: str) -> bytes:
        return bytes.fromhex((self.call("eth_call", [{"from": None, "to": to, "data": data}, "latest"]) or "0x")[2:])
