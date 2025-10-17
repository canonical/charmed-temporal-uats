# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for UATs."""

import pytest
import jubilant


def pytest_addoption(parser):
    parser.addoption(
        "--server-model",
        action="store",
        help="Model for temporal server",
    )
    parser.addoption(
        "--workers-model",
        action="store",
        help="Model for temporal workers",
    )
    parser.addoption(
        "--cos-model",
        action="store",
        help="Model for COS related to temporal",
    )


@pytest.fixture(scope="module")
def python_namespace():
    return "worker-python-namespace"


@pytest.fixture(scope="module")
def go_namespace():
    return "worker-go-namespace"


@pytest.fixture(scope="module")
def python_task_queue():
    return "worker-python-queue"


@pytest.fixture(scope="module")
def go_task_queue():
    return "worker-go-queue"


@pytest.fixture(scope="module")
def python_workflow_classname():
    return "HelloWorldWorkflow"


@pytest.fixture(scope="module")
def go_workflow_classname():
    return "Workflow"


@pytest.fixture(scope="module")
def juju_server_model(request: pytest.FixtureRequest):
    server_model_name = request.config.getoption("--server-model")

    server_model = jubilant.Juju(model=server_model_name)

    server_model.wait_timeout = 10 * 60

    yield server_model

    if request.session.testsfailed:
        log = server_model.debug_log(limit=100)
        print(log, end="--- END OF SERVER MODEL LOGS ---")


@pytest.fixture(scope="module")
def juju_workers_model(request: pytest.FixtureRequest):
    workers_model_name = request.config.getoption("--workers-model")

    workers_model = jubilant.Juju(model=workers_model_name)

    workers_model.wait_timeout = 10 * 60

    yield workers_model

    if request.session.testsfailed:
        log = workers_model.debug_log(limit=100)
        print(log, end="--- END OF WORKERS MODEL LOGS ---")
