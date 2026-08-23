from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from simplicio_loop_quality.impact_analysis import (
    ChangedFile,
    analyze_repository,
    parse_changed_files,
)


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "impact" / "polyglot"
OBSERVED_AT = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class ImpactAnalysisTest(unittest.TestCase):
    def test_polyglot_monorepo_preserves_component_boundaries_and_uses_map(self):
        result = analyze_repository(
            FIXTURE_ROOT,
            changed_files=["packages/web/src/index.ts"],
            observed_at=OBSERVED_AT,
            project_map_max_age=timedelta(days=2),
        )

        self.assertEqual(result.project_map.freshness, "fresh")
        self.assertEqual({signal.name for signal in result.profile.languages}, {"Python", "TypeScript"})
        components = {component.root for component in result.profile.components}
        self.assertIn("packages/web", components)
        self.assertIn("services/api", components)
        self.assertEqual(result.changed_files[0].component, "packages/web")
        self.assertIn("packages/web/src/helper.ts", result.dependencies["packages/web/src/index.ts"])
        self.assertIn("packages/web/src/index.ts", result.reverse_dependents["packages/web/src/helper.ts"])
        self.assertIn("public_api", {surface.kind for surface in result.risk_surfaces})

    def test_name_status_resolves_rename_delete_and_nul_delimited_input(self):
        text = "R100\tpackages/web/src/helper.ts\tpackages/web/src/new-helper.ts\nD\tservices/api/src/api/app.py\n"
        parsed = parse_changed_files(text, root=FIXTURE_ROOT)
        self.assertEqual(
            parsed,
            (
                ChangedFile("packages/web/src/new-helper.ts", "renamed", "packages/web/src/helper.ts"),
                ChangedFile("services/api/src/api/app.py", "deleted"),
            ),
        )

        nul = "R100\x00packages/web/src/helper.ts\x00packages/web/src/new-helper.ts\x00"
        self.assertEqual(parse_changed_files(nul, root=FIXTURE_ROOT)[0].old_path, "packages/web/src/helper.ts")

    def test_generated_files_are_explicitly_marked(self):
        result = analyze_repository(
            FIXTURE_ROOT,
            changed_files=["packages/web/src/api.generated.ts"],
            observed_at=OBSERVED_AT,
        )

        changed = result.changed_files[0]
        self.assertTrue(changed.generated)
        self.assertEqual(changed.generated_reason, "project-map-role")
        generated = next(surface for surface in result.risk_surfaces if surface.kind == "generated_artifacts")
        self.assertEqual(generated.paths, ("packages/web/src/api.generated.ts",))

    def test_stale_map_is_reported_and_does_not_hide_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            (root / "project-map.json").write_text(
                json.dumps(
                    {
                        "schema": "simplicio.project-map/v1",
                        "generated_at": "2020-01-01T00:00:00Z",
                        "files": [{"path": "src/main.py", "imports": [], "roles": []}],
                    }
                ),
                encoding="utf-8",
            )

            result = analyze_repository(root, changed_files=["src/main.py"], observed_at=OBSERVED_AT)

        self.assertEqual(result.project_map.freshness, "stale")
        self.assertIn("PROJECT_MAP_TOO_OLD", {item.reason_code for item in result.unknowns})
        self.assertIn("mapper_uncertainty", {surface.kind for surface in result.risk_surfaces})

    def test_missing_change_set_is_unknown_and_deterministic(self):
        first = analyze_repository(FIXTURE_ROOT, observed_at=OBSERVED_AT)
        second = analyze_repository(FIXTURE_ROOT, observed_at=OBSERVED_AT)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.changed_files, ())
        self.assertIn("CHANGED_FILES_NOT_SUPPLIED", {item.reason_code for item in first.unknowns})
        self.assertNotIn(".", first.impacted_files)

    def test_impact_set_is_monotonic_when_a_second_change_is_added(self):
        one = analyze_repository(
            FIXTURE_ROOT,
            changed_files=["packages/web/src/helper.ts"],
            observed_at=OBSERVED_AT,
        )
        two = analyze_repository(
            FIXTURE_ROOT,
            changed_files=["packages/web/src/helper.ts", "packages/web/src/index.ts"],
            observed_at=OBSERVED_AT,
        )

        self.assertTrue(set(one.impacted_files).issubset(two.impacted_files))
        self.assertTrue(
            set(one.changed_files).issubset(two.changed_files),
            "adding a changed file must not discard an existing changed-file fact",
        )


if __name__ == "__main__":
    unittest.main()
