from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components.conversation import async_register_tool

from homeassistant.helpers import history


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up custom OpenAI tools."""


    # Tool 1: Query history (last known state)
    async def query_history(entity_id: str):
        state = history.get_last_state(hass, entity_id)
        if state:
            return {
                "entity_id": entity_id,
                "state": state.state,
                "last_changed": str(state.last_changed),
            }

        return {"error": f"No history found for {entity_id}"}

    # Tool 2: Get device info (attributes and metadata)
    async def get_device_info(entity_id: str):
        state = hass.states.get(entity_id)
        if not state:
            return {"error": f"Entity {entity_id} not found"}
        return {
            "entity_id": entity_id,
            "state": state.state,

            "attributes": state.attributes,
            "last_changed": str(state.last_changed),
        }

    # Tool 3: Control scenes (activate/deactivate)
    async def scene_control(scene_id: str, action: str):
        if not scene_id.startswith("scene."):
            return {"error": "scene_id must start with 'scene.'"}
        service = "turn_on" if action == "activate" else "turn_off"
        await hass.services.async_call("scene", service, {"entity_id": scene_id})
        return {"scene_id": scene_id, "action": action, "status": "done"}

    # Tool 4: Control automations (enable/disable/trigger)
    async def automation_control(automation_id: str, action: str):
        if not automation_id.startswith("automation."):
            return {"error": "automation_id must start with 'automation.'"}
        if action == "enable":
            service = "turn_on"
        elif action == "disable":
            service = "turn_off"
        elif action == "trigger":
            service = "trigger"
        else:
            return {"error": "action must be enable, disable, or trigger"}
        await hass.services.async_call("automation", service, {"entity_id": automation_id})
        return {"automation_id": automation_id, "action": action, "status": "done"}

    # Register all tools
    async_register_tool(hass, "query_history", query_history,
                        description="Get the last known state and timestamp for an entity.")
    async_register_tool(hass, "get_device_info", get_device_info,
                        description="Get attributes and metadata for an entity.")
    async_register_tool(hass, "scene_control", scene_control,
                        description="Activate or deactivate a scene.")
    async_register_tool(hass, "automation_control", automation_control,
                        description="Enable, disable, or trigger an automation.")

    return True

