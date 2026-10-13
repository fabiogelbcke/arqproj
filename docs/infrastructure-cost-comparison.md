# Pilot infrastructure: costs and hosting choices

**13 October 2026 · USD/month · planning estimates, not a provider quote**

Companion to the [implementation plan](multi-tenant-implementation-plan.md).
Prices were checked against the official sources linked below. No resources were
provisioned. Existing account eligibility, negotiated discounts and actual traffic
have not been inspected. Promotional credits are excluded from monthly totals.

## Revised POC recommendation: start smaller

The original ~$65 estimate below is **not a minimum cost for five offices**.
It assumed paid PostgreSQL kept awake by frequent polling (~$25), a wildcard
load balancer (~$19), 60 GB of outbound traffic (~$11), and an $8 operating
allowance. The scheduler and queue themselves were estimated at $0. Neither
office count nor multi-tenancy inherently requires those paid components.

For the personally onboarded POC, consider this simpler proposal before selecting
the fuller deployment:

```text
One hourly Cloud Scheduler job (or local cron)
                    ↓ authenticated POST
Existing web service: /internal/maintenance
                    ↓
PostgreSQL sync cursors / pending email batches ↔ Drive and email APIs
```

Keep one Cloud Run service, with no separate worker deployment, broker or Cloud
Tasks queue initially. The endpoint does a bounded amount of work before returning:
check Drive changes, update metadata, send due digests and retry recoverable work.
Persist cursors and pending/sent status; guard against overlapping calls and use
stable operation IDs for external side effects. These are small application
records, not a mandate to build a general-purpose queue framework. Do not keep
working in an untracked background thread after returning the HTTP response.

**Scheduling choice: Cloud Scheduler is preferred while the billing account has
free allowance available; local cron remains an alternative.** Both call the
same endpoint and neither requires a separate queue or worker deployment.

| Option | Timer cost | Operational tradeoff |
| --- | --- | --- |
| Cloud Scheduler — preferred | $0 within the first three jobs per billing account; otherwise $0.10/job per 31 days | Runs independently of a developer's computer; confirm allowance across the billing account before setup |
| Local cron — alternative | No additional cloud scheduler fee when using an existing computer | Runs only while that computer is awake and connected; missed runs delay processing until a later call |

These are timer costs only. Both still incur application execution, database and
API usage, so local cron does not remove those costs. Start with one shared job
for all offices, not one per office. Hourly execution remains a proposed cadence
pending agreement on freshness and notification timing. Use only one active
timer at a time to avoid unnecessary duplicate calls.

