"""AC-8: the evaluation set has the required shape and its graders match what the script really prints."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent.parent / "evals"

# For every task case: the command a correct run performs (written to the file the prompt names).
REFERENCE = {
    "task-first-monday": ("findings.json", ["explain", "0 9 1-7 * 1", "--dialect", "unix", "--from",
                                            "2027-01-01T00:00Z"]),
    "task-quartz-to-eventbridge": ("eventbridge.json", ["convert", "0 0 12 ? * 2-6", "--from-dialect", "quartz",
                                                        "--to", "eventbridge", "--from", "2027-01-01T00:00Z"]),
    "task-weekday-shift": ("diff.json", ["diff", "0 0 12 ? * 2-6", "0 12 * * 2-6", "--dialect", "quartz",
                                         "--dialect2", "unix", "--from", "2027-01-01T00:00Z"]),
    "task-github-dst-gap": ("runs.json", ["next", "30 2 * * *", "--dialect", "github", "--tz", "America/New_York",
                                          "--from", "2027-03-14T00:00", "--count", "2"]),
    "task-scheduler-fold": ("fold.json", ["next", "30 1 * * ? *", "--dialect", "eventbridge-scheduler", "--tz",
                                          "America/New_York", "--from", "2027-11-07T00:00", "--count", "2"]),
    "task-error-eventbridge-qmark": ("fixed.json", ["parse", "0 12 ? * MON-FRI *", "--dialect", "eventbridge"]),
}

# For every result grader that reads the agent's answer (target: trace): the script command whose text output
# (stdout + stderr, --lang en) it must match, the exit code of that command, and a correct command whose output
# must NOT match (so the grader tells the right finding from a run that never hit it).
# A trace grader that is not listed here fails test_trace_graders_are_backed_by_script_output: no grader may
# score the agent's own prose about a fact the script does not print.
TRACE_REFERENCE = {
    ("task-error-eventbridge-qmark", "result-code.md"): (
        ["parse", "0 12 * * MON-FRI *", "--dialect", "eventbridge"], 2,
        ["parse", "0 12 ? * MON-FRI *", "--dialect", "eventbridge"],
    ),
}


def _front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    block = text.split("---")[1]
    out = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def _pattern(raw: str) -> str:
    assert raw.startswith("'") and raw.endswith("'"), raw
    return raw[1:-1]


def _cases(prefix: str):
    return sorted(d for d in EVALS.iterdir() if d.is_dir() and d.name.startswith(prefix))


def _trace_graders():
    """(case, grader file name) of every task result grader that reads the agent's answer."""
    found = []
    for d in _cases("task-"):
        for g in sorted((d / "graders").glob("result-*.md")):
            if _front(g).get("target") == "trace":
                found.append((d.name, g.name))
    return found


def test_counts():
    trigger = _cases("trigger-")
    near = _cases("notrigger-near-")
    far = [d for d in _cases("notrigger-") if not d.name.startswith("notrigger-near-")]
    tasks = _cases("task-")
    assert len(trigger) == 13
    assert sum(1 for d in trigger if re.search(r"[가-힣]", (d / "prompt.md").read_text(encoding="utf-8"))) == 3
    assert len(near) == 7 and len(near) + len(far) == 12
    # v2: exactly six task cases, every one scored on exact script values; the prose-only k8s case is gone
    assert len(tasks) == 6, [d.name for d in tasks]
    assert sorted(d.name for d in tasks) == sorted(REFERENCE)
    assert "task-k8s-timezone" not in {d.name for d in tasks}
    assert not (EVALS / "fixtures" / "task-k8s-timezone").exists()
    assert sum(1 for d in tasks if d.name.startswith("task-error-")) == 1


def test_trigger_prompts_do_not_name_the_skill():
    for d in _cases("trigger-"):
        body = (d / "prompt.md").read_text(encoding="utf-8").split("---", 2)[2]
        assert not re.search(r"cron-dialects|\bskill\b|스킬", body, re.I), d.name


