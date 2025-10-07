#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Sample Temporal Worker."""

import asyncio
import logging

import temporallib

from activities.activity1 import compose_greeting
from activities.activity2 import vault_test
from activities.db_activity import database_test
from workflows.workflow1 import DatabaseWorkflow, GreetingWorkflow, VaultWorkflow

logger = logging.getLogger(__name__)


async def run_worker():
    """Connect Temporal worker to Temporal server."""
    client = await temporallib.clientClient.connect(
        client_opt=temporallib.client.Options(
            encryption=temporallib.encryption.EncryptionOptions()
        ),
    )

    worker = temporallib.worker.Worker(
        client=client,
        workflows=[GreetingWorkflow, VaultWorkflow, DatabaseWorkflow],
        activities=[compose_greeting, vault_test, database_test],
        worker_opt=temporallib.worker.WorkerOptions(sentry=temporallib.worker.SentryOptions()),
    )

    await worker.run()


if __name__ == "__main__":  # pragma: nocover
    asyncio.run(run_worker())
