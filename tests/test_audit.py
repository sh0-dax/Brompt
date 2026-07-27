"""Unit tests for the hash-chained audit log."""

from brompt.audit import AuditLog


class TestAuditLog:
    def test_record_and_read(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        log.record("execute", "s1", True)
        entries = log.read_all()
        assert len(entries) == 1
        assert entries[0]["event"] == "execute"

    def test_chain_links_entries(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        entries = log.read_all()
        assert entries[1]["prev_hash"] == entries[0]["entry_hash"]

    def test_verify_passes_on_untampered_log(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        for i in range(5):
            log.record("execute", f"s{i}", True)
        assert log.verify() is True

    def test_verify_fails_on_tampered_log(self, tmp_path):
        import json

        path = tmp_path / "a.log"
        log = AuditLog(str(path))
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)

        lines = path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["state_id"] = "tampered"
        lines[0] = json.dumps(first)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert log.verify() is False

    def test_verify_empty_log(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        assert log.verify() is True
