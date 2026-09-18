"""Tests that talk to ENA. Deselected by default; run with ``-m integration``.

Two kinds, both marked ``integration``:

* **public** — the API definitions and one released record. No credentials.
* **authenticated** — one small request per report, against ``wwwdev``.
  Skipped unless Webin credentials are configured (environment or ``.env``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from ena_api import WebinClient, WebinConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_models as gen  # noqa: E402

pytestmark = pytest.mark.integration


def _test_credentials() -> WebinConfig | None:
    """The configured credentials, forced at ``wwwdev``, or ``None``."""
    try:
        config = WebinConfig()  # type: ignore[call-arg]  # values come from the environment or .env
    except Exception:
        return None
    return config.model_copy(update={"test": True})


_CREDENTIALS = _test_credentials()
_needs_credentials = pytest.mark.skipif(_CREDENTIALS is None, reason="no ENA_WEBIN credentials")

#: A long-released public study — the Browser API serves it without credentials.
_PUBLIC_ACCESSION = "PRJEB1787"


@pytest.fixture(scope="module")
def live_specs() -> dict[str, dict[str, Any]]:
    """ENA's three OpenAPI definitions, fetched once."""
    return {api: httpx.get(url, timeout=gen.TIMEOUT, follow_redirects=True).json() for api, url in gen.API_DOCS.items()}


@pytest.mark.parametrize(
    ("name", "api", "method", "path", "params"), gen.OPERATIONS, ids=[op[0] for op in gen.OPERATIONS]
)
def test_operation_still_exists(
    live_specs: dict[str, dict[str, Any]], name: str, api: str, method: str, path: str, params: tuple[str, ...]
) -> None:
    """Every allow-listed operation, and the parameters the proxies pass, are still served."""
    operation = live_specs[api].get("paths", {}).get(path, {}).get(method.lower())
    assert operation is not None, f"{api}: {method} {path} is gone"
    live = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
    assert set(params) <= live, f"{api}: {method} {path} no longer takes {sorted(set(params) - live)}"


def test_receipt_xsd_still_covers_the_generated_tags() -> None:
    """The committed receipt tags still match the XSD ENA publishes."""
    xsd = httpx.get(gen.RECEIPT_XSD_URL, timeout=gen.TIMEOUT, follow_redirects=True).text
    from ena_api.models import RECEIPT_ENTITY_TAGS

    assert gen.receipt_entity_tags(xsd) == RECEIPT_ENTITY_TAGS


def test_browser_xml_of_a_public_record() -> None:
    """The Browser API serves a released record without credentials."""
    with WebinClient(config=WebinConfig(webin_id="anonymous", password="anonymous", test=False)) as client:
        xml = client.browser.xml(_PUBLIC_ACCESSION)
    assert xml.lstrip().startswith(b"<")
    assert _PUBLIC_ACCESSION.encode() in xml


@pytest.fixture
def test_client() -> Iterator[WebinClient]:
    """A client pointed at ``wwwdev`` with the configured credentials."""
    with WebinClient(config=_CREDENTIALS) as client:
        yield client


@_needs_credentials
@pytest.mark.parametrize(
    ("method", "entity"),
    [
        ("list_projects", "projects"),
        ("list_samples", "samples"),
        ("list_runs", "runs"),
        ("list_experiments", "experiments"),
        ("list_analyses", "analyses"),
        ("list_run_processes", "run-process"),
        ("list_files", "run-files"),
    ],
)
def test_list_method_against_wwwdev(test_client: WebinClient, method: str, entity: str) -> None:
    """Each list method reaches a real endpoint and parses what comes back.

    An empty list is a pass: the test account need not own records of every
    kind. A wrong URL is not — ``_fetch`` turns a 404 into ``[]``, so the
    status code is asserted separately. That is exactly how ``list_files``
    calling the non-existent ``/report/files`` stayed invisible.
    """
    response = test_client._http.get(
        f"{test_client.config.reports_url}/{entity}", params={"format": "json", "max-results": 1}
    )
    assert response.status_code == 200, f"/{entity} answered {response.status_code}"
    assert isinstance(json.loads(response.text), list)

    records = getattr(test_client.reports, method)(max_results=1)
    assert isinstance(records, list)
