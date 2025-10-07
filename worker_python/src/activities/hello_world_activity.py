# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
import temporalio


@dataclasses.dataclass
class HelloWorldInput:
    greeted: str


# Basic activity that logs and does string concatenation
@temporalio.activity.defn(name="compose_hello_world")
async def compose_hello_world(arg: HelloWorldInput) -> str:
    temporalio.activity.logger.info("Running activity with parameter %s" % arg)

    return f"Hello World to {arg.greeted} in python"
