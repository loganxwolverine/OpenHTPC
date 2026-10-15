"""Coverage guard for the canonical Flex source definition.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.

Scope: tools/openhtpc-devctl :: _flex_source_files, against the versioned content
of vendor/flex-launcher.

The Flex source fingerprint must be reproducible from the versioned sources
alone.  The canonical definition therefore names the source roots explicitly
(FLEX_SOURCE_ROOTS / FLEX_SOURCE_ROOT_FILES).  A source directory committed
under vendor/flex-launcher without updating those constants would silently stop
being covered by the fingerprint: the invariant would keep holding on paper
while a real source change would no longer invalidate the recorded value.  This
guard turns that silent omission into a red test and forces an explicit
decision.

Git is used by this test only, as a development-checkout consistency check.
The fingerprint function and the official build chain (which computes the
fingerprint on a `git archive` export) never depend on .git.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLEX_SOURCE = ROOT / "vendor/flex-launcher"
DEVCTL = ROOT / "tools/openhtpc-devctl"


def _load_devctl():
    loader = importlib.machinery.SourceFileLoader("flex_source_contract_devctl", str(DEVCTL))
    spec = importlib.util.spec_from_loader("flex_source_contract_devctl", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FlexSourceContract(unittest.TestCase):
    """The canonical definition covers exactly the versioned Flex sources."""

    def versioned_sources(self) -> set[str]:
        """Files tracked by Git under vendor/flex-launcher.

        `-c safe.directory` is set on the invocation so the guard states its own
        precondition: project tests run with a hermetic HOME, which hides the
        account-level safe.directory and would otherwise make git refuse the
        checkout for reasons unrelated to this contract.
        """
        result = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT}", "ls-files", "--", "vendor/flex-launcher"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        prefix = "vendor/flex-launcher/"
        return {line[len(prefix):] for line in result.stdout.splitlines() if line.startswith(prefix)}

    def canonical_selection(self) -> set[str]:
        devctl = _load_devctl()
        return {
            path.relative_to(FLEX_SOURCE).as_posix()
            for path in devctl._flex_source_files(FLEX_SOURCE)
        }

    def test_canonical_definition_covers_exactly_versioned_sources(self):
        versioned = self.versioned_sources()
        selected = self.canonical_selection()
        self.assertTrue(versioned, "no versioned Flex source found")
        self.assertEqual(
            sorted(selected - versioned), [],
            "the canonical definition keeps files that are not versioned",
        )
        self.assertEqual(
            sorted(versioned - selected), [],
            "versioned sources escape FLEX_SOURCE_ROOTS / FLEX_SOURCE_ROOT_FILES",
        )
