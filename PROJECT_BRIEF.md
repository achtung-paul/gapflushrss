# GapFlushRSS — Project Brief

Consolidated from `Specs/GapFlushRSS.pdf` plus scoping decisions made 2026-08-05. This is written to be handed to Claude Code as the starting brief for implementation.

## What it is

A web application for automotive dimensional engineers to run Dimensional Variation Analysis (tolerance stack-up analysis) on interior parts. It helps decide gap and flush targets between components so they fit without interference, squeaks, or uneven gaps, by running a statistical simulation against manufacturing and assembly tolerances.

## Data hierarchy

```
Project
 └─ Commodity
     └─ Analysis (unique ID, e.g. XX-001)
         ├─ Gap analysis (optional, ID suffix -GAP)
         └─ Flush analysis (optional, ID suffix -FLUSH)
```

- Projects and Commodities are only definable by Site Admins or Project Admins, added via the GUI.
- The Commodity list is admin-populated and each entry has two fields: a name (e.g. "Doors") and a manually entered 2-letter code (e.g. `DR`) used as the ID prefix. Same pattern for Instrument Panel → `IP`, etc. — the admin sets the code when creating the commodity, it isn't auto-generated.
- Each Analysis gets a unique ID: a 2-letter commodity code + a 3-digit sequential number starting at 001.
- Each Analysis must have **at least one** of Gap or Flush attached; both are allowed on the same analysis. Each one added takes the base unique ID and appends `-GAP` or `-FLUSH`.
- An Analysis can exist as a placeholder with no recorded data yet.
- Each Gap/Flush analysis has its own manually entered nominal target (e.g. 3.5 mm), **plus an upper and lower tolerance on that nominal**. These are not assumed to be symmetric — e.g. `+0/-0.5` or `-0.2/+1` must both be supported. The data model should store the nominal value and the upper/lower limits as separate fields, not a single ± value.

## Core workflow (per Gap or Flush analysis)

1. **Define objectives** — identify the critical-to-quality (CTQ) clearance and set the nominal target.
2. **Image annotation** — upload an image of the part/assembly, mark up interface points using Annotorious. Markers render as numbered red circle "balloons" (leader-line style, per the reference image in the spec) linked to DB entries.
3. **Geometric alignment (locating schemes)** — 3-2-1 locating principle and vehicle coordinate system (X/Y/Z). **Not calculated by the software** — this is done manually by the user and not recorded. Flagged in the spec as a possible future module.
4. **Build the tolerance chain** — trace the dimension path from Component A through the structure to Component B (potentially many parts). Input component tolerances (GD&T-based) and assembly-process variation (robotic placement, fixture, locator, fastening shift, etc). Process type (plastics, castings, pressings, ...) is selected from an admin-editable dropdown.
5. **Run the statistical simulation** — Root Sum Square (RSS) method for linear stacks, evaluated at **3σ, 4σ, and 5σ** (corrected from the source spec, which said 6σ). Show the resulting distribution on a graph.
6. **Evaluate results** — compare the calculated stack-up result against the nominal target's tolerance band (nominal + upper/lower limits — see asymmetric tolerance note under Data hierarchy). Show a visual RAG (red/amber/green) indicator using this rule:
   - **Green** — calculated result falls within the tolerance band (between `nominal − lower limit` and `nominal + upper limit`).
   - **Amber** — calculated result falls outside the band (either above the upper limit or below the lower limit), but within 5% of the limit it breached.
   - **Red** — calculated result falls outside the band by more than 5% of the limit it breached, on either side.

   This applies symmetrically: breaching the lower limit is evaluated the same way as breaching the upper limit, not just excess-over-nominal on one side.
7. **Report** — each Gap/Flush analysis needs a printable report, also exportable to Excel via openpyxl.

## Scope for v1 (material/process)

