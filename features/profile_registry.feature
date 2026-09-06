Feature: Agent assets governed by a private forward-only journal
  Zuat observes native agent state, reconciles named profiles, and exposes only
  stable domain assets and operations.

  Scenario: Adopt, force, uninstall, and audit real-format Claude assets
    Given an isolated Claude home with an existing skill and two shared hooks
    When I observe and adopt the existing Claude skill and first hook
    And the adopted Claude hook drifts outside Zuat
    And I force the adopted Claude hook back to its desired content
    And I uninstall that Claude hook by its stable reference
    Then the unrelated Claude hook and setting remain unchanged
    And the Claude lifecycle operations appear in causal journal order

  Scenario: Reject drift, force a profile switch, and revert it forward
    Given an isolated Codex home with a version one skill and two named profiles
    When the work profile is configured with version two of the skill
    And native Codex drifts while the default profile is selected
    Then an unforced switch to work is rejected without selecting it
    When I force the switch to work and revert that operation
    Then the default profile and version one native skill are restored
    And the revert is a new operation that references the forced switch

  Scenario: Keep four agent identities and outcomes independent
    Given isolated native homes contain the same skill for every supported agent
    When I observe and adopt that skill for every supported agent
    And I uninstall only the Codex asset by its stable reference
    Then each agent has an independent stable asset identity
    And only Codex native state changed while every agent reported its own outcome

  Scenario: Recover an interrupted deletion from recorded evidence
    Given an isolated Codex skill is archived before an interrupted deletion
    When I reopen the registry and restore all skills from the interruption
    Then the Codex skill and its unauthoritative state are restored
    And the recovery is appended after the interrupted operation evidence
