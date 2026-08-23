import unittest

from simplicio_loop_quality.generic_profile import onboarding_profile, validate_profile


class GenericProfileTest(unittest.TestCase):
    def test_unknown_toolchain_profile_is_declarative(self):
        profile = onboarding_profile(commands=[{"id": "lint", "lane": "static", "command": ["custom-lint", "--json"], "parser": "json", "artifacts": ["reports/lint.json"]}])
        self.assertEqual(validate_profile(profile).status, "PASS")

    def test_unsafe_artifact_and_env_are_blocked(self):
        result = validate_profile({"commands": [{"command": ["tool"], "artifacts": ["../secret"], "env_allowlist": ["BAD-NAME"]}]})
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("COMMAND_0_ARTIFACT_PATH_UNSAFE", result.findings)

    def test_container_requires_an_image(self):
        self.assertEqual(validate_profile({"commands": [{"command": ["tool"]}], "container": {}}).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
