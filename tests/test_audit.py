"""Unit tests for the hash-chained audit log (+ optional HMAC signing)."""

import json

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

    # ------------------------------------------------------------------
    # HMAC signing tests
    # ------------------------------------------------------------------

    def test_is_signed_true_when_key_provided(self):
        log = AuditLog(secret_key="test-key")
        assert log.is_signed is True

    def test_is_signed_false_by_default(self):
        log = AuditLog()
        assert log.is_signed is False

    def test_hmac_verify_passes_with_correct_key(self, tmp_path):
        path = str(tmp_path / "hmac.log")
        log = AuditLog(path, secret_key="correct-key")
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        assert log.verify() is True

    def test_hmac_verify_fails_with_wrong_key(self, tmp_path):
        path = str(tmp_path / "hmac.log")
        log = AuditLog(path, secret_key="correct-key")
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)

        wrong_log = AuditLog(path, secret_key="wrong-key")
        assert wrong_log.verify() is False

    def test_hmac_downgrade_attack_detected(self, tmp_path):
        path = tmp_path / "hmac.log"
        log = AuditLog(str(path), secret_key="correct-key")
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)

        lines = path.read_text(encoding="utf-8").splitlines()
        stripped = []
        for line in lines:
            record = json.loads(line)
            record.pop("hmac", None)
            stripped.append(json.dumps(record))
        path.write_text("\n".join(stripped) + "\n", encoding="utf-8")

        tampered = AuditLog(str(path), secret_key="correct-key")
        assert tampered.verify() is False

    def test_hmac_unsigned_entries_pass_when_no_key(self, tmp_path):
        path = str(tmp_path / "mixed.log")
        log = AuditLog(path)
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        assert log.verify() is True
