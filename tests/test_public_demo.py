from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pandas as pd

from scripts import prepare_demo_data, run_pipeline
from src.dashboard import (
    DEFAULT_PROFILE,
    PROJECT_ROOT,
    available_profiles,
    load_dashboard_data,
    load_research_engine,
    profile_metadata,
    sha256_file,
    validate_dashboard_data,
)


PUBLIC_PROFILES = ("demo_synthetic",)


def read_chunks(profile: str) -> list[dict]:
    path = PROJECT_ROOT / "data" / profile / "chunks.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


class F9PublicDataTests(unittest.TestCase):
    def test_public_profiles_are_present_and_default_is_synthetic(self) -> None:
        self.assertEqual(DEFAULT_PROFILE, "demo_synthetic")
        profiles = available_profiles(PROJECT_ROOT)
        self.assertEqual(profiles, list(PUBLIC_PROFILES))

    def test_public_profile_counts_and_schemas_are_complete(self) -> None:
        expected = {"demo_synthetic": (240, 12, 4)}
        for profile, counts in expected.items():
            with self.subTest(profile=profile):
                bundle = load_dashboard_data(
                    PROJECT_ROOT,
                    profile=profile,
                )
                observed = validate_dashboard_data(bundle)
                self.assertEqual(
                    (
                        observed["nav_rows"],
                        observed["report_count"],
                        observed["period_count"],
                    ),
                    counts,
                )
                self.assertEqual(observed["fund_count"], 3)

    def test_synthetic_profile_is_unambiguously_synthetic(self) -> None:
        metadata = profile_metadata(
            "demo_synthetic",
            PROJECT_ROOT,
        )
        self.assertFalse(metadata["contains_real_fund_data"])
        self.assertFalse(metadata["contains_complete_pdf"])
        self.assertFalse(metadata["network_required"])
        manifest = pd.read_csv(
            PROJECT_ROOT
            / "data"
            / "demo_synthetic"
            / "source_manifest.csv",
            keep_default_na=False,
        )
        self.assertTrue(
            all(
                urlparse(url).hostname == "example.invalid"
                for url in manifest["announcement_url"]
            )
        )
        self.assertTrue((manifest["file_url"] == "").all())
        self.assertTrue(
            all(
                chunk["sample_scope"] == "fully_synthetic"
                for chunk in read_chunks("demo_synthetic")
            )
        )

    def test_real_sample_is_not_distributed(self) -> None:
        self.assertFalse((PROJECT_ROOT / "data" / "sample_real").exists())

    def test_public_retrieval_indexes_validate(self) -> None:
        for profile, expected_chunks in (("demo_synthetic", 12),):
            with self.subTest(profile=profile):
                _, chunks = load_research_engine(
                    PROJECT_ROOT,
                    profile=profile,
                )
                self.assertEqual(len(chunks), expected_chunks)
                manifest_ids = set(
                    pd.read_csv(
                        PROJECT_ROOT
                        / "data"
                        / profile
                        / "source_manifest.csv"
                    )["doc_id"]
                )
                self.assertTrue(
                    all(
                        chunk["doc_id"] in manifest_ids
                        for chunk in chunks
                    )
                )

    def test_public_profiles_load_without_private_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for profile in PUBLIC_PROFILES:
                target = root / "data" / profile
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    PROJECT_ROOT / "data" / profile,
                    target,
                )
            for profile in PUBLIC_PROFILES:
                with self.subTest(profile=profile):
                    bundle = load_dashboard_data(
                        root,
                        profile=profile,
                    )
                    self.assertEqual(
                        validate_dashboard_data(bundle)["fund_count"],
                        3,
                    )
                    _, chunks = load_research_engine(
                        root,
                        profile=profile,
                    )
                    self.assertGreater(len(chunks), 0)


class F9OfflinePipelineTests(unittest.TestCase):
    def test_synthetic_generator_is_deterministic(self) -> None:
        profile_dir = PROJECT_ROOT / "data" / "demo_synthetic"
        before = {
            path.name: sha256_file(path)
            for path in sorted(profile_dir.iterdir())
            if path.is_file()
        }
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare_demo_data.main([]), 0)
        after = {
            path.name: sha256_file(path)
            for path in sorted(profile_dir.iterdir())
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_synthetic_generator_needs_no_network_or_api_key(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                socket,
                "socket",
                side_effect=AssertionError("network access attempted"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(prepare_demo_data.main([]), 0)

    def test_public_pipeline_needs_no_network_or_api_key(self) -> None:
        output = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                socket,
                "socket",
                side_effect=AssertionError("network access attempted"),
            ),
            contextlib.redirect_stdout(output),
        ):
            for profile in PUBLIC_PROFILES:
                self.assertEqual(
                    run_pipeline.main(["--profile", profile]),
                    0,
                )
        rendered = output.getvalue()
        self.assertEqual(rendered.count("network_calls=0"), 1)
        self.assertEqual(rendered.count("api_keys_required=0"), 1)

    def test_private_holdout_artifact_is_not_distributed(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "results" / "f7_holdout_lock.json").exists()
        )

    @unittest.skipUnless(
        importlib.util.find_spec("streamlit") is not None,
        "Streamlit runtime is not installed",
    )
    def test_streamlit_defaults_to_synthetic_profile(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(PROJECT_ROOT / "app.py"),
            default_timeout=30,
        ).run()
        self.assertFalse(app.exception)
        profile_selectors = [
            selector
            for selector in app.selectbox
            if selector.label == "数据模式"
        ]
        self.assertEqual(len(profile_selectors), 1)
        self.assertEqual(
            profile_selectors[0].value,
            "demo_synthetic",
        )


class F9AuditTests(unittest.TestCase):
    def test_pass_audit_matches_current_files_when_available(self) -> None:
        audit_path = PROJECT_ROOT / "results" / "f9_audit.json"
        manifest_path = (
            PROJECT_ROOT / "results" / "f9_run_manifest.json"
        )
        if not audit_path.exists() or not manifest_path.exists():
            self.skipTest("F9 audit has not been generated")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("status") != "PASS":
            self.skipTest("F9 audit is not yet passing")
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "PASS")
        self.assertEqual(
            manifest["outputs"]["results/f9_audit.json"]["sha256"],
            sha256_file(audit_path),
        )
        self.assertFalse(manifest["holdout_rerun_performed"])
        self.assertFalse(manifest["deployment_performed"])
        for relative_path, expected in audit["code_sha256"].items():
            self.assertEqual(
                sha256_file(PROJECT_ROOT / relative_path),
                expected,
            )
        for relative_path, expected in audit[
            "public_data_sha256"
        ].items():
            self.assertEqual(
                sha256_file(PROJECT_ROOT / relative_path),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
