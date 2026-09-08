"""Explicit project selection; never inherit a developer's default GCP project."""
import os
import datetime
import subprocess
from functools import lru_cache

from google.auth.credentials import Credentials

PROJECT = os.getenv("CLAPPY_GOOGLE_PROJECT", "clappy-cinema-2026-0907")
LOCATION = os.getenv("CLAPPY_GOOGLE_LOCATION", "global")
MODEL = os.getenv("CLAPPY_GEMINI_MODEL", "gemini-2.5-flash")
DIRECTOR_LIVE_MODEL = os.getenv("CLAPPY_DIRECTOR_LIVE_MODEL", MODEL)


class LocalGcloudCredentials(Credentials):
    """Development-only token refresh using the user's already authorized CLI."""
    def __init__(self):
        super().__init__()
        self._quota_project_id = PROJECT

    def refresh(self, request):
        result = subprocess.run(["gcloud", "auth", "print-access-token", f"--project={PROJECT}"],
            capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError("The Google Cloud CLI login needs to be renewed")
        self.token = result.stdout.strip()
        self.expiry = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(minutes=5)


@lru_cache(maxsize=1)
def google_credentials():
    import google.auth
    if os.getenv("CLAPPY_AUTH_MODE") == "gcloud":
        credentials = LocalGcloudCredentials()
        # Refresh before constructing gRPC channels; avoid spawning the CLI
        # for the first time from an active gRPC authentication callback.
        credentials.refresh(None)
    else:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id=PROJECT,
        )
    return credentials


def google_client():
    from google import genai
    from google.genai import types

    credentials = google_credentials()
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION, credentials=credentials,
        http_options=types.HttpOptions(timeout=45000, retry_options=types.HttpRetryOptions(attempts=2)))
