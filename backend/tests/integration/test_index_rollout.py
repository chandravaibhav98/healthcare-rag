"""Index versions under image-based rollouts (Phase 9, ADR-0008).

On Kubernetes each index ships as an image and an init container copies it to the
same boot path in every pod. So during a rolling update (or a `kubectl rollout undo`)
the database can name an active version whose files exist only in *other* pods.
These tests pin the behaviour: the deployed index wins at start-up, an old pod never
tries to "follow" a version it does not have, and activating such a version is a 409.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from app.api.routes.admin import PREFIX
from app.rag.index.registry import IndexRegistry
from app.rag.ingestion.chunker import ChunkingConfig
from app.rag.pipeline import BuildConfig, build_index
from app.rag.runtime import build_runtime
from app.repositories import index_versions as version_repo
from app.services.index_service import IndexService
from tests.conftest import FIXTURE_CORPUS
from tests.support import AuthedClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def candidate_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A second, valid index of the fixture corpus (different chunking → new version)."""
    out = tmp_path_factory.mktemp("candidate") / "index"
    build_index(
        FIXTURE_CORPUS, out, BuildConfig(chunking=ChunkingConfig(min_tokens=40, max_tokens=80))
    )
    return out


def _version(path: Path) -> str:
    from app.rag.index.manifest import read_manifest

    return str(read_manifest(path)["index_version"])


def _pod(api: AuthedClient, boot_dir: Path) -> IndexService:
    """A fresh 'pod': its own registry loaded from `boot_dir`, sharing the database."""
    settings = api.app.state.settings
    registry = IndexRegistry(lambda index: build_runtime(index, settings))
    registry.load(boot_dir)
    return IndexService(
        registry,
        boot_dir=boot_dir,
        store_dir=boot_dir.parent / "no-store",
        corpus_dir=FIXTURE_CORPUS,
        build=lambda corpus, out: None,
    )


def _active(api: AuthedClient) -> Any:
    async def read() -> Any:
        async with api.db.session() as s:
            return await version_repo.active(s)

    return api.run(read)


def test_a_rollout_makes_the_deployed_index_active_and_is_audited(
    api: AuthedClient, candidate_index: Path, tmp_path: Path
) -> None:
    boot = tmp_path / "index"
    old = api.app.state.index_service._boot_dir  # the fixture index, active in the DB
    shutil.copytree(old, boot)
    old_version = _version(boot)

    async def register(pod: IndexService) -> None:
        async with api.db.session() as s:
            await pod.register_known(s)

    api.run(register, _pod(api, boot))  # an old pod registers its boot path
    assert _active(api).version == old_version

    # The new image's init container replaces the files at the same boot path.
    shutil.rmtree(boot)
    shutil.copytree(candidate_index, boot)
    new_version = _version(boot)
    assert new_version != old_version
    api.run(register, _pod(api, boot))

    assert _active(api).version == new_version
    log = api.get(f"{PREFIX}/audit-log", params={"action": "index.activate"}).json()["items"]
    assert any(e["details"].get("reason") == "deployment" for e in log)


def test_an_old_pod_keeps_serving_during_a_rolling_update(
    api: AuthedClient, candidate_index: Path, tmp_path: Path
) -> None:
    serving = api.client.get("/version").json()["index_version"]
    elsewhere = tmp_path / "other-pod" / "index"
    shutil.copytree(candidate_index, elsewhere)
    candidate = _version(elsewhere)

    async def activate_in_new_pods() -> None:
        # The new pods registered the candidate at a path that, in THIS pod, still holds
        # the old index (same boot path, different image).
        async with api.db.session() as s:
            await version_repo.register(
                s,
                version=candidate,
                path=str(api.app.state.index_service._boot_dir),
                manifest={"index_version": candidate},
                source="boot",
            )
            await version_repo.set_active(s, candidate)
            await s.commit()

    api.run(activate_in_new_pods)

    async def poll() -> bool:
        async with api.db.session() as s:
            switched: bool = await api.app.state.index_service.sync_active(s)
            return switched

    assert api.run(poll) is False, "an old pod must not reload a version it does not have"
    assert api.run(poll) is False
    assert api.client.get("/version").json()["index_version"] == serving
    assert (
        api.ask("How long should hand hygiene with alcohol-based handrub take?").status_code == 200
    )

    # Activating it from this pod is refused with a clear 409, not a silent mismatch.
    resp = api.post(f"{PREFIX}/index/versions/{candidate}/activate")
    assert resp.status_code == 409
    assert "not available in this deployment" in resp.json()["detail"]
