# ADR-005: External authorization port

**Status:** Accepted
**Date:** 2026-08-10
**Decider:** Project Manager

## Context

This repository builds the ViVi Vehicle Agent. It must be able to connect to
ViGuard later, but vendor wire schemas, HTTP behavior and mock-server code had
been placed under core-looking `contracts/guardrail` and `adapters/guardrail`
names. Core modules also imported that wire contract directly. Replacing or
upgrading the real service would therefore spread changes through the Agent.

## Decision

The Agent owns a stable `authorization` boundary:

- `ActionAuthorizer`, `ConfirmationAuthorizer`, and `MonitorAuthorizer` ports;
- the minimal proposal/decision validation and digest semantics consumed by
  the Agent;
- vendor-neutral entry points such as `authorizer` and
  `to_authorization_snapshot`.

ViGuard-specific HTTP code, wire schema, fixtures and protocol mock live only
under `vivi_agent.integrations.viguard`. The integration implements the Agent
ports. Core Agent packages must not import `integrations.viguard` or the legacy
`contracts.guardrail`/`adapters.guardrail` paths.

Legacy imports and keyword names remain thin deprecated shims during migration.
They contain no ViGuard implementation and can be removed in a later major
version after downstream consumers move to the stable port.

## Options considered

1. Keep direct Guardrail imports: least immediate work, but every service
   contract change leaks into Agent core.
2. Remove all authorization concepts: makes the Agent unable to request an
   external execution decision and merely postpones integration work.
3. Stable Agent port plus optional ViGuard integration: selected because it
   preserves a small composition seam without embedding the external system.

## Consequences

- A real ViGuard connection is configured by constructing `ViGuardClient` and
  injecting it as `authorizer`; workflow/model code remains unchanged.
- Another authorization service can implement the same ports.
- Wire-version changes are localized to `integrations/viguard` plus explicit
  translation at the boundary.
- Compatibility shims temporarily preserve old imports but are not valid
  locations for new implementation.
