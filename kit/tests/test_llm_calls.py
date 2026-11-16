from kit import llm


def test_every_call_to_the_model_is_repeatable_and_a_schema_forces_the_shape(monkeypatch):
    sent = []
    client = llm.OllamaClient("http://127.0.0.1:11434")
    monkeypatch.setattr(client, "_call", lambda path, body=None, timeout=300: sent.append(body) or {"message": {"content": "{}"}})
    schema = {"type": "object", "properties": {"kind": {"type": "string"}}}
    client.chat("m", [{"role": "user", "content": "x"}], schema=schema)
    client.chat("m", [{"role": "user", "content": "x"}])
    with_schema, without = sent
    assert with_schema["format"] == schema and with_schema["options"]["temperature"] == 0.0
    assert with_schema["options"]["seed"] == without["options"]["seed"] == llm.SEED  # the same file gets the same answer every time
    assert "format" not in without
