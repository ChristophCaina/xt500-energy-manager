"""Create the optional dashboard once, using HA's live Lovelace collections."""
from __future__ import annotations

import asyncio
import inspect
import logging
from urllib.parse import urlsplit

from homeassistant.components import persistent_notification
from homeassistant.components.lovelace.const import LOVELACE_DATA, ConfigNotFound
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import CONF_AUTO_DASHBOARD, DOMAIN, FRONTEND_URL

_LOGGER = logging.getLogger(__name__)
STRATEGY = "custom:xt500-energy-manager"
PATH = "xt500-energiemanager"


def _dashboard_collection(hass):
    """Use the existing collection, never a second writer of its storage file.

    HA exposes this collection through its bound dashboard-list handler.
    Keep this compatibility seam guarded: unsupported HA versions fail visibly.
    """
    handler = hass.data.get("websocket_api", {}).get("lovelace/dashboards/list")
    owner = getattr(inspect.unwrap(handler[0]), "__self__", None) if handler else None
    collection = getattr(owner, "storage_collection", None)
    if collection is None:
        raise HomeAssistantError("Dashboard-Verwaltung dieser HA-Version wird nicht unterstützt.")
    return collection


async def async_ensure_dashboard(hass, entry):
    """Do not recreate deliberately deleted dashboards or change existing layouts."""
    # Older entries have no flag and keep their existing manual dashboard workflow.
    if not entry.data.get(CONF_AUTO_DASHBOARD, False):
        return
    lock_key = f"{DOMAIN}_dashboard_lock"
    lock = hass.data.setdefault(lock_key, asyncio.Lock())
    async with lock:
        store = Store(hass, 1, f"{DOMAIN}.dashboard_setup")
        try:
            saved = await store.async_load() or {}
            if saved.get("completed"):
                return
            data = hass.data[LOVELACE_DATA]
            resources = data.resources
            if not resources.loaded:
                await resources.async_load()
                resources.loaded = True
            resource = next((r for r in resources.async_items()
                             if urlsplit(r["url"]).path == FRONTEND_URL), None)
            if resource is None:
                if not hasattr(resources, "async_create_item"):
                    raise HomeAssistantError("Bei YAML-Ressourcen bitte die XT500-JavaScript-Ressource manuell eintragen.")
                await resources.async_create_item({"res_type": "module", "url": FRONTEND_URL})
                await resources.store.async_save({"items": resources.async_items()})
            elif resource.get("type", resource.get("res_type")) != "module":
                raise HomeAssistantError("Die vorhandene XT500-Ressource muss ein JavaScript-Modul sein.")
            for path, dashboard in list(data.dashboards.items()):
                try:
                    config = await dashboard.async_load(False)
                except ConfigNotFound:
                    continue
                if config.get("strategy", {}).get("type") in (STRATEGY, "xt500-energy-manager"):
                    await store.async_save({"completed": True, "path": path})
                    persistent_notification.async_dismiss(hass, f"{DOMAIN}_dashboard_setup")
                    return
            collection = _dashboard_collection(hass)
            path = saved.get("pending_path", PATH)
            if "pending_path" not in saved:
                suffix = 2
                while path in data.dashboards or path in hass.data.get("frontend_panels", {}):
                    path = f"{PATH}-{suffix}"
                    suffix += 1
                await store.async_save({"pending_path": path})
            if path not in data.dashboards:
                await collection.async_create_item({"url_path": path, "title": "XT500 Energiemanager",
                    "icon": "mdi:home-battery", "show_in_sidebar": True, "require_admin": False})
                await collection.store.async_save({"items": collection.async_items()})
            dashboard = data.dashboards[path]
            try:
                config = await dashboard.async_load(False)
            except ConfigNotFound:
                config = None
            if config is not None:
                # A user filled the pending dashboard: preserve it rather than overwrite.
                await store.async_save({"completed": True, "path": path})
                persistent_notification.async_dismiss(hass, f"{DOMAIN}_dashboard_setup")
                return
            await dashboard.async_save({"strategy": {"type": STRATEGY, "dashboard_path": path}})
            await store.async_save({"completed": True, "path": path})
            persistent_notification.async_dismiss(hass, f"{DOMAIN}_dashboard_setup")
        except Exception as err:
            _LOGGER.exception("Automatische XT500-Dashboard-Einrichtung fehlgeschlagen")
            persistent_notification.async_create(hass,
                f"Das XT500-Dashboard konnte nicht automatisch eingerichtet werden: {err}. "
                "Bitte die Dashboard-Einrichtung in der Integrationsbeschreibung prüfen.",
                title="XT500 Dashboard", notification_id=f"{DOMAIN}_dashboard_setup")
