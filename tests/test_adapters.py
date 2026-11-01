"""Contract tests for the real plugin registration and HTTP adapter."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file, package=False):
    spec = importlib.util.spec_from_file_location(name, file, submodule_search_locations=[str(ROOT)] if package else None)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RegistrationTests(unittest.TestCase):
    def test_tools_and_skill_register_and_dispatch(self):
        plugin = load("github_projects_test_plugin", ROOT / "__init__.py", True)
        tools = {}
        skills = {}

        class Context:
            def register_tool(self, **kwargs):
                tools[kwargs["name"]] = kwargs

            def register_skill(self, name, path):
                skills[name] = path

        plugin.register(Context())
        self.assertEqual(len(tools), 8)
        self.assertTrue(skills["github-projects"].is_file())
        with patch.object(plugin, "execute", return_value={"projects": []}) as execute:
            result = json.loads(tools["github_projects_list"]["handler"]({"owner": "example"}))
            self.assertTrue(result["ok"])
            execute.assert_called_once_with("projects", {"owner": "example"})
        with patch.object(plugin, "execute", side_effect=plugin.GitHubError("denied")):
            result = json.loads(tools["github_projects_list"]["handler"]({"owner": "example"}))
            self.assertEqual(result, {"ok": False, "error": "denied"})
        for tool in tools.values():
            params = tool["schema"]["parameters"]
            self.assertFalse(params["additionalProperties"])
            self.assertTrue(set(params["required"]) <= set(params["properties"]))


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI = None


@unittest.skipIf(FastAPI is None, "HTTP adapter tests require Hermes runtime (FastAPI and HTTPX)")
class AdapterTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        self.api = load("github_projects_test_api", ROOT / "dashboard" / "plugin_api.py")
        app = FastAPI()
        app.include_router(self.api.router, prefix="/api/plugins/github-projects")
        self.client = TestClient(app)

    def test_success_uses_shared_service(self):
        with patch.object(self.api._service, "execute", return_value={"projects": []}) as execute:
            response = self.client.post("/api/plugins/github-projects/call", json={"operation": "projects", "arguments": {"owner": "example"}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True, "data": {"projects": []}})
            execute.assert_called_once_with("projects", {"owner": "example"})

    def test_domain_errors_are_visible_and_unexpected_errors_are_redacted(self):
        for error, expected in [(self.api._service.GitHubError("Missing project scope"), "Missing project scope"), (RuntimeError("private-path-or-secret"), "Unexpected plugin failure. Refresh GitHub before retrying any write.")]:
            with self.subTest(error=type(error).__name__), patch.object(self.api._service, "execute", side_effect=error):
                response = self.client.post("/api/plugins/github-projects/call", json={"operation": "board", "arguments": {}})
                self.assertEqual(response.json(), {"ok": False, "error": expected})

    def test_bad_envelope_rejected(self):
        for payload in [{"operation": ""}, {"operation": "board", "arguments": []}, {"operation": "board", "extra": True}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/plugins/github-projects/call", json=payload).status_code, 422)


if __name__ == "__main__":
    unittest.main()
