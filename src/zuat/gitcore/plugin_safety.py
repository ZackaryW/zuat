"""Durable plugin event envelopes admit domain metadata, not native payloads."""

from zuat.utils.plugin_state import metadata_identifier


def plugin_event(before, after, metadata):
    return metadata.get("state_kind") == "plugin-lifecycle" or any(
        item.ref.kind == "plugin" or item.evidence.get("provider") == "plugin"
        for item in (*before, *after)
    )


def clean_metadata(metadata):
    scalar_keys = {
        "state_kind",
        "plugin_agent",
        "plugin_context",
        "reverted_kind",
        "from_profile",
        "to_profile",
        "reverts",
        "restores",
        "interrupted_operation_id",
        "interrupted_kind",
        "observation_identity",
        "observation_context",
        "policy_key",
        "policy",
        "artifact_id",
        "bundle_id",
        "build_revision",
    }
    cleaned = {}
    for key, value in metadata.items():
        if key in scalar_keys and value is not None:
            cleaned[key] = metadata_identifier(value)
        elif key == "observation_agents" and isinstance(value, list):
            cleaned[key] = [metadata_identifier(agent) for agent in value]
        elif key == "plugin_ref" and isinstance(value, dict):
            from zuat.specs.native import PluginRef

            cleaned[key] = PluginRef(**value).to_dict()
        elif key == "intended_revision" and isinstance(value, dict):
            from zuat.specs.native import PluginRevision

            cleaned[key] = PluginRevision(**value).to_dict()
    return cleaned
