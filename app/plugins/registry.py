"""内置行业插件注册表。"""

from app.plugins.base import DomainPlugin
from app.plugins.insurance import INSURANCE_PLUGIN


_PLUGINS: dict[str, DomainPlugin] = {INSURANCE_PLUGIN.plugin_id: INSURANCE_PLUGIN}


def load_domain_plugin(plugin_id: str) -> DomainPlugin:
    """按配置载入行业插件，并在启动阶段尽早暴露无效插件 ID。"""
    try:
        return _PLUGINS[plugin_id]
    except KeyError as exc:
        supported = ", ".join(sorted(_PLUGINS))
        raise ValueError(
            f"unsupported domain plugin '{plugin_id}'; available: {supported}"
        ) from exc


def registered_plugins() -> list[DomainPlugin]:
    """返回管理后台可展示的全部已注册插件。"""
    return list(_PLUGINS.values())