def test_every_case_has_prompt_and_graders():
    for d in EVALS.iterdir():
        if d.is_dir() and d.name != "fixtures":
            assert (d / "prompt.md").is_file(), d.name
            assert list((d / "graders").glob("*.md")), d.name


def test_every_task_has_fixture_and_exact_value_regex():
    for d in _cases("task-"):
        assert d.name in REFERENCE, d.name
        fixtures = EVALS / "fixtures" / d.name
        assert fixtures.is_dir() and list(fixtures.iterdir()), d.name
        regexes = [g for g in (d / "graders").glob("*.md") if _front(g).get("type") == "regex"]
        assert regexes, d.name
        for g in regexes:
            assert len(_pattern(_front(g)["pattern"])) >= 8
    # no fixture folder is left without its task case
    for f in (EVALS / "fixtures").iterdir():
        assert f.name in REFERENCE, f.name


@pytest.mark.parametrize("case", sorted(REFERENCE))
def test_graders_match_real_script_output(case, cli, tmp_path):
    out_name, argv = REFERENCE[case]
    target = tmp_path / out_name
    code, stdout, stderr = cli(argv + ["--out", str(target)])
    assert code == (1 if argv[0] == "diff" else 0), stderr          # diff exits 1 when the schedules differ
    saved = target.read_text(encoding="utf-8")
    for g in sorted((EVALS / case / "graders").glob("result-*.md")):
        front = _front(g)
        pattern = re.compile(_pattern(front["pattern"]))
        if front["target"] == "trace":
            continue                                                 # checked against the text output below
        assert f"path: {out_name}" in front["target"], g.name        # the file the prompt asks the agent to save
        assert pattern.search(saved), f"{g.name}: {pattern.pattern}"


def test_trace_graders_are_backed_by_script_output():
    """Every trace-target result grader must have a script command whose output it is checked against."""
    assert sorted(_trace_graders()) == sorted(TRACE_REFERENCE)


@pytest.mark.parametrize("case,grader", sorted(TRACE_REFERENCE))
def test_trace_graders_match_the_script_text_output(case, grader, cli):
    """An agent that quotes the script's English line passes; the grader does not rely on the agent's prose."""
    argv, want_code, other_argv = TRACE_REFERENCE[(case, grader)]
    g = EVALS / case / "graders" / grader
    front = _front(g)
    assert front["target"] == "trace" and front["type"] == "regex"
    pattern = re.compile(_pattern(front["pattern"]))
    code, out, err = cli(argv + ["--lang", "en"])
    assert code == want_code, err
    assert pattern.search(out + err), f"{grader}: {pattern.pattern}"
    # the grader is specific: a run that never hit the finding does not satisfy it
    code, out, err = cli(other_argv + ["--lang", "en"])
    assert code == 0, err
    assert not pattern.search(out + err), f"{grader} also matches {other_argv}"


def test_wrong_answers_do_not_match_the_graders(cli, tmp_path):
    """The graders must reject the usual wrong answers (loose graders survive the mutation check)."""
    target = tmp_path / "x.json"
    cli(["convert", "0 0 12 ? * 2-6", "--from-dialect", "quartz", "--to", "unix", "--from", "2027-01-01T00:00Z",
         "--out", str(target)])
    text = target.read_text(encoding="utf-8")
    for name in ("result-expr.md", "result-wrapped.md"):
        g = EVALS / "task-quartz-to-eventbridge" / "graders" / name
        assert not re.search(_pattern(_front(g)["pattern"]), text), g.name
    cli(["next", "30 2 * * *", "--dialect", "cronie", "--tz", "America/New_York", "--from", "2027-03-14T00:00",
         "--count", "2", "--out", str(target)])
    text = target.read_text(encoding="utf-8")
    for g in (EVALS / "task-github-dst-gap" / "graders").glob("result-*.md"):
        assert not re.search(_pattern(_front(g)["pattern"]), text), g.name


def test_skill_md_asks_for_answer_language_and_tz_note():
    skill = (EVALS.parent / "skills" / "cron-dialects" / "SKILL.md").read_text(encoding="utf-8")
    assert "`--lang en` or `--lang ko`" in skill
    assert "`tz_note`" in skill and "word for word" in skill
