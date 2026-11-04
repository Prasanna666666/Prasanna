"""`aperture check` times every step of the real flow; here the timing and the reporting are checked with stand-ins."""

import time

from aperture import cli


def test_time_steps_times_each_step_and_reports_failures_instead_of_raising():
    def slow():
        time.sleep(0.02)

    def broken():
        raise RuntimeError("Ollama is not reachable")

    rows = cli.time_steps([("fast", lambda: None), ("slow", slow), ("broken", broken)])
    assert [r[0] for r in rows] == ["fast", "slow", "broken"]
    assert rows[1][1] >= 0.02 > rows[0][1] and rows[0][2] == ""
    assert rows[2][2].startswith("FAILED: Ollama is not reachable")


def test_check_command_exists_and_budgets_cover_the_slow_steps():
    assert cli.build_parser().parse_args(["check"]).command == "check"
    assert set(cli.BUDGET) == {"router", "first words", "AI plan", "instant photo matches"}
    assert "check" not in cli.GUARDED  # it reads no photos


def test_the_image_model_choices_are_named_models():
    from aperture import cli

    assert cli.IMAGE_MODELS["small"] == ("ViT-B-32", "laion2b_s34b_b79k") and cli.IMAGE_MODELS["large"] == ("ViT-L-14", "laion2b_s32b_b82k")
