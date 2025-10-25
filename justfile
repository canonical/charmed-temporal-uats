set export # Just variables are exported to environment variables

[private]
default:
    just --list

[private]
clean:
    rm -rf ./temporal-k8s-operator/
    rm ./worker_python/*.rock
    rm ./worker_go/*.rock

[private]
stop-local-registry:
    docker stop registry || true
    docker rm registry || true

[private]
start-local-registry:
    docker start registry || docker run -d -p 5000:5000 --name registry registry:2.7

[private]
push-to-local-registry rock_filepath registry tag: (start-local-registry)
    rockcraft.skopeo --insecure-policy copy --dest-tls-verify=false \
        "oci-archive:${rock_filepath}" \
        "docker://localhost:5000/${registry}:${tag}"

[private]
clone-temporal-k8s-repo branch="track/1.23":
    rm -rf ./temporal-k8s-operator
    git clone --branch ${branch} --single-branch https://github.com/canonical/temporal-k8s-operator.git temporal-k8s-operator

[private]
install-nginx-controller:
    #!/usr/bin/bash
    set -euxo pipefail

    if [ "$(kubectl get ingressclass | grep nginx | wc -l)" = "1" ]; then
        echo "nginx ingress controller already installed"
        exit 0
    fi

    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/refs/tags/controller-v1.13.3/deploy/static/provider/cloud/deploy.yaml

    until [[ $(kubectl -n ingress-nginx get svc | grep -E 'ingress-nginx-controller\s' | awk '{print $4}') =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] ; do
        echo "Waiting for ingress controller to be assigned an external ip"
        sleep 5
    done

[private]
cleanup-models suffix="" cleanup_all_uat_models="true":
    #!/usr/bin/bash
    set -x

    if [ "${cleanup_all_uat_models}" = "true" ]; then
        for model in $(juju models | grep "uats" | awk '{print $1}' | sed s/*//); do
            juju destroy-model --destroy-storage --no-prompt --force ${model} || true
        done
    else
        juju destroy-model --destroy-storage --no-prompt --force temporal-server-uats-${suffix} || true
        juju destroy-model --destroy-storage --no-prompt --force temporal-workers-uats-${suffix} || true
        juju destroy-model --destroy-storage --no-prompt --force cos-uats-${suffix} || true
    fi

[private]
create-models suffix="fixed" cleanup_all_uat_models="true":
    just cleanup-models ${suffix} ${cleanup_all_uat_models}

    juju add-model temporal-server-uats-${suffix}
    juju model-config update-status-hook-interval=10s

    juju add-model temporal-workers-uats-${suffix}
    juju model-config update-status-hook-interval=10s

    juju add-model cos-uats-${suffix}
    juju model-config update-status-hook-interval=10s

[private]
destroy-server-model:
    juju destroy-model --force --destroy-storage --no-prompt "temporal-server-uats-$(just get-model-suffix)"

[private]
destroy-workers-model:
    juju destroy-model --force --destroy-storage --no-prompt "temporal-workers-uats-$(just get-model-suffix)"

[private]
destroy-cos-model:
    juju destroy-model --force --destroy-storage --no-prompt "cos-uats-$(just get-model-suffix)"

[parallel]
[private]
destroy-all-models: destroy-server-model destroy-workers-model destroy-cos-model

[private]
deploy-temporal-server model_suffix="fixed" temporal_channel="1.23/edge" postgresql_channel="14/stable" nginx_ingress_integrator_channel="latest/stable" self_signed_certificates_channel="1/stable":
    #!/usr/bin/bash
    juju switch temporal-server-uats-${model_suffix}

    juju deploy postgresql-k8s --channel "${postgresql_channel}" --trust

    juju deploy temporal-k8s --channel "${temporal_channel}" \
        --config num-history-shards=1 \
        --config auth-enabled=false
    juju deploy temporal-admin-k8s --channel "${temporal_channel}"
    juju deploy temporal-ui-k8s --channel "${temporal_channel}" \
        --config tls-secret-name=""

    juju deploy nginx-ingress-integrator temporal-ui-ingress \
        --channel "${nginx_ingress_integrator_channel}" --trust \
        --config ingress-class=nginx \
        --config backend-protocol=HTTP \
        --config service-hostname=temporal-ui-k8s

    juju deploy self-signed-certificates --channel "${self_signed_certificates_channel}"

