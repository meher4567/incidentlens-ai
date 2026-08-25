"""Worker orchestration contracts for the live event pipeline."""

from worker.tasks import aggregation, detection


class _Session:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def close(self):
        self.closed = True

    def rollback(self):
        self.rolled_back = True


def test_aggregation_triggers_detection_when_windows_close(monkeypatch):
    session = _Session()
    delayed = []
    monkeypatch.setattr(aggregation, "SyncSessionLocal", lambda: session)
    monkeypatch.setattr(aggregation, "run_aggregation_all_services", lambda value: 12)
    monkeypatch.setattr(detection.run_detection, "delay", lambda: delayed.append(True))

    result = aggregation.aggregate_windows.run()

    assert result == {"status": "ok", "windows_computed": 12}
    assert delayed == [True]
    assert session.closed


def test_aggregation_does_not_fan_out_without_new_windows(monkeypatch):
    session = _Session()
    delayed = []
    monkeypatch.setattr(aggregation, "SyncSessionLocal", lambda: session)
    monkeypatch.setattr(aggregation, "run_aggregation_all_services", lambda value: 0)
    monkeypatch.setattr(detection.run_detection, "delay", lambda: delayed.append(True))

    result = aggregation.aggregate_windows.run()

    assert result == {"status": "ok", "windows_computed": 0}
    assert delayed == []
    assert session.closed
