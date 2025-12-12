import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class DummyS3Client:
    """S3 stub that records uploads without touching the network."""

    def __init__(self):
        self.put_calls = []
        self.head_calls = []

    def head_bucket(self, Bucket):
        self.head_calls.append(Bucket)
        return None

    def put_object(self, Bucket, Key, Body, ContentType):
        self.put_calls.append(
            {"Bucket": Bucket, "Key": Key, "Body": Body, "ContentType": ContentType}
        )
        return SimpleNamespace(etag="dummy")


@pytest.fixture
def dummy_s3(monkeypatch):
    client = DummyS3Client()
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)
    return client


@pytest.fixture
def api_module(monkeypatch, dummy_s3):
    """Reload the api module with safe env vars and a stubbed S3 client."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-google-key")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    # Avoid unexpected real Supabase connections during tests
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    api = importlib.import_module("api")
    api = importlib.reload(api)
    return api
