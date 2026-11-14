"""rental_job_payload must map the rental period, not the event date."""

from datetime import date, datetime

from app.domains.stockwire.client import rental_job_payload


class _FakeJob:
    def __init__(
        self,
        id="11111111-1111-1111-1111-111111111111",
        title="Show",
        venue_name="Venue",
        notes="n",
        event_date=None,
        start_date=None,
        end_date=None,
    ):
        self.id = id
        self.title = title
        self.venue_name = venue_name
        self.notes = notes
        self.event_date = event_date
        self.start_date = start_date
        self.end_date = end_date


def test_uses_rental_dates_not_event_date():
    job = _FakeJob(
        event_date=datetime(2026, 11, 1, 20, 0),
        start_date=date(2026, 11, 10),
        end_date=date(2026, 11, 12),
    )
    payload = rental_job_payload(job)
    # event_date must NOT be forwarded as start_date
    assert payload.get("start_date") == "2026-11-10"
    assert payload.get("end_date") == "2026-11-12"
    assert payload["start_date"] != "2026-11-01"


def test_end_date_is_included():
    job = _FakeJob(start_date=date(2026, 11, 10), end_date=date(2026, 11, 12))
    payload = rental_job_payload(job)
    assert payload["end_date"] == "2026-11-12"


def test_open_ended_rental_closes_to_single_day():
    # When only a start date is set we still send an end date so the rental job
    # has a closed window instead of an open-ended one.
    job = _FakeJob(start_date=date(2026, 11, 10), end_date=None)
    payload = rental_job_payload(job)
    assert payload["start_date"] == "2026-11-10"
    assert payload["end_date"] == "2026-11-10"


def test_no_dates_sends_neither():
    job = _FakeJob(start_date=None, end_date=None, event_date=date(2026, 1, 1))
    payload = rental_job_payload(job)
    assert "start_date" not in payload
    assert "end_date" not in payload
