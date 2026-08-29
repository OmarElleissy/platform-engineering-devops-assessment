# Private multi-cloud network design

## Purpose and design principles

This reference design connects a frontend running on Amazon EKS to a backend API
running on Azure AKS and PostgreSQL in Azure. Application traffic has no public
endpoint: users enter from an enterprise private network, both Kubernetes
ingresses are internal, and the database is reachable only through Azure
private networking. The design is intentionally independent from the small ECS
assessment environment and has not been deployed.

The principal design choices are:

- non-overlapping address space allocated centrally before any cluster exists;
- two private cross-cloud links with dynamic routing rather than internet VPN as
  the normal path;
- regional transit hubs so application VPCs/VNets do not form a peering mesh;
- split-horizon private DNS with resolvers in each cloud;
- identity, Kubernetes NetworkPolicy, security groups/NSGs, and TLS in addition
  to routing controls; and
- no direct path from the frontend to PostgreSQL.

The companion [network diagram](network-diagram.png) summarizes the topology.

## Topology and address plan

The examples reserve space that can be summarized cleanly at the transit
boundary. They must be replaced by allocations from the organization's IP
address management system before implementation.

| Zone | Example CIDR | Purpose |
|---|---:|---|
| AWS application VPC | `10.40.0.0/16` | EKS nodes, VPC-CNI pods, internal load balancers, and resolver endpoints |
| AWS transit subnets | `10.40.0.0/24` | Transit Gateway attachments in three availability zones |
| AWS EKS node/pod subnets | `10.40.16.0/20`, `10.40.32.0/20`, `10.40.48.0/20` | One private subnet per availability zone |
| AWS internal-ingress subnets | `10.40.64.0/24`, `10.40.65.0/24`, `10.40.66.0/24` | Internal NLB/ALB addresses only |
| AWS Route 53 Resolver subnets | `10.40.80.0/28`, `10.40.80.16/28` | Inbound and outbound endpoints |
| Azure hub VNet | `10.50.0.0/20` | Virtual WAN hub connection, firewall, and DNS resolver |
| Azure AKS spoke VNet | `10.51.0.0/16` | AKS nodes and internal API load balancer |
| Azure PostgreSQL VNet | `10.52.0.0/20` | Delegated database or private-endpoint subnet |
| EKS service CIDR | `172.20.0.0/16` | Cluster-internal virtual services; not advertised |
| AKS service CIDR | `172.21.0.0/16` | Cluster-internal virtual services; not advertised |
| AKS overlay pod CIDR | `10.244.0.0/16` | Non-routed overlay addresses; nodes perform routing/NAT as designed |

Only routable VPC/VNet prefixes are exchanged across clouds. Kubernetes service
CIDRs and the AKS overlay pod CIDR remain local to their clusters. EKS uses the
VPC CNI, so its pod addresses come from the EKS subnets; security policy should
target pod security groups where supported rather than assuming every packet is
identifiable only by a node address.

The AWS application VPC attaches to an AWS Transit Gateway through a dedicated
subnet in each availability zone. The Azure AKS and PostgreSQL spoke VNets
connect to an Azure Virtual WAN secured hub. Spoke-to-spoke traffic is inspected
through Azure Firewall according to the hub route table; direct VNet peering
bypasses are not permitted.

## Selected private connectivity

The preferred connection is a managed network-provider fabric with two
independent physical paths. Each path presents:

- an AWS Direct Connect private virtual interface associated through a Direct
  Connect gateway to the AWS Transit Gateway; and
- an Azure ExpressRoute private-peering circuit connected to the Azure Virtual
  WAN ExpressRoute gateway.

The two circuits terminate in different provider locations and use separate BGP
sessions. The organization advertises only the summarized AWS `10.40.0.0/16`
and approved Azure `10.50.0.0/15` subprefixes. Maximum-prefix limits, explicit
route filters, and BGP community policy prevent accidental default-route or
unrelated enterprise-prefix propagation. Bidirectional Forwarding Detection is
enabled where the provider supports it, and the higher-cost path remains warm
for rapid failover.

This design is chosen over a permanent internet IPsec mesh because it provides
predictable private routing, higher throughput, stable latency, and clearer
operational ownership. Its disadvantages are circuit cost, lead time, and a
dependency on a connectivity provider. For initial build or disaster recovery,
two route-based IPsec tunnels may terminate on Transit Gateway and the Azure
Virtual WAN VPN gateway with less-preferred BGP routes. That backup is not a
reason to expose application load balancers publicly.

## DNS and service discovery

Applications use names, never cross-cloud IP literals. An internal namespace
such as `prod.internal.example` is delegated through enterprise DNS.

