import unittest

from simplicio_loop_quality.documentation_quality import (
    normalize_documentation,
    plan_documentation,
)


class DocumentationQualityTest(unittest.TestCase):
    def test_complete_documentation_plan(self):
        documents = {name: "present" for name in ("overview", "quickstart", "api", "examples", "troubleshooting")}
        self.assertEqual(plan_documentation(documents)["status"], "PLANNED")

    def test_missing_sections_block(self):
        self.assertEqual(plan_documentation({})["status"], "BLOCKED")

    def test_broken_link_fails(self):
        result = normalize_documentation([{"kind": "broken_link", "location": "README.md"}])
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
