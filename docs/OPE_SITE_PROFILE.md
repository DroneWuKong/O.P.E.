# O.P.E. Site Profile

Public-safe profile for the Gurnee/Southridge physical site where O.P.E. runs.

This document intentionally omits the full residential address, owner details, private network identifiers, access instructions, and secret material. Keep those in a private local runbook or password manager, not in this repository.

## Site Role

The Gurnee/Southridge site is the physical body for O.P.E. It provides:

- Power, cooling, and physical security for Octoputer nodes.
- Residential broadband access to the tailnet.
- A stable place for self-hosted AI orchestration, memory, and tool execution.
- The operational boundary between cloud services, local compute, and human custody.

## Public Property Snapshot

Public real-estate records and listing mirrors describe the site as:

- Single-family residential property in Gurnee, Lake County, Illinois.
- Approximately 2,636 sq ft.
- Approximately 0.32 acre lot.
- Built around 1990.
- 4 bedrooms and 2.5 to 3 baths depending on source normalization.
- Off-market / not currently listed for sale.
- Public estimate range observed around the high $400k range.
- Public tax data observed near $10.8k/year in recent records.

Public sources disagree on some ownership/sale-history details. Treat listing-site history as advisory only; verify material facts through Lake County records before making financial, legal, or insurance decisions.

## Operational Interpretation

This site should be managed like a small edge compute room inside a residential shell.

The key question is not just "is the house valuable?" It is:

> Can this site keep O.P.E. powered, cooled, connected, secure, and recoverable during normal life, storms, ISP failures, and hardware incidents?

## Current Strengths

- Residential structure gives O.P.E. low-friction physical custody.
- Gurnee has multiple consumer broadband options listed publicly, including cable, fiber where available, fixed wireless, and cellular/satellite alternatives.
- ComEd is the regional electric utility, with public outage status and outage-map tooling.
- The lot size and suburban setting likely allow practical UPS/generator planning, subject to local code, HOA rules, noise constraints, and insurance.
- The site is close enough to dense suburban infrastructure to make replacement parts, contractor access, and ISP service calls practical.

## Main Risks

### Power

O.P.E. depends on continuous power. Residential utility power is usually good enough for casual compute, but not enough for reliable infrastructure without buffering.

Minimum controls:

- UPS on every compute/network node.
- UPS runtime target documented per node class.
- Graceful shutdown automation.
- Surge protection on compute, networking, and ISP equipment.
- Generator or battery-backup plan for long outages.

### Network

Tailnet access makes the site useful, but a single ISP is still a single failure path.

Minimum controls:

- Primary wired ISP.
- Secondary path: cellular, fixed wireless, or satellite.
- Router that can fail over automatically.
- Tailnet health check from outside the site.
- Local admin path that still works when the public internet is down.

### Cooling

Residential rooms are not server rooms. Heat can silently degrade hardware.

Minimum controls:

- Temperature sensors near compute.
- High-temperature alerting.
- Clear intake/exhaust paths.
- Dust management.
- Summer AC failure plan.
- No dense compute in closets without airflow.

### Flood / Water

Gurnee's most serious flood hazard is associated with the Des Plaines River and tributaries. Whether this specific site is in or near a regulated flood zone must be verified with Lake County/FEMA map tooling, not inferred from city-level risk.

Minimum controls:

- Verify FEMA flood zone for the parcel.
- Keep compute off basement floors and away from sump/ejector risk.
- Add water sensors near basement, utility, sump, and rack locations.
- Document shutoff locations.

### Physical Security

The site is residential, so the threat model is different from a data center.

Minimum controls:

- No exposed secrets on labels, monitors, or dashboards.
- Locked room/cabinet if visitors or contractors are present.
- Cameras or door sensors where appropriate.
- Inventory of hardware serial numbers.
- Encrypted disks or secrets stored outside local plaintext.

### Fire / Electrical

Compute gear adds continuous electrical load.

Minimum controls:

- Know circuit ratings and breaker layout.
- Avoid daisy-chained power strips.
- Use proper PDUs where needed.
- Smoke detection in compute area.
- Fire extinguisher suitable for electrical equipment.
- Electrician review before expanding load.

## Recommended Site Tiers

### Tier 0: Current Residential Edge

Goal: O.P.E. works when the house works.

- Single ISP.
- Consumer router.
- UPS for network and primary compute.
- Manual recovery.

### Tier 1: Resilient Home Lab

Goal: O.P.E. survives short outages and common ISP failures.

- UPS runtime of 20-60 minutes.
- Automatic shutdown for compute.
- Cellular/fixed wireless backup WAN.
- Remote health monitor.
- Temperature/water sensors.
- Documented restart procedure.

### Tier 2: Serious Edge Node

Goal: O.P.E. remains useful through multi-hour incidents.

- Generator or whole-home battery.
- Automatic WAN failover.
- Dedicated compute circuit.
- Environmental monitoring with alerts.
- Off-site backups.
- Tested restore process.
- Spare router/switch/storage on shelf.

## Immediate Action Checklist

1. Confirm exact electrical circuits used by Octoputer hardware.
2. Measure idle and peak watt draw for each node and the network stack.
3. Size UPS capacity from measured load, not guesses.
4. Confirm ISP plan, upload speed, data cap, and public/private addressing behavior.
5. Price a secondary WAN path.
6. Verify FEMA/Lake County flood designation for the parcel.
7. Place water and temperature sensors near compute and utility-risk areas.
8. Build an off-site backup target for O.P.E. memory/config.
9. Document cold-start and graceful-shutdown procedures.
10. Create a private site runbook containing the exact address, access notes, ISP account info, utility account info, and emergency contacts.

## Private Runbook Fields

Keep this out of git.

- Full address.
- Parcel/PIN.
- Utility account numbers.
- ISP account numbers.
- Tailnet device names and admin URLs.
- Local IP ranges.
- Wi-Fi credentials.
- API keys.
- Kubeconfig and SSH keys.
- Physical access notes.
- Emergency contacts.
- Insurance details.

## Public Source Notes

- Redfin public record/listing mirror for the off-market property, approximate size, lot, year built, estimate, and last-sale data. URL omitted here because it contains the residential street address.
- Homes.com public listing mirror for estimated value, public tax history, and ownership-history summary. URL omitted here because it contains the residential street address.
- Lake County property-tax tooling for official verification: https://tax.lakecountyil.gov/
- Lake County flood insurance and map tooling: https://www.lakecountyil.gov/2373/Flood-Insurance-Maps
- Village of Gurnee flood guidance for area-level flood context: https://www.gurnee.il.us/residents/safety/extreme-weather-events/flooding-in-gurnee
- Public ISP availability examples for Gurnee broadband options: https://broadbandnow.com/Illinois/Gurnee and https://www.xfinity.com/local/il/gurnee
- ComEd outage tooling for power-incident monitoring: https://secure.comed.com/FaceBook/Pages/outagemap.aspx

## Open Questions

- Which room physically hosts the current Octoputer hardware?
- Are any nodes in a basement or utility-adjacent space?
- What are the current UPS models and battery ages?
- What is the measured continuous watt load?
- Does the router support automatic WAN failover?
- Are O.P.E. memory and Postgres backups replicated off-site?
- Is there a documented "leave the house and keep O.P.E. safe" shutdown mode?
