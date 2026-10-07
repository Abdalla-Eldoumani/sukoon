import sqlite3

import pytest

from sukoon.jobs.store import Store, TransitionError


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


def test_link_jobs_fetch_before_they_are_checked(store):
    job = store.create("youtube.com/watch?v=x", {}, state="fetching", link={"url": "u"})
    assert job["link"] == {"url": "u"}
    for state in ("checking", "queued", "encoding", "done"):
        job = store.transition(job["id"], state)
    stopped = store.create("youtube.com/watch?v=y", {}, state="fetching")
    store.transition(stopped["id"], "interrupted")
    assert store.transition(stopped["id"], "fetching")["state"] == "fetching"


def test_a_database_from_the_first_release_takes_link_jobs(tmp_path):
    # The 0.1.0 table: no fetching state in its CHECK and no link column.
    db = sqlite3.connect(tmp_path / "jobs.db")
    db.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, created REAL NOT NULL, name TEXT NOT NULL, "
        "kind TEXT, state TEXT NOT NULL CHECK (state IN ('checking', 'awaiting_track', "
        "'awaiting_confirm', 'queued', 'waiting_model', 'decoding', 'separating', 'encoding', "
        "'done', 'failed', 'canceled', 'interrupted')), stage TEXT, "
        "progress REAL NOT NULL DEFAULT 0, eta REAL, options TEXT NOT NULL DEFAULT '{}', "
        "probe TEXT, result TEXT, error TEXT, retryable INTEGER NOT NULL DEFAULT 1)"
    )
    db.execute(
        "INSERT INTO jobs (id, created, name, state, result) "
        "VALUES ('a', 1.0, 'old.mp3', 'done', '{\"notes\": []}')"
    )
    db.commit()
    db.close()
    s = Store(tmp_path / "jobs.db")
    assert s.get("a")["name"] == "old.mp3"
    assert s.get("a")["result"] == {"notes": []}
    assert s.create("x.com/u/status/1", {}, state="fetching")["state"] == "fetching"
    s.close()