[private]
deploy-cos model_suffix="fixed" cos_channel="latest/stable":
    juju deploy --model cos-uats-${model_suffix} cos-lite --channel="${cos_channel}" --trust

    juju offer cos-uats-${model_suffix}.grafana:grafana-dashboard
    juju offer cos-uats-${model_suffix}.loki:logging
    juju offer cos-uats-${model_suffix}.prometheus:metrics-endpoint
    # TODO: add tracing

# TODO: change 1.0/edge -> 1.0/stable
[private]
deploy-workers worker_python_image worker_go_image model_suffix="fixed" worker_channel="1.0/edge":
    #!/usr/bin/bash
    juju switch temporal-workers-uats-${model_suffix}

    juju deploy temporal-worker-k8s temporal-worker-k8s-python \
        --channel ${worker_channel} \
        --resource temporal-worker-image=${worker_python_image} \
        --config host=temporal-k8s.temporal-server-uats-${model_suffix}:7233 \
        --config queue=worker-python-queue \
        --config namespace=worker-python-namespace
    juju deploy temporal-worker-k8s temporal-worker-k8s-go \
        --channel ${worker_channel} \
        --resource temporal-worker-image=${worker_go_image} \
        --config host=temporal-k8s.temporal-server-uats-${model_suffix}:7233 \
        --config queue=worker-go-queue \
        --config namespace=worker-go-namespace

[private]
integrate-applications model_suffix="fixed":
    #!/usr/bin/bash

    juju switch temporal-server-uats-${model_suffix}

    # Integrate charms within temporal-server-uats model
    juju integrate temporal-k8s:db postgresql-k8s:database
    juju integrate temporal-k8s:visibility postgresql-k8s:database

    juju integrate temporal-k8s:admin temporal-admin-k8s:admin

    juju integrate temporal-k8s:ui temporal-ui-k8s:ui

    juju integrate temporal-ui-ingress:certificates self-signed-certificates:certificates

    juju integrate temporal-ui-k8s:nginx-route temporal-ui-ingress:nginx-route

    # Consume cos-uat offers in temporal-server-uats model
    juju consume admin/cos-uats-${model_suffix}.grafana
    juju consume admin/cos-uats-${model_suffix}.loki
    juju consume admin/cos-uats-${model_suffix}.prometheus

    # Integrate Temporal charms with COS
    juju integrate temporal-k8s:grafana-dashboard grafana
    juju integrate temporal-k8s:logging loki
    juju integrate temporal-k8s:metrics-endpoint prometheus

    juju switch temporal-workers-uats-${model_suffix}

    # Consume cos-uat offers in temporal-workers-uats model
    juju consume admin/cos-uats-${model_suffix}.grafana
    juju consume admin/cos-uats-${model_suffix}.loki
    juju consume admin/cos-uats-${model_suffix}.prometheus

    # Integrate Temporal python worker charm with COS
    juju integrate temporal-worker-k8s-python:metrics-endpoint prometheus
    juju integrate temporal-worker-k8s-python:logging loki
    juju integrate temporal-worker-k8s-python:grafana-dashboard grafana

[private]
create-namespaces:
    #!/usr/bin/bash
    juju switch "temporal-server-uats-$(just get-model-suffix)"

    juju wait-for application temporal-admin-k8s --query='name == "temporal-admin-k8s" && status == "active"'

    juju run temporal-admin-k8s/0 cli args="operator namespace create --namespace worker-go-namespace --retention 3d" --wait 1m
    juju run temporal-admin-k8s/0 cli args="operator namespace create --namespace worker-python-namespace --retention 3d" --wait 1m

# Pack the python worker image
pack-worker-python debug="":
    #!/usr/bin/bash
    set -x

    debug_options=$(if [ -n "${debug}" ]; then echo "--debug"; fi)
    cd worker_python && rockcraft pack ${debug_options}

pack-worker-go debug="":
    #!/usr/bin/bash
    set -x

    debug_options=$(if [ -n "{debug}" ]; then echo "--debug"; fi)
    cd worker_go && rockcraft pack ${debug_options}

