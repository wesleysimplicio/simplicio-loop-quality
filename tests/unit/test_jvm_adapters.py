import unittest

from simplicio_loop_quality.jvm_adapters import normalize_jvm_report, plan_jvm_adapter


class JVMAdapterTest(unittest.TestCase):
    def test_maven_java_and_kotlin_are_detected(self):
        plan = plan_jvm_adapter(["pom.xml", "src/Main.java", "src/App.kt"])
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.languages, ("java", "kotlin"))

    def test_missing_build_system_blocks(self):
        self.assertEqual(plan_jvm_adapter(["Main.java"]).status, "BLOCKED")

    def test_report_format_is_preserved(self):
        self.assertEqual(normalize_jvm_report({"status": "PASS", "format": "junit"})["format"], "junit")


if __name__ == "__main__":
    unittest.main()
