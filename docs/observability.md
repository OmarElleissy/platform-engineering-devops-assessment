# Observability and SRE design

## Scope and stack

This is a cloud-neutral reference design for the frontend, backend API, and
PostgreSQL platform described in the [private network design](network-design.md).
It has not been deployed. The goal is to answer four questions quickly: Is the
service available? Is it fast enough? Where are requests failing? Which resource
is approaching saturation?

The selected stack is:

- OpenTelemetry SDKs and automatic instrumentation for application metrics,
  traces, and context propagation;
- an OpenTelemetry Collector gateway in each Kubernetes cluster for batching,
  filtering, redaction, and authenticated export;
- Prometheus-compatible metrics stored in Grafana Mimir;
- structured logs stored in Grafana Loki;
- distributed traces stored in Grafana Tempo; and
- Grafana for dashboards, alert rules, and links between metrics, logs, and
  traces.

The components may be self-hosted or replaced by compatible managed services.
The telemetry contract—OpenTelemetry protocols, metric names, structured log
fields, and alert semantics—should remain portable. Collectors communicate over
private endpoints and encrypted OTLP; telemetry backends have no public ingest
endpoint.

## Service-level objectives

Start with two user-facing service-level indicators measured at the frontend
ingress, where the user's outcome is visible:

- **Availability:** proportion of valid requests that do not return a platform
  or server error. Exclude deliberate client errors such as malformed `4xx`
  requests, but count throttling caused by insufficient service capacity.
- **Latency:** proportion of successful interactive requests completed within
  the agreed threshold.

A reasonable initial objective for this assessment design is 99.9 percent
monthly availability and 95 percent of successful interactive requests below
500 ms, with a secondary p99 threshold of 1.5 seconds. These are proposed
targets, not measured commitments. Once real traffic exists, the product owner
and SRE team should revise thresholds from user expectations and observed
baselines.

Use multi-window burn-rate alerts against the availability SLO instead of
paging on every isolated error. A fast-burn alert catches severe failures over
5 minutes and 1 hour; a slow-burn alert catches sustained degradation over 6
hours and 3 days. Planned maintenance is handled through explicit maintenance
windows, not by deleting data or silently changing the SLO query.

## Metrics: rate, errors, latency, and saturation

Every HTTP service emits a low-cardinality RED metric set:

- **Rate:** `http.server.request.duration` count, grouped by service, route
  template, method, and status-code class. Never use raw URL, user ID, request
  ID, or database key as a metric label.
- **Errors:** server errors, handled application errors, timeouts, dependency
  failures, and rejected/throttled requests. Distinguish caller `4xx` from
  service-owned failures.
- **Duration:** histogram buckets appropriate to the SLO, allowing p50, p95,
  p99, and threshold compliance to be calculated centrally.

Infrastructure uses the USE method:

- **Utilization:** pod and node CPU, memory working set, network throughput,
  connection-pool use, PostgreSQL CPU/storage/connection use, and private-link
  bandwidth.
- **Saturation:** CPU throttling, run queue, memory pressure, pod pending time,
  connection-pool waiters, PostgreSQL locks, storage queue depth, BGP/link
  capacity, and collector export queue occupancy.
- **Errors:** container restarts, OOM kills, node conditions, failed scheduling,
  load-balancer unhealthy targets, DNS failures, dropped network flows,
  PostgreSQL failovers, and telemetry export failures.

Key workload metrics include Kubernetes desired/available replicas, rollout
status, HPA current/desired replicas, pod restart rate, ingress response codes,
AKS/EKS node readiness, and persistent-volume capacity. PostgreSQL adds query
latency, transactions, deadlocks, active versus maximum connections,
replication lag, cache-hit ratio, storage remaining, and backup/restore status.
Slow-query collection must normalize statements and remove literal values.

Synthetic probes run from at least one private location in each cloud. They test
DNS resolution, TLS, frontend health, the frontend-to-API path, and a harmless
read-only business transaction. `/health` process checks are useful for
orchestration but do not replace the end-to-end synthetic transaction.

## Dashboards

### Executive service dashboard

This page is small and outcome-focused. It shows current availability, SLO
target, remaining error budget, request volume, p95/p99 latency, error rate, and
active customer-impacting incidents. A 30-day view shows SLO trend and release
markers. It avoids pod counts and cloud-specific implementation details. The
audience is product, engineering leadership, incident command, and service
owners.

### Application dashboard

The application view follows a request across the system:

- request rate and status classes by frontend/backend route template;
- latency heatmaps and p50/p95/p99 by service and route;
- error type, timeout, retry, and dependency-failure rate;
- frontend-to-backend and backend-to-PostgreSQL client spans;
- current version/full Git SHA, deployment time, and rollout markers;
- top normalized slow operations and connection-pool wait;
- links from a metric exemplar to its trace, then to logs sharing the trace ID.

Release comparison panels show the current and previous version without using
commit SHA as an unbounded metric dimension. The value belongs in resource
attributes, dashboard variables, logs, and traces.

