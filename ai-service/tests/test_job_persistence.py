"""Generation jobs survive a restart when JOBS_DIR is set; a job that was running is reported as failed."""
from app.jobs import JobOutput, JobStore
from app.models import FileAnalysis, GenerateRequest, JobStatus, Scope


def make_request():
    return GenerateRequest(scope=Scope.file, target="src/a.py", template_id="default", files=[FileAnalysis(path="src/a.py")])


def test_a_finished_job_and_its_output_are_read_back_after_a_restart(tmp_path):
    store = JobStore(str(tmp_path))
    job = store.create(make_request())
    store.update(job.id, status=JobStatus.completed, progress=1.0, result="# doc")
    store.set_output(job.id, JobOutput(scope=Scope.file, target="src/a.py", template_id="default", template_name=None,
                                       output_language="en", sections=[("src/a.py", "# a", "generated", 0.9)]))

    restarted = JobStore(str(tmp_path))
    assert restarted.get(job.id).status == JobStatus.completed
    assert restarted.get(job.id).result == "# doc"
    output = restarted.get_output(job.id)
    assert output.sections == [("src/a.py", "# a", "generated", 0.9)]
    assert output.output_language == "en"


def test_a_job_that_was_running_is_marked_failed_after_a_restart(tmp_path):
    store = JobStore(str(tmp_path))
    job = store.create(make_request())
    store.update(job.id, status=JobStatus.running)

    restarted = JobStore(str(tmp_path))
    assert restarted.get(job.id).status == JobStatus.failed
    assert "restarted" in restarted.get(job.id).error


def test_an_unreadable_file_does_not_stop_the_store(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert JobStore(str(tmp_path)).list() == []


def test_without_a_directory_nothing_is_written(tmp_path):
    store = JobStore()
    store.create(make_request())
    assert list(tmp_path.iterdir()) == []
