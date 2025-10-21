# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random
import string
import pytest

import jubilant
import temporalio.client

from .conftest import (
    PYTHON_NAMESPACE,
    GO_NAMESPACE,
    PYTHON_TASK_QUEUE,
    GO_TASK_QUEUE,
    PYTHON_WORKFLOW_CLASSNAME,
    GO_WORKFLOW_CLASSNAME,
)
from .helpers import start_workflow

logger = logging.getLogger(__name__)


async def test_python_workflow(juju_server_model: jubilant.Juju):
    """Test to ensure that the python workflow can be executed"""
    logger.info("Creating python workflow manually")

    random_keyword = "".join(random.choices(string.ascii_letters + string.digits, k=10))

    workflow_id, run_id = start_workflow(
        juju_server_model,
        PYTHON_NAMESPACE,
        PYTHON_TASK_QUEUE,
        PYTHON_WORKFLOW_CLASSNAME,
        input=random_keyword,
    )

    logger.info("Ensuring only workflow exists")

    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=PYTHON_NAMESPACE
    )

    python_workflow_ids = []
    python_run_ids = []
    async for workflow in client.list_workflows():
        python_workflow_ids.append(workflow.id)
        python_run_ids.append(workflow.run_id)

    assert workflow_id in python_workflow_ids, (
        "Unable to find started workflow in python namespace"
    )
    assert run_id in python_run_ids, (
        "Unable to find run of the started workflow execution in python namespace"
    )

    logger.info("Waiting until workflow completes")

    workflow_handle = client.get_workflow_handle(workflow_id)
    workflow_result = await workflow_handle.result()
    assert workflow_result == f"Hello world to {random_keyword} in python!", (
        "Unexpected result in activity of started workflow"
    )


async def test_go_workflow(juju_server_model: jubilant.Juju):
    """Test to ensure that the go workflow can be executed"""
    logger.info("Creating go workflow manually")

    random_keyword = "".join(random.choices(string.ascii_letters + string.digits, k=10))

    workflow_id, run_id = start_workflow(
        juju_server_model, GO_NAMESPACE, GO_TASK_QUEUE, GO_WORKFLOW_CLASSNAME, input=random_keyword
    )

    logger.info("Ensuring only workflow exists")

    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=GO_NAMESPACE
    )

    go_workflow_ids = []
    go_run_ids = []
    async for workflow in client.list_workflows():
        go_workflow_ids.append(workflow.id)
        go_run_ids.append(workflow.run_id)

    assert workflow_id in go_workflow_ids, "Unable to find started workflow in go namespace"
    assert run_id in go_run_ids, "Unable to find run of started workflow in go namespace"

    logger.info("Waiting until workflow completes")

    workflow_handle = client.get_workflow_handle(workflow_id)
    workflow_result = await workflow_handle.result()
    assert workflow_result == f"Hello world to {random_keyword} in go!", (
        "Unexpected result in activity of started workflow"
    )


@pytest.mark.dependency(depends=["test_python_workflow", "test_go_workflow"])
async def test_namespace_isolation(juju_server_model: jubilant.Juju):
    """Ensure there is no overlap between workflows in python and go namespaces"""
    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    logger.info("Retrieving all workflow ids in the python namespace")

    python_namespace_client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=PYTHON_NAMESPACE
    )

    python_workflow_ids = []
    python_run_ids = []
    async for workflow in python_namespace_client.list_workflows():
        python_workflow_ids.append(workflow.id)
        python_run_ids.append(workflow.run_id)

    logger.info("Retrieving all workflow ids in the go namespace")

    go_namespace_client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=GO_NAMESPACE
    )

    go_workflow_ids = []
    go_run_ids = []
    async for workflow in go_namespace_client.list_workflows():
        go_workflow_ids.append(workflow.id)
        go_run_ids.append(workflow.run_id)

    logger.info("Ensuring no overlap between workflows in python and go namespaces")
    assert not set(python_workflow_ids).intersection(set(go_workflow_ids)), (
        "Workflow IDs in python and go namespaces not disjoint"
    )

    for run_id in python_run_ids:
        assert run_id not in go_run_ids, f"Python run id {run_id} found in go namespace"