### Infrastructure dashboard

The infrastructure view is organized by dependency rather than cloud console:

- EKS and AKS capacity, ready nodes, unschedulable pods, restarts, CPU
  throttling, memory pressure, and HPA behavior;
- internal load-balancer request rate, target health, connection errors, and
  response time;
- Transit Gateway, ExpressRoute/Virtual WAN, packet loss, BGP session state,
  bytes, drops, and private DNS response/error rates;
- PostgreSQL CPU, memory, storage, IOPS, connections, locks, lag, and backup
  freshness; and
- OpenTelemetry Collector receive/export failures, queue utilization, dropped
  spans/logs, and backend ingestion health.

Each panel links to a runbook and names its owner. Dashboards are versioned as
code and reviewed with application changes.

## Structured logging and correlation

Applications log one JSON object per event to stdout/stderr. The collector adds
Kubernetes and cloud resource attributes. The base schema is:

```json
{
  "timestamp": "2026-01-01T00:00:00.000Z",
  "severity": "INFO",
  "service.name": "backend-api",
  "service.version": "full-git-sha",
  "deployment.environment": "production",
  "event.name": "http.request.completed",
  "http.request.method": "GET",
  "http.route": "/orders/{order_id}",
  "http.response.status_code": 200,
  "duration_ms": 42,
  "trace_id": "otel-trace-id",
  "span_id": "otel-span-id",
  "correlation_id": "validated-request-id"
}
```

At the first trusted ingress, accept a syntactically valid external request ID
or generate a new opaque correlation ID. Propagate W3C `traceparent` and
`tracestate` plus the correlation ID through frontend, backend, and asynchronous
work. Never use a correlation ID for authentication or expose internal trace
details as authorization decisions.

Logs must not contain access tokens, cookies, authorization headers, passwords,
database connection strings, Terraform state, raw request/response bodies, or
personal data unless a reviewed business need and redaction policy exists. The
collector performs a second redaction pass and drops prohibited fields before
export. Sampling applies primarily to successful traces; errors and high-
latency traces receive priority. Audit/security events use a separate protected
stream with stricter access and retention.

Proposed retention is 30 days searchable for application and platform logs, 13
months archived for approved audit events, 30 days for full-resolution metrics,
13 months for downsampled SLO metrics, and 14 days for traces. Legal, privacy,
incident-response, and cost requirements must approve these values before
deployment. Storage encryption, tenant isolation, RBAC, and access auditing are
mandatory.

## Alerts and response

Alerts should indicate an actionable symptom, name an owner, link to a runbook,
and include safe dashboard context. Notifications contain no credentials,
customer data, or raw log bodies.

| Alert | Initial condition | Severity and action |
|---|---|---|
| Availability fast burn | Error-budget burn above 14.4× over both 5m and 1h | Page service owner; assess rollback, dependency and routing health |
| Availability slow burn | Burn above 2× over both 6h and 3d | Ticket/on-call notification; investigate before budget exhaustion |
| Latency | p95 above 500 ms for 10m with meaningful traffic, or p99 above 1.5s | Page if user-impacting; inspect route, dependency spans and saturation |
| Error rate | Service-owned `5xx`, timeouts and throttling above 2% for 10m | Page; correlate with release, target health and dependencies |
| No traffic | Expected service has zero requests and synthetic checks fail for 5m | Page; verify DNS, load balancer, routes and deployment |
| Kubernetes availability | Available replicas below desired for 10m or rollout stuck | Page for production; inspect scheduling, image pull and probes |
| Resource saturation | CPU throttling, memory pressure, connection pool, or DB connections above 85% for 15m | Warn, then page at 95% or on errors; scale or remove bottleneck |
| PostgreSQL risk | Storage below 20%, replication lag above threshold, backup stale, or failover | Page database owner; follow database runbook |
| Private connectivity | BGP path down, packet loss, or both cross-cloud paths unavailable | Warn on one path; page immediately on loss of both paths |
| Telemetry pipeline | Collector drops/export failures or queue above 80% for 10m | Page observability owner because monitoring confidence is degraded |

Thresholds require a minimum request count to prevent noisy percentages at low
volume. Alerts are tested through controlled exercises: inject an application
error, stop a pod, withdraw one network path, exhaust a test connection pool,
and verify routing, notification, runbook, and recovery. Alert changes receive
the same code review as production changes.

## Ownership and implementation sequence

The service team owns application instrumentation, SLOs, and application
runbooks. The platform team owns collectors, Kubernetes signals, telemetry
backends, and shared dashboards. Network and database teams own their exporters,
alerts, and recovery procedures. Incident command owns cross-team escalation.

A practical rollout is: establish the logging schema and resource attributes;
deploy collectors privately; ingest RED/USE metrics; build the three dashboards;
validate trace/log correlation; agree SLOs; then enable alerts in warning mode
before paging. This sequence prevents an untested alert set from becoming the
only operational control. No part of this document claims those steps are
currently deployed.
