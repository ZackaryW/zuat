## MODIFIED Requirements

### Requirement: Generic artifact extension registration

Callers SHALL be able to register an explicitly supplied instance of the public subclassable Zuat extension contract by identifier and extension contract version. Artifact location SHALL be optional; when provided, it SHALL use installed plugin context without requiring Zuat to understand artifact-domain contents. Extension identity and contract version SHALL remain separate from native plugin identity and installed version. Duplicate conflicting registrations SHALL be rejected explicitly; re-registering the same unchanged instance SHALL be idempotent. Service-local registration SHALL NOT leak into other services; process-level registration SHALL supply defaults to subsequently created services without retroactively changing existing services.

Registration SHALL NOT invoke artifact location or lifecycle callbacks, install plugins, change native activation, grant source trust, or persist extension objects, code or artifact contents. Reopening persistent state SHALL NOT automatically load or execute extensions. A registered extension with no artifact location behavior SHALL produce no eligible artifacts, not fabricated paths. Existing provider, containment, revision, activation and policy checks SHALL apply unchanged to artifact resolution through the generalized contract.

#### Scenario: Registered extension resolves an artifact

- **WHEN** an extension is registered and an eligible installed plugin supplies its artifact
- **THEN** artifact resolution returns provider-bound references and transient resolved paths through the extension contract

#### Scenario: Unknown extension

- **WHEN** a caller requests resolution or policy changes for an unregistered extension
- **THEN** Zuat reports an unknown extension without modifying plugin or policy state

#### Scenario: Extension without artifact location

- **WHEN** a registered extension does not provide artifact location behavior
- **THEN** resolution returns no eligible artifacts and status reports artifact unavailability without treating registration as installation or invoking bundle operations

#### Scenario: Explicit registration is inert

- **WHEN** a host registers an extension whose artifact locator would perform work if invoked
- **THEN** registration validates and stores the runtime registration without invoking the locator, native commands or lifecycle callbacks and without writing extension code to persistent state

#### Scenario: Conflicting registration preserves the original

- **WHEN** another extension instance attempts to claim an already registered identifier
- **THEN** registration rejects the conflict and subsequent resolution uses the original registration, while re-registering the original unchanged instance is a no-op

#### Scenario: Registration scopes remain independent

- **WHEN** a host registers an extension on one service or registers a process default after another service has been created
- **THEN** the service-local registration affects only that service and the later default applies only to subsequently created services
