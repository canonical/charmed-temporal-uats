# Charmed Temporal UATs

Automated User Acceptance Tests (UATs) are provide a mechanism to validate a set of assertions on a deployed Charmed Temporal. Such a validation can help instill confidence in the stability of the deployment and can effectively be used as a pre-flight check before Temporal clients start using the deployment.

Charmed Temporal UATs are implemented as pytests. This repository surfaces a `justfile` that encapsulates targets to invoke individual categories of tests on a deployed Charmed Temporal. Furthermore, there are also targets which can be used in a test environment to deploy Charmed Temporal locally before executing the UAT.

**Note**: we intend to iterate on the UAT execution framework to make the experience of testing on an existing Charmed Temporal deployment smoother, more configurable and more friendly.
## Available UAT Categories

1. Temporal namespace isolation: Will start workflow runs in workers that are configured in separate Temporal namespaces. Assertions ensure workflows and their runs are scoped to the namespace they belong to.
2. Ingress: Will ensure that it is possible to access Temporal UI via Ingress (nginx) that is configured to use TLS.
3. Canonical Observability Stack: Will ensure that Temporal server {metrics,alerts,dashboards,logs} are present in integrated COS. Also ensure Temporal worker {metrics,dashboards,logs} are present in integrated COS.

## Dependency Requirements

Python >= 3.10, < 3.13
Juju >= 3.6

1. juju
2. k8s (registered as a cloud on juju) with load-balancer and ingress enabled
3. kubectl
4. just
5. rockcraft
6. jq
7. goss
8. uv

## Testing Architecture

We have `just` targets to deploy Charmed Temporal in 3 models (Temporal Server, Temporal Workers, and COS).

For each UAT, we use `goss` to implement pre-flight checks before UATs are executed. We use uv + tox to create virtual environments for the UATs. Each UAT is implemented as a pytest, and utilizes frameworks like `jubilant` and `lightkube` to interact with the underlying juju and k8s.
## Executing UATs

Starting from a fresh environment:

```bash
sudo -E concierge prepare -p k8s --extra-snaps=astral-uv
sudo k8s set load-balancer.l2-mode=true load-balancer.cdrs=10.2.0.0/24
sudo k8s enable ingress load-balancer
sudo k8s kubectl config view --raw > ~/.kube/config
just install-nginx-controller
just deploy-temporal
just uats-{namespace-isolation,ingress,cos}
```
