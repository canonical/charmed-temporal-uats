# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import jubilant


def create_workflow(
    juju: jubilant.Juju, namespace: str, task_queue: str, workflow_classname: str, input: str
) -> str:
    """Creates workflow using temporal-admin-k8s.

    Args:
        juju: jubilant.Juju client to the temporal server model
        namespace: temporal namespace to create workflow in
        task_queue: temporal task queue to use for the workflow
        workflow_classname: temporal workflow classname to invoke in the workflow
        input: input to provide to the temporal workflow
    Returns:
        Workflow ID that is created
    """
    action = juju.run(
        unit="temporal-admin-k8s/0",
        action="cli",
        params={
            "args": f'workflow start --namespace {namespace} --task-queue {task_queue} --type {workflow_classname} --input "{input}"',
        },
    )
    assert action.status == "completed", "Action to create workflow did not complete"
    assert action.results["result"] == "command succeeded", "Action to create workflow failed"

    action_output = action.results["output"]

    assert "WorkflowId" in action_output, "Unexpected output of command to create workflow"

    return [
        line.strip().split()
        for line in action.results["output"].split("\n")
        if "WorkflowId" in line
    ][0][1]
