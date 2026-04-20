# praktor.ai — Open Source

This is the **open source** repository for praktor.ai. All code here is public and
MIT-licensed. Do not add proprietary features, enterprise-only logic, commercial
licensing code, or anything intended solely for paying customers.

## Scope

What belongs here:
- Agent framework core (routing, observability, prompt registry, tools)
- General LLM judge + golden dataset format
- Base monitoring store and CLI tooling
- Clinical evaluation pipeline for HEDIS/Diabetes (reference implementation)
- AIGov obligation framework (open specification)
- Streamlit UI for local development and demos

What does NOT belong here (goes in `praktor-enterprise`):
- Multi-tenant governance engine with RBAC and audit log export
- Industry-specific judge packs beyond the reference implementation
- Golden dataset marketplace or vertical benchmarks
- Judge calibration-as-a-service
- Enterprise observability (multi-agent dashboards, SLA alerting)
- HITL workflow with reviewer roles and approval gates
- SSO, data residency, SOC 2 controls

When a feature request touches enterprise territory, say so explicitly and suggest
it belongs in the commercial repo instead.

## Sync rule

Open source first, then promote. Build core features here, ship them, then pull
into `praktor-enterprise` and layer enterprise extensions on top.

---

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

## gstack

Use the /browse skill from gstack for all web browsing. Never use mcp__claude-in-chrome__* tools.

Available gstack skills:
/office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation,
/design-shotgun, /design-html, /review, /ship, /land-and-deploy, /canary, /benchmark,
/browse, /qa, /qa-only, /design-review, /setup-browser-cookies, /setup-deploy, /retro,
/investigate, /document-release, /codex, /cso, /autoplan, /plan-devex-review, /devex-review,
/careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn
