"""Unit tests for the hash-chained audit log (+ optional HMAC signing)."""

import json

import pytest

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

    # ------------------------------------------------------------------
    # verify_report() — detailed, locatable failure reports
    # ------------------------------------------------------------------

    def test_verify_report_valid_log(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        for i in range(3):
            log.record("execute", f"s{i}", True)
        report = log.verify_report()
        assert report["ok"] is True
        assert report["reason"] == "valid"
        assert report["entries"] == 3
        assert report["line"] is None

    def test_verify_report_empty_log(self, tmp_path):
        log = AuditLog(str(tmp_path / "a.log"))
        report = log.verify_report()
        assert report["ok"] is True
        assert report["reason"] == "empty"

    def test_verify_report_chain_break(self, tmp_path):
        path = tmp_path / "a.log"
        log = AuditLog(str(path))
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[1])
        rec["prev_hash"] = "0" * 64
        lines[1] = json.dumps(rec)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = AuditLog(str(path)).verify_report()
        assert report["ok"] is False
        assert report["reason"] == "chain_break"
        assert report["line"] == 2
        assert report["expected_prev_hash"] == json.loads(lines[0])["entry_hash"]
        assert report["found_prev_hash"] == "0" * 64

    def test_verify_report_hash_mismatch(self, tmp_path):
        path = tmp_path / "a.log"
        log = AuditLog(str(path))
        log.record("execute", "s1", True)
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["detail"] = "tampered"
        lines[0] = json.dumps(rec)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = AuditLog(str(path)).verify_report()
        assert report["ok"] is False
        assert report["reason"] == "hash_mismatch"
        assert report["line"] == 1

    def test_verify_report_invalid_json(self, tmp_path):
        path = tmp_path / "a.log"
        log = AuditLog(str(path))
        log.record("execute", "s1", True)
        path.write_text(path.read_text(encoding="utf-8") + '{"broken"\n', encoding="utf-8")

        report = AuditLog(str(path)).verify_report()
        assert report["ok"] is False
        assert report["reason"] == "invalid_json"

    def test_verify_report_detects_hmac_mismatch(self, tmp_path):
        path = tmp_path / "hmac.log"
        log = AuditLog(str(path), secret_key="correct")
        log.record("execute", "s1", True)
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["hmac"] = "0" * 64
        lines[0] = json.dumps(rec)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = AuditLog(str(path), secret_key="correct").verify_report()
        assert report["ok"] is False
        assert report["reason"] == "hmac_mismatch"
        assert report["line"] == 1

    # ------------------------------------------------------------------
    # Concurrent-write robustness (no cross-process lock / O_APPEND path)
    # ------------------------------------------------------------------

    def test_oappend_fallback_append(self, tmp_path, monkeypatch):
        import brompt.audit as audit_module
        monkeypatch.setattr(audit_module, "_PORTALOCKER_AVAILABLE", False)
        log = audit_module.AuditLog(str(tmp_path / "o.log"))
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        assert log.verify() is True
        assert len(log.read_all()) == 2

    def test_read_all_skips_partial_trailing_line(self, tmp_path):
        path = tmp_path / "a.log"
        log = AuditLog(str(path))
        log.record("execute", "s1", True)
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"entry_hash": "abc')  # simulate writer mid-append
        entries = log.read_all()
        assert len(entries) == 1
        assert log._last_hash() == entries[0]["entry_hash"]

    # ------------------------------------------------------------------
    # Ed25519 asymmetric signing
    # ------------------------------------------------------------------

    def test_ed25519_records_signature_and_pubkey(self, tmp_path):
        log = AuditLog(str(tmp_path / "ed.log"), signing_key="seed")
        log.record("execute", "s1", True)
        entry = log.read_all()[0]
        assert log.is_ed25519 is True
        assert entry["signature"]
        assert entry["pubkey_id"] == log.pubkey_id

    def test_ed25519_verify_passes(self, tmp_path):
        log = AuditLog(str(tmp_path / "ed.log"), signing_key="seed")
        log.record("execute", "s1", True)
        log.record("execute", "s2", True)
        assert log.verify() is True

    def test_ed25519_verify_fails_on_tampered_signature(self, tmp_path):
        path = tmp_path / "ed.log"
        log = AuditLog(str(path), signing_key="seed")
        log.record("execute", "s1", True)
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["signature"] = "0" * 128
        lines[0] = json.dumps(rec)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert AuditLog(str(path), signing_key="seed").verify() is False
        report = AuditLog(str(path), signing_key="seed").verify_report()
        assert report["ok"] is False
        assert report["reason"] == "signature_mismatch"
        assert report["line"] == 1

    def test_ed25519_downgrade_detected(self, tmp_path):
        path = tmp_path / "ed.log"
        log = AuditLog(str(path), signing_key="seed")
        log.record("execute", "s1", True)
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec.pop("signature", None)
        rec.pop("pubkey_id", None)
        lines[0] = json.dumps(rec)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert AuditLog(str(path), signing_key="seed").verify() is False
        assert AuditLog(str(path), signing_key="seed").verify_report()["reason"] == "missing_signature"

    def test_ed25519_verify_entry(self, tmp_path):
        log = AuditLog(str(tmp_path / "ed.log"), signing_key="seed")
        entry = log.record("execute", "s1", True)
        assert log.verify_entry(entry["entry_hash"]) is True

    def test_ed25519_requires_cryptography(self, tmp_path, monkeypatch):
        import brompt.audit as audit_module
        monkeypatch.setattr(audit_module, "_CRYPTO_AVAILABLE", False)
        with pytest.raises(ImportError):
            audit_module.AuditLog(str(tmp_path / "x.log"), signing_key="seed")

    # ------------------------------------------------------------------
    # Replay determinism
    # ------------------------------------------------------------------

    def test_replay_runs_exact_stored_messages(self, tmp_path):
        log = AuditLog(str(tmp_path / "r.log"))
        msgs = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        log.record("execute", "s1", True, messages=msgs)
        entry_hash = log.read_all()[0]["entry_hash"]

        captured = {}

        def fn(messages, system=None):
            captured["messages"] = messages
            captured["system"] = system
            return "4"

        result = log.replay(entry_hash, fn=fn)
        assert captured["messages"] == msgs
        assert result["replayed"].text == "4"

    def test_replay_deterministic_provider_identical_across_runs(self, tmp_path):
        log = AuditLog(str(tmp_path / "r2.log"))
        msgs = [{"role": "user", "content": "Translate: hello"}]
        log.record("execute", "s1", True, messages=msgs)
        entry_hash = log.read_all()[0]["entry_hash"]

        def fn(messages, system=None):
            return "bonjour"

        r1 = log.replay(entry_hash, fn=fn)
        r2 = log.replay(entry_hash, fn=fn)
        assert r1["replayed"].text == r2["replayed"].text == "bonjour"
