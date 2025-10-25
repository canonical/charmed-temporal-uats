# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import jubilant
import requests

logger = logging.getLogger(__name__)


def test_temporal_alerts_created(cos_model: jubilant.Juju):
    """Test to ensure Temporal alerts created in COS."""
    prometheus_unit_ip_address = cos_model.status().get_units("prometheus")["prometheus/0"].address
    assert prometheus_unit_ip_address != "", "Empty prometheus unit IP address"

    alerts_query_url = f"http://{prometheus_unit_ip_address}:9090/api/v1/rules?type=alert"

    response = requests.get(alerts_query_url)

    response.raise_for_status()
    response_data = response.json()

    temporal_alert_group = [
        group
        for group in response_data["data"]["groups"]
        if group["name"].startswith("temporal_server_uats_")
    ][0]

    temporal_alert_rules = temporal_alert_group["rules"]
    assert len(temporal_alert_rules) > 0, "No available temporal alert rules"

    temporal_alert_rule_names = [rule["name"] for rule in temporal_alert_rules]
    assert "TemporalServerDown" in temporal_alert_rule_names, (
        "TemporalServerDown alert rule missing"
    )
    assert "TemporalDatabaseDown" in temporal_alert_rule_names, (
        "TemporalDatabaseDown alert rule missing"
    )

    assert all([rule["state"] == "inactive" for rule in temporal_alert_rules]), (
        "Some temporal alert rules are active"
    )


def test_temporal_server_dashboard_created(cos_model: jubilant.Juju):
    """Test to ensure Temporal dashboard created in COS."""
    grafana_unit_ip_address = cos_model.status().get_units("grafana")["grafana/0"].address
    assert grafana_unit_ip_address != "", "Empty grafana unit IP address"

    action = cos_model.run(
        unit="grafana/0",
        action="get-admin-password",
    )
    assert action.status == "completed", "Action to get grafana admin password did not complete"

    grafana_admin_password = action.results["admin-password"]
    assert grafana_admin_password != "", "Empty grafana admin password"

    dashboards_list_url = (
        f"http://admin:{grafana_admin_password}@{grafana_unit_ip_address}:3000/api/search"
    )

    response = requests.get(dashboards_list_url)

    response.raise_for_status()
    response_data = response.json()

    assert (
        len([
            dashboard["title"]
            for dashboard in response_data
            if dashboard["title"] == "Temporal Server Metrics"
        ])
        == 1
    ), "Missing Temporal Server Metrics dashboard"

    assert (
        len([
            dashboard["title"]
            for dashboard in response_data
            if dashboard["title"] == "Temporal Worker SDK Metrics"
        ])
        == 1
    ), "Missing Temporal Worker SDK Metrics dashboard"


def test_temporal_metrics_exist(cos_model: jubilant.Juju):
    """Test to ensure Temporal metrics exist in COS."""
    prometheus_unit_ip_address = cos_model.status().get_units("prometheus")["prometheus/0"].address
    assert prometheus_unit_ip_address != "", "Empty prometheus unit IP address"

    metrics_list_url = f"http://{prometheus_unit_ip_address}:9090/api/v1/label/__name__/values"

    response = requests.get(metrics_list_url)

    response.raise_for_status()
    response_data = response.json()

    assert (
        len([metric for metric in response_data["data"] if metric.startswith("temporal_")]) > 0
    ), "Missing temporal metrics"
    assert (
        len([
            metric
            for metric in response_data["data"]
            if metric.startswith("visibility_persistence_")
        ])
        > 0
    ), "Missing visibility persistence metrics"
    assert (
        len([metric for metric in response_data["data"] if metric.startswith("workflow_")]) > 0
    ), "Missing workflow metrics"
    assert (
        len([metric for metric in response_data["data"] if metric.startswith("activity_")]) > 0
    ), "Missing activity metrics"

    assert (
        len([
            metric
            for metric in response_data["data"]
            if metric.startswith("custom_activity_schedule_to_start_")
        ])
        > 0
    ), "Missing worker workflow metrics"


def test_temporal_log_stream_exists(cos_model: jubilant.Juju):
    """Test to ensure Temporal log stream exists in COS."""
    loki_unit_ip_address = cos_model.status().get_units("loki")["loki/0"].address
    assert loki_unit_ip_address != "", "Empty loki unit IP address"

    loki_list_streams_url = f"http://{loki_unit_ip_address}:3100/loki/api/v1/series"

    response = requests.get(loki_list_streams_url)

    response.raise_for_status()
    response_data = response.json()

    temporal_server_stream = [
        stream for stream in response_data["data"] if stream.get("charm") == "temporal-k8s"
    ][0]

    assert temporal_server_stream["pebble_service"] == "temporal-server", (
        "Unexpected pebble service in temporal server loki stream"
    )
    assert temporal_server_stream["juju_unit"] == "temporal-k8s/0", (
        "Unexpected unit name in temporal server loki stream"
    )
    assert temporal_server_stream["juju_application"] == "temporal-k8s", (
        "Unexpected application name in temporal server loki stream"
    )

    temporal_worker_python_stream = [
        stream
        for stream in response_data["data"]
        if stream.get("charm") == "temporal-worker-k8s"
        and stream.get("juju_application") == "temporal-worker-k8s-python"
    ][0]

    assert temporal_worker_python_stream["pebble_service"] == "temporal-worker", (
        "Unexpected pebble service in temporal worker python loki stream"
    )
    assert temporal_server_stream["juju_unit"] == "temporal-worker-k8s-python/0", (
        "Unexpected unit name in temporal worker python loki stream"
    )
