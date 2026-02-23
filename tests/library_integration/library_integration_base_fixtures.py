import pytest
from pathlib import Path
from detectmatelibrary.schemas import ParserSchema, LogSchema


@pytest.fixture(scope="session")
def test_log_file() -> Path:
    """Return path to the test log file in this folder."""
    return Path(__file__).parent / "test_logs.log"


@pytest.fixture(scope="session")
def audit_log_file() -> Path:
    return Path(__file__).parent / "audit.log"


@pytest.fixture(scope="session")
def test_templates_file() -> Path:
    return Path(__file__).parent / "audit_templates.txt"


@pytest.fixture(scope="session")
def test_parser_messages() -> list:
    """Generate test ParserSchema messages for detector input."""
    messages = []
    parser_configs = [
        {
            "parserType": "LogParser",
            "parserID": "parser_001",
            "EventID": 1,
            "template": "User <*> logged in from <*>",
            "variables": ["john", "192.168.1.100"],
            "parsedLogID": "101",
            "logID": "1",
            "log": "User john logged in from 192.168.1.100",
            "logFormatVariables": {
                "username": "john",
                "ip": "192.168.1.100",
                "Time": "1634567890"
            },
            "receivedTimestamp": 1634567890,
            "parsedTimestamp": 1634567891,
        },
        {
            "parserType": "LogParser",
            "parserID": "parser_002",
            "EventID": 2,
            "template": "Database query failed: <*>",
            "variables": ["connection timeout"],
            "parsedLogID": "102",
            "logID": "2",
            "log": "Database query failed: connection timeout",
            "logFormatVariables": {
                "error": "connection timeout",
                "severity": "HIGH",
                "Time": "1634567900"
            },
            "receivedTimestamp": 1634567900,
            "parsedTimestamp": 1634567901,
        },
        {
            "parserType": "LogParser",
            "parserID": "parser_003",
            "EventID": 3,
            "template": "File <*> accessed by <*> at <*>",
            "variables": ["config.txt", "admin", "10:45:30"],
            "parsedLogID": "103",
            "logID": "3",
            "log": "File config.txt accessed by admin at 10:45:30",
            "logFormatVariables": {
                "filename": "config.txt",
                "user": "admin",
                "Time": "1634567910"
            },
            "receivedTimestamp": 1634567910,
            "parsedTimestamp": 1634567911,
        },
    ]

    for config in parser_configs:
        parser_msg = ParserSchema(config)
        byte_message = parser_msg.serialize()
        messages.append(byte_message)
    return messages


@pytest.fixture(scope="session")
def test_log_messages() -> list:
    """Fixture providing test LogSchema messages for parser input."""
    messages = []
    log_configs = [
        {
            "logID": "1",
            "log": "User john logged in from 192.168.1.100",
            "logSource": "auth_server",
            "hostname": "server-01",
        },
        {
            "logID": "2",
            "log": "Database query failed: connection timeout",
            "logSource": "database",
            "hostname": "db-01",
        },
        {
            "logID": "3",
            "log": "File config.txt accessed by admin at 10:45:30",
            "logSource": "file_server",
            "hostname": "fs-01",
        },
    ]
    for config in log_configs:
        log_msg = LogSchema(config)
        byte_message = log_msg.serialize()
        messages.append(byte_message)
    return messages
