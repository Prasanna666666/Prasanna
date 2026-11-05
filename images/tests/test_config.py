def test_a_settings_file_from_the_time_of_the_cloud_option_still_loads_and_the_option_is_gone(tmp_path):
    import json

    from images.config import Paths, Settings

    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    paths.settings_file.write_text(
        json.dumps({"schema": 9, "cloud_interpreter": True, "cloud_model": "x", "cloud_cap_usd": 9.0, "page_size": 48})
    )
    s = Settings.load(paths)
    assert s.page_size == 48 and not hasattr(s, "cloud_interpreter") and not hasattr(s, "cloud_model")
