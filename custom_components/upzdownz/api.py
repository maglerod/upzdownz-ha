"""API client for UpzDownz metric-ingest Edge Function."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class UpzDownzApiError(Exception):
    """General API error."""


class UpzDownzAuthError(UpzDownzApiError):
    """Authentication error (401)."""


class UpzDownzRateLimitError(UpzDownzApiError):
    """Rate/row limit reached (429)."""


class UpzDownzApiClient:
    """Async client for the UpzDownz metric-ingest API."""

    BASE_URL = API_BASE_URL

    def __init__(self, api_key: str, session: aiohttp.ClientSession) -> None:
        self._api_key = api_key
        self._session = session

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request and return parsed JSON."""
        url = f"{self.BASE_URL}{path}"
        _LOGGER.debug("UpzDownz: %s %s", method, url)
        try:
            async with self._session.request(
                method, url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15), **kwargs
            ) as resp:
                _LOGGER.debug("UpzDownz: response status %s from %s", resp.status, url)
                if resp.status == 401:
                    text = await resp.text()
                    _LOGGER.error("UpzDownz: 401 Unauthorized — check your API key. Response: %s", text)
                    raise UpzDownzAuthError("Invalid API key")
                if resp.status == 429:
                    text = await resp.text()
                    _LOGGER.warning("UpzDownz: 429 Row limit reached. Response: %s", text)
                    raise UpzDownzRateLimitError("Row limit reached")
                if resp.status >= 500:
                    text = await resp.text()
                    _LOGGER.error("UpzDownz: server error %s. Response: %s", resp.status, text)
                    raise UpzDownzApiError(f"Server error {resp.status}: {text}")
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.error("UpzDownz: client error %s from %s. Response: %s", resp.status, url, text)
                    raise UpzDownzApiError(f"Client error {resp.status}: {text}")
                body = await resp.text()
                _LOGGER.debug("UpzDownz: response body: %s", body[:500])
                import json
                return json.loads(body) if body.strip() else {}
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("UpzDownz: connection error to %s — %s", url, err)
            raise UpzDownzApiError(f"Connection error: {err}") from err
        except aiohttp.ClientResponseError as err:
            _LOGGER.error("UpzDownz: response error from %s — %s", url, err)
            raise UpzDownzApiError(f"Response error: {err}") from err
        except aiohttp.ServerTimeoutError as err:
            _LOGGER.error("UpzDownz: timeout connecting to %s — %s", url, err)
            raise UpzDownzApiError(f"Timeout: {err}") from err
        except Exception as err:
            _LOGGER.error("UpzDownz: unexpected error calling %s — %s (%s)", url, err, type(err).__name__)
            raise UpzDownzApiError(f"Unexpected error: {err}") from err

    async def validate_key(self) -> bool:
        """Validate the API key by calling GET /. Returns True if valid."""
        try:
            _LOGGER.debug("UpzDownz: validating API key against %s", self.BASE_URL)
            await self._request("GET", "/")
            _LOGGER.info("UpzDownz: API key validated successfully")
            return True
        except UpzDownzAuthError:
            return False

    async def list_sources(self) -> list[dict]:
        """List all data sources for this dashboard."""
        data = await self._request("GET", "/")
        return data.get("sources", [])

    async def get_source(self, source_id: str) -> dict:
        """Get a specific data source by ID."""
        return await self._request("GET", f"/sources/{source_id}")

    async def create_source(self, name: str, schema: list[dict]) -> dict:
        """Create a new data source. Returns the created source dict."""
        payload = {"name": name, "schema": schema}
        data = await self._request("POST", "/sources", json=payload)
        return data.get("source", data)

    async def update_source(self, source_id: str, name: str | None = None, schema: list[dict] | None = None) -> dict:
        """Update an existing data source."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if schema is not None:
            payload["schema"] = schema
        return await self._request("PUT", f"/sources/{source_id}", json=payload)

    async def push_data(self, source_id: str, rows: list[dict]) -> dict:
        """Push one or more rows to a data source. Max 1000 rows per call."""
        if not rows:
            return {}
        results = {}
        for i in range(0, len(rows), 1000):
            batch = rows[i : i + 1000]
            payload = batch if len(batch) > 1 else batch[0]
            results = await self._request("POST", f"/sources/{source_id}/data", json=payload)
        return results

    async def clear_source_data(self, source_id: str) -> dict:
        """Delete all data rows from a source (keeps the source itself)."""
        return await self._request("DELETE", f"/sources/{source_id}/data")