# Lint source code
lint:
    tox -e lint

# Format source code
format:
    tox -e format

# Deploy the Temporal applications for UATs
deploy-temporal:
    #!/usr/bin/bash
    set -euxo pipefail

    just pack-worker-python
    worker_python_rock_filepath=$(ls -d "$PWD"/worker_python/* | grep "\.rock")

    just pack-worker-go
    worker_go_rock_filepath=$(ls -d "$PWD"/worker_go/* | grep "\.rock")

    just stop-local-registry
    just push-to-local-registry ${worker_python_rock_filepath} worker-python dev
    just push-to-local-registry ${worker_go_rock_filepath} worker-go dev

    suffix=$(head /dev/urandom | tr -dc a-z0-9 | head -c 10)

    just create-models ${suffix}

    just deploy-temporal-server ${suffix}
    just deploy-cos ${suffix}
    just deploy-workers localhost:5000/worker-python:dev localhost:5000/worker-go:dev ${suffix}

    just integrate-applications ${suffix}

    just create-namespaces

# Get model suffix for UAT models
get-model-suffix:
    #!/usr/bin/bash
    set -euo pipefail

    model_suffixes=$(juju models | grep uats | awk '{print $1}' | sed s/*//g | rev | cut -d- -f1 | rev | sort -u)

    if [ "$(echo \"${model_suffixes} | wc -l)" != "1" ]; then
        exit 1;
    fi

    echo "${model_suffixes}"

# Execute namespace isolation UATs
uats-namespace-isolation server_model="" workers_model="" cos_model="":
    #!/usr/bin/bash
    set -euxo pipefail

    goss validate --retry-timeout=900s --sleep 60s --color

    model_suffix=$(just get-model-suffix)

    tox -e uats-namespace-isolation -- \
        --server-model="${server_model:-temporal-server-uats-${model_suffix}}" \
        --workers-model="${workers_model:-temporal-workers-uats-${model_suffix}}" \
        --cos-model="${cos_model:-cos-uats-${model_suffix}}"

uats-ingress server_model="" workers_model="" cos_model="":
    #!/usr/bin/bash
    set -euxo pipefail

    goss validate --retry-timeout=900s --sleep 60s --color

    model_suffix=$(just get-model-suffix)

    tox -e uats-ingress -- \
        --server-model="${server_model:-temporal-server-uats-${model_suffix}}" \
        --workers-model="${workers_model:-temporal-workers-uats-${model_suffix}}" \
        --cos-model="${cos_model:-cos-uats-${model_suffix}}"

uats-cos server_model="" workers_model="" cos_model="":
    #!/usr/bin/bash
    set -euxo pipefail

    model_suffix=$(just get-model-suffix)

    juju run --model "temporal-server-uats-${model_suffix}" temporal-admin-k8s/0 \
        cli \
        args='workflow start --namespace worker-python-namespace --task-queue worker-python-queue --type HelloWorldWorkflow --input "test-cos"' --wait 1m


    goss --gossfile goss.yaml --gossfile cos.goss.yaml validate --retry-timeout=900s --sleep 60s --color

    tox -e uats-cos -- \
        --server-model="${server_model:-temporal-server-uats-${model_suffix}}" \
        --workers-model="${workers_model:-temporal-workers-uats-${model_suffix}}" \
        --cos-model="${cos_model:-cos-uats-${model_suffix}}"

# Execute all UATs
uats server_model="" workers_model="" cos_model="":
    just uats-namespace-isolation ${server_model} ${workers_model} ${cos_model}
    just uats-ingress ${server_model} ${workers_model} ${cos_model}
    just uats-cos ${server_model} ${workers_model} ${cos_model}

get-system-state:
    #!/usr/bin/bash

    df -h
    echo "---"

    model_suffix=$(just get-model-suffix)

    juju status --model "temporal-server-uats-${model_suffix}" --color --relations --storage
    echo "---"

    juju status --model "temporal-workers-uats-${model_suffix}" --color --relations --storage
    echo "---"

    juju status --model "cos-uats-${model_suffix}" --color --relations --storage
    echo "---"

    sudo k8s status
    echo "---"
