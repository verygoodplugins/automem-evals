"""Protocol correctness tests; synthetic records here are tests, never scored cases."""
import unittest
import json
import subprocess
from http.client import HTTPConnection, RemoteDisconnected
from tempfile import TemporaryDirectory
from threading import Thread
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from runners.precisionmembench.protocol import NoRedirect, Protocol, create_server, local_url, prepare


class ProtocolTests(unittest.TestCase):
    def make(self, beliefs=()):
        protocol = Protocol("http://127.0.0.1:8091", "test-token", beliefs, Path("unused"))
        protocol.call = Mock()
        protocol.wait = Mock()
        return protocol

    def test_local_boundary_and_redirects(self):
        for url in ["https://localhost", "http://example.com", "http://localhost@evil.com",
                    "http://localhost/path", "http://localhost?redirect=evil"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_url(url)
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_indexing_readiness_and_timeout(self):
        protocol = self.make()
        protocol.call.return_value = {"memory_count": 0, "vector_count": 0}
        self.assertEqual(Protocol.wait(protocol), {"ok": True})
        protocol.call.return_value = {"memory_count": 1, "vector_count": 0}
        with patch("runners.precisionmembench.protocol.time.monotonic", side_effect=[0, 121]):
            with self.assertRaises(TimeoutError):
                Protocol.wait(protocol)

    def test_scope_user_and_noise_ids(self):
        protocol = self.make()
        protocol.reverse = {"uuid-good": "target", "uuid-noise": "noise"}
        protocol.call.return_value = {"results": [{"id": "uuid-good"}, {"memory": {"id": "uuid-noise"}}]}
        result = protocol.search({"query": "alias", "user_id": "alice", "scope": "code", "limit": 7})
        self.assertEqual(result["results"], [{"id": "target"}, {"id": "noise"}])
        query = parse_qs(urlsplit(protocol.call.call_args.args[1]).query)
        self.assertEqual(query["tags"], [protocol.run_tag, protocol.tag("alice"), protocol.tag("alice", "code")])
        self.assertNotEqual(protocol.tag("alice", "code"), protocol.tag("bob", "code"))
        self.assertEqual(query["current_only"], ["true"])
        self.assertEqual(query["tag_match"], ["exact"])
        protocol.reverse.clear()
        with self.assertRaises(KeyError):
            protocol.search({"query": "alias", "user_id": "alice"})

    def test_lifecycle_direction_update_and_owned_reset(self):
        protocol = self.make([{"_id": "old", "superseded_by": "new"},
                              {"_id": "new", "created_at": "2026-10-01T00:00:00Z"}])
        protocol.call.side_effect = [{"memory_id": "old-uuid"}, {"memory_id": "new-uuid"},
                                     {}, {}, {"memory": {"t_invalid": "2026-10-01"}}, {}, {}, {}]
        old = {"metadata": {"beliefId": "old", "scope": "code"}, "user_id": "alice", "text": "old"}
        new = {**old, "metadata": {"beliefId": "new", "scope": "code"}, "text": "new"}
        protocol.add(old)
        protocol.add(new)
        edge = protocol.call.call_args_list[2].args[2]
        self.assertEqual(edge, {"memory1_id": "old-uuid", "memory2_id": "new-uuid",
                                "type": "INVALIDATED_BY", "strength": 1.0})
        protocol.add({**new, "text": "new aliases"}, update=True)
        self.assertEqual(protocol.call.call_args.args, ("PATCH", "/memory/new-uuid", {"content": "new aliases"}))
        protocol.reset()
        self.assertEqual([c.args[1] for c in protocol.call.call_args_list[-2:]],
                         ["/memory/old-uuid", "/memory/new-uuid"])
        self.assertEqual(protocol.ids, {})


    def test_preparation_rejects_changed_official_assertions_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "providers.config.json").write_text('{"existing": {}}\n')
            session = root / "src/session-retrieval.external.eval.test.ts"
            session.write_text("          adapter.updateBeliefAliases(\n")
            runner = root / "src/retrieval.external.eval.test.ts"
            runner.write_text("official assertion\n")

            def git(*args):
                return subprocess.check_output(["git", "-C", directory, *args],
                                               text=True, stderr=subprocess.DEVNULL)

            git("init", "--quiet")
            git("add", ".")
            git("-c", "user.name=Protocol Test", "-c", "user.email=protocol-test@example.invalid",
                "commit", "--quiet", "-m", "fixture")
            revision = git("rev-parse", "HEAD").strip()
            with patch("runners.precisionmembench.protocol.REVISION", revision):
                prepare(root, 18099)
                prepare(root, 18099)
                self.assertIn("await adapter.updateBeliefAliases", session.read_text())
                runner.write_text("modified assertion\n")
                with self.assertRaises(subprocess.CalledProcessError):
                    prepare(root, 18099)
                runner.write_text("official assertion\n")
                session.write_text("modified session assertion\n")
                with self.assertRaises(ValueError):
                    prepare(root, 18099)

    def test_bridge_errors_disconnect_and_stop_instead_of_scoring_empty_hits(self):
        for route, method in [("/search", "search"), ("/add", "add"), ("/wait", "wait")]:
            with self.subTest(route=route), TemporaryDirectory() as directory:
                protocol = self.make()
                protocol.trace = Path(directory) / "trace.jsonl"
                setattr(protocol, method, Mock(side_effect=TimeoutError("backend unavailable")))
                server = create_server(protocol, 0)
                failures = []

                def serve():
                    try:
                        server.serve_forever(poll_interval=0.01)
                    except RuntimeError as exc:
                        failures.append(str(exc))
                    finally:
                        server.server_close()

                thread = Thread(target=serve, daemon=True)
                thread.start()
                connection = HTTPConnection(*server.server_address, timeout=2)
                try:
                    connection.request("POST", route, body="{}")
                    with self.assertRaises(RemoteDisconnected):
                        connection.getresponse()
                finally:
                    connection.close()
                    thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(failures, ["Protocol failure invalidates this benchmark run"])
                self.assertEqual(json.loads(protocol.trace.read_text()),
                                 {"error": "backend unavailable", "route": route})


if __name__ == "__main__":
    unittest.main()
