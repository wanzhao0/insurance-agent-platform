from app.plugins.base import DomainPlugin
from app.plugins.insurance import INSURANCE_PLUGIN


_PLUGINS: dict[str, DomainPlugin] = {INSURANCE_PLUGIN.plugin_id: INSURANCE_PLUGIN}


def load_domain_plugin(plugin_id: str) -> DomainPlugin:
    try:
        return _PLUGINS[plugin_id]
    except KeyError as exc:
        supported = ", ".join(sorted(_PLUGINS))
        raise ValueError(
            f"unsupported domain plugin '{plugin_id}'; available: {supported}"
        ) from exc


def registered_plugins() -> list[DomainPlugin]:
    return list(_PLUGINS.values())
