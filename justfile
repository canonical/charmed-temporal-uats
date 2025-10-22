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

    rm -rf kuberenetes-ingress

    git clone https://github.com/nginx/kubernetes-ingress.git --branch v5.2.1
    cd kubernetes-ingress

    kubectl apply -f deployments/common/ns-and-sa.yaml
    kubectl apply -f deployments/rbac/rbac.yaml

    kubectl apply -f deployments/common/nginx-config.yaml
    kubectl apply -f deployments/common/ingress-class.yaml

    kubectl apply -f config/crd/bases/k8s.nginx.org_virtualservers.yaml
    kubectl apply -f config/crd/bases/k8s.nginx.org_virtualserverroutes.yaml
    kubectl apply -f config/crd/bases/k8s.nginx.org_transportservers.yaml
    kubectl apply -f config/crd/bases/k8s.nginx.org_policies.yaml
    kubectl apply -f config/crd/bases/k8s.nginx.org_globalconfigurations.yaml

    kubectl apply -f deployments/deployment/nginx-ingress.yaml

    until kubectl -n nginx-ingress get pods | grep -q nginx-ingress; do
        sleep 1
    done

    kubectl create -f deployments/service/nodeport.yaml

    cd ..
    rm -rf kubernetes-ingress

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
    juju add-model temporal-workers-uats-${suffix}
    juju add-model cos-uats-${suffix}

[private]
deploy-temporal-server model_suffix="fixed" temporal_channel="1.23/edge" postgresql_channel="14/stable" openfga_channel="3.0/stable":
    #!/usr/bin/bash
    juju switch temporal-server-uats-${model_suffix}

    juju deploy postgresql-k8s --channel "${postgresql_channel}" --trust

    juju deploy openfga-k8s --channel "${openfga_channel}"

    juju deploy temporal-k8s --channel "${temporal_channel}" \
        --config num-history-shards=1 \
        --config auth-enabled=true
    juju deploy temporal-admin-k8s --channel "${temporal_channel}"
    juju deploy temporal-ui-k8s --channel "${temporal_channel}" \
        --config tls-secret-name=""

    juju deploy nginx-ingress-integrator temporal-ui-ingress --trust \
        --config ingress-class=nginx \
        --config backend-protocol=HTTPS \
        --config service-hostname=temporal-ui-k8s

    juju deploy self-signed-certificates

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

    juju integrate openfga-k8s:database postgresql-k8s:database
    juju integrate temporal-k8s:openfga openfga-k8s:openfga

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

    # TODO: add juju wait-for to ensure temporal-k8s ready for openfga config

    trap 'rm -rf ./temporal-k8s-operator' EXIT

    just clone-temporal-k8s-repo

    juju wait-for application temporal-k8s --query='name == "temporal-k8s" && status == "blocked" && forEach(units, unit => unit.workload-message == "missing openfga authorization model")'

    juju run temporal-k8s/0 create-authorization-model model="$(<./temporal-k8s-operator/temporal_auth_model.json)" --string-args=true

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

    # trap 'just cleanup-models ${suffix} false' ERR

    just create-models ${suffix}

    just deploy-temporal-server ${suffix}
    just deploy-cos ${suffix}
    just deploy-workers localhost:5000/worker-python:dev localhost:5000/worker-go:dev ${suffix}

    just integrate-applications ${suffix}

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
uats-namespace-isolation server_model workers_model cos_model:
    #!/usr/bin/bash
    set -euxo pipefail

    tox -e uats-namespace-isolation -- \
        --server-model="${server_model}" \
        --workers-model="${workers_model}" \
        --cos-model="${cos_model}"

uats-ingress server_model workers_model cos_model:
    #!/usr/bin/bash
    set -euxo pipefail

    tox -e uats-ingress -- \
        --server-model="${server_model}" \
        --workers-model="${workers_model}" \
        --cos-model="${cos_model}"

# Execute all UATs
uats server_model workers_model cos_model:
    just uats-namespace-isolation ${server_model} ${workers_model} ${cos_model}
    just uats-ingress ${server_model} ${workers_model} ${cos_model}
