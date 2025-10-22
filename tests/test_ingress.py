# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import jubilant
import logging
import requests
import tempfile

logger = logging.getLogger(__name__)


def test_tls_connection_to_ui_via_ingress(juju_server_model: jubilant.Juju):
    """Test access to Temporal UI with TLS via ingress."""

    with tempfile.NamedTemporaryFile() as ca_cert_file:
        action = juju_server_model.run(
            unit="self-signed-certificates/0",
            action="get-ca-certificate",
        )
        assert action.status == "completed", "Action to retrieve ca certificate did not complete"

        ca_cert_file.write(action.results["ca-certificate"].encode("utf-8"))
        ca_cert_file.write("\n".encode("utf-8"))
        ca_cert_file.flush()

        # inline import to scope below DNS resolution hack to this test
        import urllib3

        urllib3.connection.HTTPConnection.host = ""
        urllib3.connection.HTTPConnection._dns_host = "10.1.0.83"

        response = requests.get("https://temporal-ui-k8s", verify=ca_cert_file.name)

        response.raise_for_status()

        assert "svelte" in response.text.lower(), (
            "Unable to find keyword 'svelte' in Temporal UI response"
        )
