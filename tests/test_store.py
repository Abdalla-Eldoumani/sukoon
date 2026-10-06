import sqlite3

import pytest

from sukoon.store import Store, TransitionError


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "jobs.db")
    yield s
    s.close()


def test_jobs_list_in_creation_order(store):
    ids = [store.create(f"file{i}.mp3", {})["id"] for i in range(5)]
    assert [j["id"] for j in store.list()] == ids
    assert store.next_queued() is None


def test_transition_follows_the_lifecycle(store):
    job = store.create("a.mp3", {"preset": "fast"})
    assert job["state"] == "checking"
    for state in ("queued", "decoding", "separating", "encoding", "done"):
        job = store.transition(job["id"], state)
    assert job["state"] == "done"
    assert job["options"] == {"preset": "fast"}


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (["queued"], "done"),
        (["queued", "decoding", "separating", "encoding", "done"], "queued"),
        ([], "separating"),
    ],
)
def test_transition_refuses_a_wrong_from_state(store, path, bad):
    job = store.create("a.mp3", {})
    for state in path:
        store.transition(job["id"], state)
    with pytest.raises(TransitionError):
        store.transition(job["id"], bad)


def test_retry_from_every_stopped_state(store):
    for stop in ("failed", "canceled", "interrupted"):
        job = store.create("a.mp3", {})
        store.transition(job["id"], "queued")
        store.transition(job["id"], "decoding")
        store.transition(job["id"], stop)
        assert store.transition(job["id"], "queued")["state"] == "queued"


def test_check_constraint_rejects_unknown_states(store, tmp_path):
    job = store.create("a.mp3", {})
    db = sqlite3.connect(tmp_path / "jobs.db")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE jobs SET state = 'exploded' WHERE id = ?", (job["id"],))
        db.commit()


def test_update_cannot_change_state(store):
    job = store.create("a.mp3", {})
    with pytest.raises(ValueError):
        store.update(job["id"], state="done")


def test_listeners_see_every_change(store):
    seen = []
    store.subscribe(lambda event, job: seen.append((event, job["state"])))
    job = store.create("a.mp3", {})
    store.update(job["id"], progress=0.5)
    store.transition(job["id"], "failed", error="nope")
    store.delete(job["id"])
    assert seen == [
        ("job", "checking"),
        ("job", "checking"),
        ("job", "failed"),
        ("deleted", "failed"),
    ]


def test_json_fields_round_trip(store):
    job = store.create("a.mp3", {"format": "flac"})
    store.update(job["id"], probe={"duration": 3.5}, result={"notes": ["x"]})
    again = store.get(job["id"])
    assert again["probe"] == {"duration": 3.5}
    assert again["result"] == {"notes": ["x"]}


def test_state_survives_reopening(tmp_path):
    s = Store(tmp_path / "jobs.db")
    job = s.create("lecture.mp3", {})
    s.transition(job["id"], "queued")
    s.close()
    again = Store(tmp_path / "jobs.db")
    assert again.get(job["id"])["state"] == "queued"
    again.close()
