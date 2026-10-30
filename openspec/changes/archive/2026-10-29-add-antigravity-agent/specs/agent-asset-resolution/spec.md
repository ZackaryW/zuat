# Spec Delta

## MODIFIED Requirements

### Requirement: Independent agent trees
Zuat SHALL represent Codex, Claude, Kimi, Pi, and Antigravity in independent top-level agent trees. An operation on one agent tree SHALL affect only that agent unless the caller explicitly requests separate operations for additional agents.

#### Scenario: Change one agent asset
- **WHEN** an operation targets a Codex skill
- **THEN** Zuat observes or reconciles only the Codex asset and leaves similarly named assets for other agents unchanged

#### Scenario: Represent identical content for two agents
- **WHEN** Codex and Claude contain skills with identical content
- **THEN** Zuat assigns each skill an agent-specific reference and allows their lifecycle state to diverge independently

#### Scenario: Represent identical content for Antigravity
- **WHEN** Claude and Antigravity contain skills with identical content
- **THEN** Zuat assigns each an agent-specific reference and a change to one leaves the other unchanged

### Requirement: Agent-owned native behavior
Zuat SHALL use one common resolution contract while requiring a distinct implementation for each supported agent. Each agent implementation SHALL own its native asset kinds, locations, formats, scopes, validation, reconciliation, and verification behavior.

#### Scenario: Resolve a supported agent
- **WHEN** Zuat processes an asset for Codex, Claude, Kimi, Pi, or Antigravity
- **THEN** it selects that agent's implementation and returns a common Zuat domain result

#### Scenario: Reject an unsupported agent
- **WHEN** a caller identifies an unsupported agent
- **THEN** Zuat rejects the request without interpreting the asset using another agent's rules
