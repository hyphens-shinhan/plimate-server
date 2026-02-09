import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.deps import CurrentUser, get_current_user
from app.main import app

TEST_USER_ID = os.environ.get("TEST_USER_ID", "00000000-0000-0000-0000-000000000000")


def _override_get_current_user() -> CurrentUser:
    return CurrentUser(id=UUID(TEST_USER_ID), email="test@example.com")


app.dependency_overrides[get_current_user] = _override_get_current_user


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
