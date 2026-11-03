"""Pruebas de integración: el servidor real registra y ejecuta las tools vía MCP."""

from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import call_json, call_tool_result

EXPECTED_TOOLS = {
    # system
    "system_info",
    "system_now",
    "system_disk_usage",
    "system_env_vars",
    "system_run_command",
    # files
    "files_list_files",
    "files_read_file",
    "files_write_file",
    "files_delete_file",
    "files_search_files",
    # data
    "data_read_csv",
    "data_read_json",
    "data_flatten_json",
    "data_sqlite_query",
    "data_to_json",
    # analysis
    "analysis_stats",
    "analysis_math_eval",
    "analysis_linear_regression",
    "analysis_correlation",
    "analysis_frequency",
    # ai
    "ai_text_stats",
    "ai_summarize",
    "ai_sentiment",
    "ai_keywords",
    "ai_extract",
    "ai_slugify",
    # automation
    "automation_http_request",
    "automation_send_webhook",
    "automation_uuid4",
    "automation_timestamp",
    "automation_wait",
}


async def test_all_modules_register_expected_tools(server) -> None:
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert EXPECTED_TOOLS <= names
    assert len(names) == len(tools), "No debe haber tools duplicadas"


async def test_system_tools(server, monkeypatch) -> None:
    info = await call_json(server, "system_info")
    assert "python" in info and "platform" in info

    bogota = await call_json(server, "system_now", {"tz": "America/Bogota"})
    assert "-05:00" in bogota["iso"]

    unknown_tz = await call_json(server, "system_now", {"tz": "Marte/Olympus"})
    assert "error" in unknown_tz

    disk = await call_json(server, "system_disk_usage")
    assert disk["total"] > 0

    monkeypatch.setenv("MY_SERVICE_TOKEN", "supersecreto")
    monkeypatch.setenv("MY_SERVICE_REGION", "us-east-1")
    env = await call_json(server, "system_env_vars", {"prefix": "MY_SERVICE_"})
    assert env["variables"]["MY_SERVICE_TOKEN"] == "***"
    assert env["variables"]["MY_SERVICE_REGION"] == "us-east-1"

    shell = await call_json(server, "system_run_command", {"command": "echo hi"})
    assert "error" in shell  # deshabilitada por defecto (MCP_ENABLE_SHELL=false)


async def test_files_roundtrip(server) -> None:
    written = await call_json(
        server,
        "files_write_file",
        {"path": "notas/demo.txt", "content": "línea uno\npalabra clave aquí\nlínea tres\n"},
    )
    assert written["bytes_written"] > 0

    listed = await call_json(server, "files_list_files", {"path": "."})
    assert any(e["name"] == "notas" and e["type"] == "dir" for e in listed["entries"])

    read = await call_json(server, "files_read_file", {"path": "notas/demo.txt"})
    assert "palabra clave" in read["content"]

    found = await call_json(server, "files_search_files", {"query": "clave"})
    assert found["match_count"] >= 1
    assert found["matches"][0]["path"].endswith("demo.txt")

    deleted = await call_json(server, "files_delete_file", {"path": "notas/demo.txt"})
    assert deleted["deleted"] == "notas/demo.txt"


async def test_files_sandbox_escape_blocked(server) -> None:
    response = await call_json(server, "files_read_file", {"path": "../../etc/passwd"})
    assert "error" in response


async def test_data_csv_and_json(server) -> None:
    await call_tool_result(
        server,
        "files_write_file",
        {"path": "datos.csv", "content": "nombre,edad\nAna,30\nLuis,25\n"},
    )
    csv_data = await call_json(server, "data_read_csv", {"path": "datos.csv"})
    assert csv_data["columns"] == ["nombre", "edad"]
    assert csv_data["total_rows"] == 2
    assert csv_data["rows"][0]["nombre"] == "Ana"

    await call_tool_result(
        server,
        "files_write_file",
        {"path": "conf.json", "content": '{"db": "sqlite", "reintentos": 3}'},
    )
    conf = await call_json(server, "data_read_json", {"path": "conf.json"})
    assert conf["reintentos"] == 3

    flat = await call_json(server, "data_flatten_json", {"data": {"a": {"b": [1, 2]}}})
    assert flat == {"a.b.0": 1, "a.b.1": 2}


async def test_data_sqlite_query(server, settings) -> None:
    db_path = settings.workspace_dir / "app.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE usuarios (id INTEGER, nombre TEXT)")
    con.executemany("INSERT INTO usuarios VALUES (?, ?)", [(1, "Ana"), (2, "Luis")])
    con.commit()
    con.close()

    result = await call_json(
        server,
        "data_sqlite_query",
        {"path": "app.db", "sql": "SELECT id, nombre FROM usuarios ORDER BY id", "limit": 10},
    )
    assert result["columns"] == ["id", "nombre"]
    assert result["rows"] == [[1, "Ana"], [2, "Luis"]]

    blocked = await call_json(
        server, "data_sqlite_query", {"path": "app.db", "sql": "DROP TABLE usuarios"}
    )
    assert "error" in blocked


async def test_analysis_tools(server) -> None:
    stats = await call_json(server, "analysis_stats", {"numbers": [1, 2, 3, 4]})
    assert stats["mean"] == 2.5

    calc = await call_json(server, "analysis_math_eval", {"expression": "(2 + 3) * sqrt(16)"})
    assert calc["result"] == 20.0

    reg = await call_json(server, "analysis_linear_regression", {"x": [1, 2, 3], "y": [3, 5, 7]})
    assert reg["slope"] == 2.0

    corr = await call_json(server, "analysis_correlation", {"x": [1, 2, 3], "y": [6, 5, 4]})
    assert corr["direction"] == "negative"

    freq = await call_json(server, "analysis_frequency", {"items": ["a", "b", "a"], "top": 5})
    assert freq["most_common"][0] == {"item": "a", "count": 2}


async def test_ai_tools(server) -> None:
    stats = await call_json(
        server, "ai_text_stats", {"text": "Hola mundo.\n\nOtro párrafo con más texto."}
    )
    assert stats["paragraphs"] == 2

    summary = await call_json(
        server,
        "ai_summarize",
        {"text": "El gato duerme. El perro ladra. El sol brilla. Los pájaros cantan. La luna aparece."},
    )
    assert summary["summary_sentences"] <= 3

    sentiment = await call_json(server, "ai_sentiment", {"text": "Excelente servicio, ¡muchas gracias!"})
    assert sentiment["label"] in {"positive", "neutral"}

    slug = await call_json(server, "ai_slugify", {"text": "Título del Blog 2024"})
    assert slug["slug"] == "titulo-del-blog-2024"


async def test_automation_utilities(server) -> None:
    uuid_response = await call_json(server, "automation_uuid4")
    assert len(uuid_response["uuid"]) == 36

    stamp = await call_json(server, "automation_timestamp")
    assert stamp["epoch"] > 1_600_000_000

    waited = await call_json(server, "automation_wait", {"seconds": 0.01})
    assert waited["waited_seconds"] == pytest.approx(0.01)


async def test_automation_blocks_private_hosts(server) -> None:
    loopback = await call_json(server, "automation_http_request", {"url": "http://127.0.0.1:9/x"})
    assert "error" in loopback and "SSRF" in loopback["error"]

    webhook = await call_json(
        server, "automation_send_webhook", {"url": "http://localhost/hook", "payload": {"a": 1}}
    )
    assert "error" in webhook