Initial release targets **plastics only**, per DIN 16742 and the older DIN 16901 standard. Process type list (plastics, castings, pressings, etc.) should be admin-editable from the start so other processes can be added later without a schema change.

**Tolerance data decision:** build a generic, editable admin table now (process type → tolerance class → value) rather than hardcoding DIN figures. Real DIN 16742/16901 values will be supplied and loaded into this table later — don't invent or research values in the meantime.

## Users, auth, and RBAC

Full target design (per spec):
- Hierarchical RBAC: **Root Admin** (global system/DB admin) → **Project Admin** (creates projects, manages assets/users within them) → **Standard User** (project-scoped via groups).
- Permissions are never assigned directly to users — only via project-scoped groups.
- Every new project auto-creates three groups: `Project-<Name>-Managers` (read/write/delete), `-Contributors` (read/write), `-Viewers` (read-only).
- DB shape: `Users(user_id, username, global_role)`, `Projects(project_id, project_name)`, `Groups(group_id, group_name)`, join table `User_Group_Project(user_id, group_id, project_id)`.
- Onboarding/offboarding is a single group-membership change; Root Admin bypasses project-scope checks entirely via `global_role == 'Root'`.
- Auth options: Microsoft OAuth (Entra ID in production, Keycloak in dev) **or** a simple username/password system with recovery — selectable, not mutually exclusive.

**Phasing decision:** build the RBAC hierarchy and a simple username/password auth system in the first pass. Defer OAuth/Entra ID/Keycloak integration to a later phase — don't block core functionality on it.

**Account recovery decision (2026-08-05):** password recovery is email-based (reset link/token sent to the user's registered email), not admin-triggered. Requires an outbound email-sending capability (e.g. SMTP relay) as part of the Phase 1 auth build.

## Tech stack (as specified)

- **Language:** Python 3.13.12 for the backend — code must stay simple and well-commented, written at a level a programmer with ~6 months of experience could follow. This is an explicit, non-negotiable constraint on code style throughout the project.
- **Frontend:** React
- **Database:** PostgreSQL
- **Image storage:** MinIO
- **Web server:** Nginx
- **Excel export:** openpyxl
- **Annotation:** Annotorious (custom bubble shape/CSS, custom fields, event listeners on shape create/click)
- **Deployment:** Docker containers inside an LXC container on a Proxmox host.

**Infra decision:** the Proxmox host and LXC container are already provisioned. The brief only needs to cover Docker/docker-compose and Nginx configuration to deploy into that existing environment — not LXC/Proxmox provisioning itself.

## UX

- Clean, simple UI with a light/dark theme switch.
- Colour palette: headings in green/shades of green; body text black (light mode) / white (dark mode).
- Common header bar across pages.
- Dropdowns for selecting project and commodity (per the navigation diagram: Project List → Commodity List → Analysis List → Tolerance Analysis → Gap/Flush).

## Open items / assumptions to revisit

These weren't specified in the source doc and are flagged rather than guessed at:

- Report layout/content beyond "printable, plus Excel export" — TBD.
- Whether Worst Case Analysis or other stack-up methods get added alongside RSS later — not in scope for v1 (RSS only, 3σ/4σ/5σ).

### Resolved (2026-08-05)

- ~~RAG thresholds~~ — see rule under step 6, Core workflow. Bands are based on the actual tolerance limits, evaluated symmetrically (upper and lower breaches treated the same way), not a flat % of nominal.
- ~~Commodity list codes~~ — see Data hierarchy: admin sets name + 2-letter code per commodity, not auto-generated.
- ~~Asymmetric nominal tolerance~~ — see Data hierarchy: nominal stores separate upper/lower limit fields, not a single ± value.
- ~~Password recovery mechanism~~ — see Account recovery decision under Users, auth, and RBAC: email-based reset, not admin-triggered.

## Reference image (from spec)

The annotation "balloon" style referenced in the spec: a red circle containing a number, similar to standard engineering drawing callouts, with a leader line to the marked feature.
