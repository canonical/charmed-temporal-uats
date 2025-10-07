# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import temporalio

import datetime


with temporalio.workflow.unsafe.imports_passed_through():
    import activities.hello_world_activity as hello_world_activities


# Basic workflow that logs and invokes an activity
@temporalio.workflow.defn(name="HelloWorldWorkflow")
class HelloWorldWorkflow:
    @temporalio.workflow.run
    async def run(self, name: str) -> str:
        temporalio.workflow.logger.info("Running HelloWorld workflow with parameter %s" % name)
        return await temporalio.workflow.execute_activity(
            hello_world_activities.compose_hello_world,
            hello_world_activities.ComposeGreetingInput("UATs"),
            start_to_close_timeout=datetime.timedelta(seconds=10),
        )
