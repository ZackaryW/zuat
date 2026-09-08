## MODIFIED Requirements

### Requirement: Public plugin operations

The supported Python interface SHALL provide installed plugin discovery, explicit available-catalog discovery, install, update, remove, general extension registration, artifact resolution, artifact status, and artifact policy set and clear operations. It SHALL expose the subclassable public `ZuatExtension` contract and `register_extension` entry points at module and service level in place of the artifact-only `ArtifactExtension` and `register_artifact` surface, without legacy aliases. The optional CLI SHALL expose plugin discovery, lifecycle, artifact status, and artifact policy operations through the same public interface. Neither surface SHALL require callers to construct internal reconciliation plans or manipulate Git state. Extension registration SHALL be available to Python hosts without requiring a CLI mechanism that loads arbitrary Python code. Generalizing registration SHALL preserve existing artifact result and policy operations.

#### Scenario: Plugin lifecycle through the public interface

- **WHEN** a caller installs a supported plugin, queries it, updates it, and removes it through public operations
- **THEN** each result exposes typed installation and revision evidence with the verified domain outcome

#### Scenario: CLI and Python parity

- **WHEN** equivalent plugin lifecycle requests are issued through Python and the installed CLI extra
- **THEN** they use the same public orchestration and produce equivalent domain outcomes

#### Scenario: General extension through the base Python package

- **WHEN** a host subclasses the public extension contract and explicitly registers its instance without the CLI extra
- **THEN** registration works through the new public surface without requiring an artifact-only wrapper or compatibility alias, and artifact queries retain their existing eligibility and policy semantics