Scheduler can attach an identity token; since the website is public, the application must
explicitly validate the token and authorized caller on this internal route.
Local cron must also use an authorized credential, kept outside the repository.
[Scheduler pricing](https://cloud.google.com/scheduler/pricing),
[HTTP authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth)

Hourly scheduling adds up to about an hour of Drive discovery delay, plus any
retained email batching window and scheduling delay. If this is too slow, evaluate
15-minute runs or a staff-triggered refresh. Website uploads can update their own
metadata immediately. Confirm the notification timing rather than silently
redefining the agreed batching behavior.

**Try Neon Free for POC metadata**, subject to usage and recovery needs. Current
limits include 100 CU-hours/month, 1 GB storage and 5 GB outbound transfer per
project, with five-minute idle suspension. Hourly short wakes at 0.25 CU consume
approximately `730 × 5/60 × 0.25 = 15.2 CU-hours/month` just in idle tails;
15-minute wakes consume about 60.8. Add actual work and viewer activity to those
figures. Connection checks must not continually wake an idle database. Free's
six-hour restore history is limited; arrange private backups and prove restore
before it contains irreplaceable metadata. Watch quotas: exhaustion can suspend
compute, rather than automatically providing free excess capacity.
[Neon limits](https://neon.com/docs/introduction/plans)

**Domain routing is a separate cost decision.** Avoiding the ~$18.25 fixed load
balancer charge requires an alternative, not merely removing the queue. For an
internal POC, a default `run.app` URL with explicit tenant paths is possible, but
temporarily changes the agreed office-subdomain requirement and needs agreement.
Individual subdomain mappings preserve the URL format without that load balancer,
but Google's mapping feature is regional, Preview and explicitly not recommended
for production due to latency issues. Do not silently substitute it for the
production design. A DNS wildcard alone does not solve HTTPS routing.
[Cloud Run domain options](https://docs.cloud.google.com/run/docs/mapping-custom-domains)

With free database/email allowances, low compute use and **1–10 GiB/month** of
outbound traffic instead of the earlier 60 GiB assumption, transfer to Brazil at
the modeled rate is about $0.19–$1.90. A no-load-balancer POC could therefore be
near zero or a few dollars monthly, plus domain registration, backup storage and
any image/build/log usage outside free allowances. This is a conditional target,
not a $0 guarantee or a measurement of the existing account. Keeping the proposed
load balancer adds about $18.25/month plus processing even at tiny traffic.
[Cloud Run pricing](https://cloud.google.com/run/pricing),
[network rates](https://cloud.google.com/vpc/network-pricing)

Upgrade when measured needs justify it: database limits or restore requirements,
work exceeding a bounded request, unacceptable refresh delay, or background jobs
interfering with page performance. Modular handlers allow later queue/worker
extraction without deploying them separately now. Tenant isolation, authenticated
maintenance calls and recoverable state remain requirements in the simpler POC.

## Original fuller deployment comparison

**Google Cloud Run remains the leading hosting candidate.** The fuller design
models roughly **$65/month for five offices**, rising to **$140/month for 25 offices**
under the assumptions below; these are not required POC starting costs.
These are shared product costs, not per-office
fees. Downloads, the database and wildcard-domain infrastructure dominate; the
scheduler is a very small expense.

| Hosting configuration | Five-office pilot | 25-office early paid phase | Main qualification |
| --- | ---: | ---: | --- |
| Google Cloud Run + external load balancer | ~$65 | ~$140 | Higher modeled transfer price to Brazil |
| AWS ECS Fargate + application load balancer | ~$80 | ~$125 | One continuously running web task; more infrastructure configuration |
| Azure Container Apps Consumption | ~$35 | ~$80 | Per-office hostname setup; large/slow streaming must pass ingress tests |

All rows include the **same external PostgreSQL and email providers**, plus a
small operating allowance. They are practical deployment alternatives, not
identical hardware or identical availability guarantees. Azure's lower estimate
is conditional on its delivery limits fitting our product. Do not move providers
solely to save a few tens of dollars before checking actual file behavior.

## Workload and scope

Use 730 hours/month and US reference regions: Google `us-central1`, AWS
`us-east-1`, Azure `eastus`. Most customers are assumed to be in Brazil. A Brazil
region needs a new quote and latency comparison; regional rates are not
interchangeable. Select a nearby database region after choosing hosting.

| Assumption | Pilot | Early paid phase |
| --- | ---: | ---: |
| Offices | 5 | 25 |
| Public HTTP requests | 200,000 | 1,000,000 |
| Aggregate billed container seconds, at 1 vCPU / 2 GiB | 100,000 | 300,000 |
| Internet outbound traffic | ~60 GB | ~300 GB |
| Load-balancer processed traffic, where applicable | ~60 GB | ~300 GB |
| Email deliveries, counting recipients | 1,000 | 5,000 |
| Database base storage | 5 GB | 10 GB |

Container seconds include web requests, streaming and background work. These are
**usage budgets, not measurements or predictions derived from office count**.
A single timer firing each minute means 43,800 invocations/month; at two seconds
each it already consumes 87,600 worker seconds. Slow streams, cold starts or
longer syncs can exceed the budget. The AWS row instead buys continuous small
web capacity, with bounded worker invocations separately.

Traffic includes file delivery and an allowance for uploads forwarded to Drive
and other outbound calls. The estimate conservatively applies Google's
Brazil-destination rate to all modeled outbound bytes. Native billing units vary
between GB and GiB; values here are rounded planning quantities. No original-file
storage is purchased: offices pay for their own Drive capacity. Streaming avoids
keeping a copy, but does not remove transfer or request-duration charges.

Includes one production environment, basic restore history, modest logs, secrets,
images/builds, DNS and a domain allowance. Excludes taxes, paid support, SMS,
WhatsApp, substantial preview storage/processing, CDN/WAF subscriptions and
engineering time. A separately funded, continuously running staging environment
is not included. Free allowances are assumed available to this application;
other projects or staging can consume the same shared allowances.

## Common database and email budget for the fuller comparison

**PostgreSQL: allow $25/month initially.** Neon Launch currently lists
$0.106/CU-hour, $0.35/GB-month base storage and $0.20/GB-month retained change
history. An always-awake 0.25-CU endpoint is about $19.35/month in compute; 5 GB
of base storage and 1 GB of retained history bring that to roughly $21.30.
The $25 allowance leaves modest headroom; it is not a fixed-price plan or a
spending cap. More compute or write history increases the bill. Configure and
test restore retention before launch.
[Neon plans](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md)

Minute/two-minute polling prevents the usual five-minute idle scale-down. Even
0.25 CU continuously consumes 182.5 CU-hours/month, exceeding Neon's 100-CU-hour
Free allowance. Do not budget the production database at zero on the assumption
that nobody is viewing the site. A managed task queue alone does not fix this
while frequent Drive polling continues.

**Email: $0 pilot / $20 growth.** Resend Free includes 3,000 messages/month but
also a 100/day limit. Pro is $20/month for 50,000 messages, without that daily
limit. A burst of notifications can therefore require the paid plan before
monthly volume does. Assume a shared product sending domain; customer-owned
sender domains are a separate feature. [Resend pricing](https://resend.com/pricing)

Using Neon makes the hosting comparison consistent. Cloud SQL, Amazon RDS and
Azure Database for PostgreSQL are alternatives, but require separate quotes for
region, instance, backups and availability. Cloud credits may make a native
database attractive temporarily; compare its post-credit bill before switching.

## Monthly estimate and calculation basis

Each cell shows **pilot / growth**, rounded to the nearest dollar.

| Cost component | Google Cloud | AWS | Azure |
| --- | ---: | ---: | ---: |
| Web and bounded worker compute | $0 / $3 | $18 / $18 | $0 / $4 |
| Load balancer and processing | $19 / $21 | $17 / $19 | Included / included |
| Separately billed public IPv4 | — | $11 / $11 | — |
| Internet outbound transfer | $11 / $57 | $0 / $18 | $0 / $17 |
| Scheduler / queue allowance | $0 / $0 | $0 / $0 | Included / included |
| PostgreSQL budget | $25 / $25 | $25 / $25 | $25 / $25 |
| Email | $0 / $20 | $0 / $20 | $0 / $20 |
| DNS/domain, logs, secrets, image/build allowance | $8 / $12 | $8 / $12 | $8 / $12 |
| **Calculated total, before headline rounding** | **$63 / $138** | **$79 / $123** | **$33 / $78** |

The last operating line is a budget allowance rather than an itemized quote.
Set retention limits and review it after the first billing cycle. These totals
assume no commitments, reserved capacity or promotional credits.

### Google Cloud

Deploy FastAPI and the worker as request-billed Cloud Run services, minimum zero
instances. Its monthly allowance includes 180,000 vCPU-seconds, 360,000 GiB-seconds
and two million requests. At the reference rates, growth compute is
`120,000 × $0.000024 + 240,000 × $0.0000025 = $3.48` after allowances.
[Cloud Run pricing](https://cloud.google.com/run/pricing)

For wildcard HTTPS, model a global external Application Load Balancer with a
serverless backend and DNS-authorized certificate. Forwarding rules cost
`730 × $0.025 = $18.25`; modeled processing adds $0.48 / $2.40 at $0.008/GiB.
Internet transfer to South America is modeled at $0.19/GiB: $11.40 / $57.
Do not charge the same outbound transfer again as a separate Cloud Run transfer.
[Load-balancer pricing](https://cloud.google.com/load-balancing/pricing),
[network pricing](https://cloud.google.com/vpc/network-pricing)

Cloud Scheduler's first three jobs per billing account are free; additional
jobs cost $0.10/job/month. A shared minute timer is one job, not 43,800 jobs.
Cloud Tasks includes one million operations/month, then $0.40/million. Operations
include enqueue calls and delivery attempts, so tasks and operations are not
interchangeable. Small ID-only payloads at our modeled volume should fit the
allowance; worker compute is still billed separately.
[Scheduler pricing](https://cloud.google.com/scheduler/pricing),
[Tasks pricing](https://cloud.google.com/tasks/pricing)

### AWS

Model one ECS Fargate Linux/x86 web task with 0.5 vCPU and 1 GiB running all month:
`730 × (0.5 × $0.0404784 + $0.004446) ≈ $18.02`. The application load balancer
adds $16.43 fixed, plus approximately $0.48 / $2.40 in capacity charges if bytes
dominate. Connection/rule dimensions can raise those charges. Budget three public
IPv4 addresses: two load-balancer addresses plus one task, totaling $10.95.
[Fargate](https://aws.amazon.com/fargate/pricing/),
[load balancing](https://aws.amazon.com/elasticloadbalancing/pricing/),
[IPv4 pricing](https://aws.amazon.com/vpc/pricing/)

This assumes a public-subnet task accepting application traffic only from the
load balancer, external PostgreSQL over TLS, and no NAT gateway. Adding private
subnets/NAT changes the bill. One task is a pilot compromise; two steady web tasks
add roughly $22/month for task compute and its IPv4 address before extra traffic.
Capacity and failover need testing; this is not a high-availability quotation.

Use EventBridge Scheduler and a bounded Lambda worker for the original SQL-queue
option. 43,800 invocations at 1 GB for two/five seconds fit Lambda's recurring
one-million-request / 400,000-GB-second allowance. Scheduler includes 14 million
invocations/month. Lambda is the background worker in this estimate, not the
large-file streaming web server. SQS is an alternative if selecting managed
dispatch. [Lambda pricing](https://aws.amazon.com/lambda/pricing/),
[EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/)

Model outbound transfer at $0.09/GB after the account's shared first 100 GB free:
$0 / $18. [AWS transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/)

### Azure

Use Container Apps Consumption for the web app and scheduled Container Apps Jobs
for bounded recurring work. Their subscription-wide monthly grant includes
180,000 vCPU-seconds and 360,000 GiB-seconds; HTTP requests include two million.
East US active rates of $0.000024/vCPU-second and $0.000003/GiB-second give $3.60
growth compute. The model uses only Consumption resources and no private
endpoints or planned-maintenance configuration that would add a management fee.
[Billing](https://learn.microsoft.com/en-us/azure/container-apps/billing),
[prices](https://azure.microsoft.com/en-us/pricing/details/container-apps/),
[scheduled jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)

For white-glove onboarding, bind each `office.product.com` separately using a
free managed certificate. The URL format remains unchanged; arbitrary wildcard
onboarding is not included. A wildcard certificate setup or Front Door needs a
separate design/quote. Built-in ingress documents a **240-second request timeout**:
test representative large files and slow connections before accepting this option.
[Managed certificates](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates),
[ingress limits](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)

Model Microsoft-network outbound transfer from East US at $0.087/GB after the
first 100 GB: $0 / $17.40. Rates were checked in the public Retail Prices API for
`Azure Container Apps` and `Bandwidth`, region `eastus`, Consumption prices;
bandwidth uses the Microsoft global network routing preference.
[Bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/),
[Retail Prices API](https://prices.azure.com/api/retail/prices)

## Free tiers and promotional credits

Monthly allowances above are distinct from temporary credits. Eligibility is
account-specific; do not assume the existing Google account qualifies again.

| Provider | New-customer offer | Startup program worth checking |
| --- | --- | --- |
| Google Cloud | $300 for 90 days | Start tier: up to $2,000 for eligible pre-funded startups. Funded startups can qualify for larger awards, up to $200,000 under the main program. |
| AWS | $100 on signup, with another $100 available through qualifying activities. Free account plan lasts up to six months; credit expiry is 12 months from account creation. Continuing beyond the free plan requires moving to paid. | Activate Founders starts at $1,000; selected participants can receive up to $5,000. Portfolio offers up to $200,000 with an eligible provider's Org ID. |
| Azure | $200 for 30 days; upgrade to pay-as-you-go to continue afterwards | Microsoft for Startups currently starts at $200 after identity verification, with $5,000 after business verification of a registered entity. Larger milestones up to $150,000 require additional adoption/usage conditions. |

Sources: [Google trial](https://cloud.google.com/signup-faqs),
[Google startups](https://cloud.google.com/startup),
[AWS Free Tier terms](https://aws.amazon.com/free/free-tier-faqs/),
[AWS Activate](https://aws.amazon.com/startups/credits/),
[Azure free account](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account),
[Microsoft startup milestones](https://learn.microsoft.com/en-us/startups/microsoft-for-startups/getting-started-mfs).

Startup awards require eligibility/approval and have their own expiry and product
restrictions. Do not assume offers stack. Cloud credits ordinarily do not pay the
separate Neon, Resend or domain-registrar invoices modeled here. Building with AI
coding assistance does not itself establish eligibility for AI-startup awards.
Do not add unnecessary services to unlock a credit tier.

## Decisions and measurements before purchase

1. Confirm region and a representative upload/download size, then test slow-client
   streaming through the real ingress path. Azure's cheaper row is conditional.
2. Measure billed web/worker duration and outbound bytes during the five-office
   pilot. Repeated downloads can dominate costs even though Drive holds originals.
3. Evaluate the hourly in-app maintenance endpoint first. Add a managed queue or
   separate worker when workload/latency calls for it, not simply for multi-tenancy.
4. Confirm database restore retention and test recovery. Request a separate quote
   if selecting a native database, higher availability or full-size staging.
5. Check credit eligibility before opening additional accounts or moving services.
   Set billing alerts, log retention and max-instance limits; alerts are not a
   hard spending cap. Reprice with actual usage before onboarding paid customers.
