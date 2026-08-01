"""Cross-process audit-log concurrency tests.

Two independent processes append to the *same* audit file concurrently;
the file must remain a valid, fully verifiable hash chain.  Uses
``multiprocessing`` (``spawn`` on Windows) with a module-level worker so
the target is picklable.
"""

import multiprocessing as mp

from brompt.audit import AuditLog


def _writer(path: str, count: int, key: str) -> None:
    """Append *count* records to the shared log from one process."""
    log = AuditLog(path, secret_key=key)
    for i in range(count):
        log.record("execute", f"p{mp.current_process().pid}-{i}", True, detail=str(i))


def test_concurrent_writers_produce_verifiable_chain(tmp_path):
    path = str(tmp_path / "shared.log")
    key = "concurrent-seed"
    count = 100
    open(path, "a", encoding="utf-8").close()  # pre-create to avoid a creation race

    procs = [mp.Process(target=_writer, args=(path, count, key)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=90)
    for p in procs:
        assert p.exitcode == 0, f"writer process exited with {p.exitcode}"

    log = AuditLog(path, secret_key=key)
    assert log.verify() is True
    report = log.verify_report()
    assert report["ok"] is True
    assert report["entries"] == 2 * count
    assert len(log.read_all()) == 2 * count


def test_concurrent_writers_hmac_chain_verifies(tmp_path):
    """With portalocker present every record is HMAC-signed under lock."""
    path = str(tmp_path / "shared_hmac.log")
    key = "hmac-seed"
    count = 50
    open(path, "a", encoding="utf-8").close()  # pre-create to avoid a creation race

    procs = [mp.Process(target=_writer, args=(path, count, key)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=90)
    for p in procs:
        assert p.exitcode == 0

    log = AuditLog(path, secret_key=key)
    assert log.verify() is True
    assert log.is_signed is True
