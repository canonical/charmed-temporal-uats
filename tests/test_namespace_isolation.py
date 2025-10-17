# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random
import string
import pytest

import jubilant
import temporalio.client

from .helpers import create_workflow

logger = logging.getLogger(__name__)


async def test_python_workflow(
    python_namespace: str,
    python_task_queue: str,
    python_workflow_classname: str,
    juju_server_model: jubilant.Juju,
):
    """Test to ensure that the python workflow can be executed"""
    logger.info("Creating python workflow manually")

    random_keyword = "".join(random.choices(string.ascii_letters + string.digits, k=10))

    workflow_id = create_workflow(
        juju_server_model,
        python_namespace,
        python_task_queue,
        python_workflow_classname,
        random_keyword,
    )

    logger.info("Ensuring only workflow exists")

    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=python_namespace
    )

    python_workflow_ids = []
    async for workflow in client.list_workflows():
        python_workflow_ids.append(workflow.id)

    assert workflow_id in python_workflow_ids, "Unable to find created workflow in all workflows"

    logger.info("Waiting until workflow completes")

    workflow_handle = client.get_workflow_handle(workflow_id)
    workflow_result = await workflow_handle.result()
    assert workflow_result == f"Hello world to {random_keyword} in python!", (
        "Unexpected result in activity of created workflow"
    )


async def test_go_workflow(
    go_namespace: str,
    go_task_queue: str,
    go_workflow_classname: str,
    juju_server_model: jubilant.Juju,
):
    """Test to ensure that the go workflow can be executed"""
    logger.info("Creating go workflow manually")

    random_keyword = "".join(random.choices(string.ascii_letters + string.digits, k=10))

    workflow_id = create_workflow(
        juju_server_model, go_namespace, go_task_queue, go_workflow_classname, random_keyword
    )

    logger.info("Ensuring only workflow exists")

    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=go_namespace
    )

    go_workflow_ids = []
    async for workflow in client.list_workflows():
        go_workflow_ids.append(workflow.id)

    assert workflow_id in go_workflow_ids, "Unable to find created workflow in all workflows"

    logger.info("Waiting until workflow completes")

    workflow_handle = client.get_workflow_handle(workflow_id)
    workflow_result = await workflow_handle.result()
    assert workflow_result == f"Hello world to {random_keyword} in go!", (
        "Unexpected result in activity of created workflow"
    )


@pytest.mark.dependency(depends=["test_python_workflow", "test_go_workflow"])
async def test_namespace_isolation(
    juju_server_model: jubilant.Juju, python_namespace: str, go_namespace: str
):
    """Ensure there is no overlap between workflows in python and go namespaces"""
    temporal_server_unit_ip = juju_server_model.status().apps["temporal-k8s"].address
    assert temporal_server_unit_ip != "", "Empty address for temporal-k8s application"

    logger.info("Retrieving all workflow ids in the python namespace")

    python_namespace_client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=python_namespace
    )

    python_workflow_ids = []
    async for workflow in python_namespace_client.list_workflows():
        python_workflow_ids.append(workflow.id)

    logger.info("Retrieving all workflow ids in the go namespace")

    go_namespace_client = await temporalio.client.Client.connect(
        f"{temporal_server_unit_ip}:7233", namespace=go_namespace
    )

    go_workflow_ids = []
    async for workflow in go_namespace_client.list_workflows():
        go_workflow_ids.append(workflow.id)

    logger.info("Ensuring no overlap between workflows in python and go namespaces")
    assert not set(python_workflow_ids).intersection(set(go_workflow_ids)), (
        "Workflow IDs in python and go namespaces not disjoint"
    )
