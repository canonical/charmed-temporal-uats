# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import jubilant

logger = logging.getLogger(__name__)


def start_workflow(
    juju: jubilant.Juju,
    namespace: str,
    task_queue: str,
    workflow_classname: str,
    input: str = "",
) -> str:
    """Start a workflow execution using temporal-admin-k8s.

    Args:
        juju: jubilant.Juju client to the temporal server model
        namespace: temporal namespace to execute the workflow in
        task_queue: the name of the task queue that the workflow execution's tasks will be placed on
        workflow_classname: temporal workflow classname to invoke in the workflow
        input: (optional) input to provide to the temporal workflow
    Returns:
        (Workflow ID, Run ID) for the started run of the workflow
    """
    action = juju.run(
        unit="temporal-admin-k8s/0",
        action="cli",
        params={
            "args": f"""workflow start --namespace {namespace} --task-queue {task_queue} --type {workflow_classname} {f'--input "{input}"' if input else ""}""".strip(),
        },
    )
    assert action.status == "completed", "Action to start workflow did not complete"
    assert action.results["result"] == "command succeeded", "Action to start workflow failed"

    action_output = action.results["output"]

    assert "RunId" in action_output and "WorkflowId" in action_output, (
        "Unexpected output of command to start workflow"
    )

    workflow_id = [
        line.strip().split()
        for line in action.results["output"].split("\n")
        if "WorkflowId" in line
    ][0][1]

    run_id = [
        line.strip().split() for line in action.results["output"].split("\n") if "RunId" in line
    ][0][1]

    return workflow_id, run_id