AWS Route 53 private hosted zones contain the frontend name and any AWS-local
service records. Route 53 Resolver inbound endpoints answer approved queries
from the enterprise network and Azure. Outbound endpoints forward Azure private
zones to Azure DNS Private Resolver inbound endpoints. Azure Resolver outbound
rules forward the AWS private zone and enterprise zones to their authoritative
resolvers. Resolver security groups and NSGs permit TCP/UDP 53 only between the
named resolver subnets.

The frontend calls `api.prod.internal.example`, which resolves to the AKS
internal load balancer address. The backend connects to a private PostgreSQL
name in an Azure Private DNS zone. That zone is linked only to the AKS and
database networks that require it; the database name is not published into the
AWS frontend zone. TTLs of 30–60 seconds balance failover responsiveness against
resolver load. DNS query logging is enabled in both clouds without logging
application payloads.

## Traffic paths

### User to frontend

An enterprise user or corporate reverse proxy resolves the frontend private
name and reaches an internal AWS load balancer over the enterprise WAN and
Transit Gateway. The load balancer terminates TLS with an internal certificate
and forwards only the application port to the EKS ingress controller. EKS nodes
and pods have no public IPs. Kubernetes ingress rules accept only approved host
names, and a default-deny NetworkPolicy limits ingress-controller traffic to the
frontend pods.

### Frontend to backend API

The frontend resolves the private API name and establishes TLS—preferably mTLS
for service identity—to the AKS internal load balancer. The route is EKS subnet,
Transit Gateway, Direct Connect, provider fabric, ExpressRoute, Azure Virtual
WAN secured hub, and AKS spoke. AWS security groups allow egress only to the API
CIDR and port. Azure Firewall policy and the AKS subnet NSG allow the reciprocal
flow. An AKS default-deny NetworkPolicy permits ingress only through the API
ingress and permits egress only to PostgreSQL, DNS, telemetry, and explicitly
approved dependencies.

### Backend to PostgreSQL

Only backend pods may reach PostgreSQL on TCP 5432. Azure uses either Flexible
Server private access in a delegated subnet or a private endpoint; public
network access is disabled in both cases. Private DNS returns the private
address. The database NSG/private-endpoint policy admits the AKS workload subnet
only, and database authentication uses workload identity plus a managed secret
or token where supported. TLS is required and certificate verification is not
disabled. There is no route or policy from the AWS frontend CIDR directly to the
database subnet.

### Management and egress

Cluster API endpoints are private. Administrators use a controlled management
network or short-lived privileged runner through private connectivity; neither
API server is opened to the internet. Software downloads leave through
centralized, filtered egress or private service endpoints. AWS VPC endpoints and
Azure Private Link are preferred for registry, object storage, secrets, and
monitoring services. NAT is not used as an inbound path.

## Security controls

Routing establishes reachability but not authorization. Controls are layered:

- Transit Gateway route tables and Virtual WAN hub route tables expose only the
  frontend-to-API and API-to-database paths required by the application.
- AWS security groups and Azure NSGs use explicit destination/source prefixes
  and ports. Broad `0.0.0.0/0` application rules are prohibited.
- Azure Firewall inspects cross-spoke and cross-cloud flows and exports flow
  logs; AWS VPC Flow Logs cover accepted and rejected VPC traffic.
- Kubernetes namespaces start with default-deny ingress and egress policies.
  Service accounts use AWS IRSA/EKS Pod Identity or Azure Workload Identity;
  node credentials are not application credentials.
- TLS protects all application hops, and certificates come from an internal CA
  with automated rotation. Sensitive values reside in managed secret stores,
  not ConfigMaps or images.
- Platform and application logs use correlation IDs but exclude credentials,
  tokens, and personal data.

## Availability, operations, and tradeoffs

EKS and AKS node pools span three zones where the regions support them. Internal
load balancers perform zone-aware health checks. PostgreSQL uses zone-redundant
high availability and tested point-in-time restore. Each private circuit is
sized to carry normal traffic if the other fails; capacity alarms fire before
70 percent sustained utilization. A quarterly test withdraws one BGP path and
verifies DNS, frontend-to-API calls, and database transactions continue.

The design favors operational clarity over the fewest components. Transit
hubs, firewalls, resolvers, and private circuits add cost, but they prevent a
fragile peering mesh and make route ownership auditable. For a small non-
production system, redundant IPsec may be a reasonable temporary compromise.
For production, Direct Connect plus ExpressRoute through two locations is the
recommended baseline.

Before implementation, the network team must approve IP allocations, route
filters, MTU/MSS behavior, asymmetric-routing tests, resolver forwarding,
certificate ownership, firewall rules, and the exact recovery runbook. None of
the CIDRs or services in this document should be treated as deployed evidence.
