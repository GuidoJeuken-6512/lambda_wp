"""Platform for Lambda WP sensor integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_TYPES,
    HP_SENSOR_TEMPLATES,
    BOIL_SENSOR_TEMPLATES,
    HC_SENSOR_TEMPLATES,
    BUFF_SENSOR_TEMPLATES,
    SOL_SENSOR_TEMPLATES,
)
from .coordinator import LambdaDataUpdateCoordinator
from .utils import build_device_info, generate_base_addresses
from .const_mapping import HP_ERROR_STATE  # noqa: F401
from .const_mapping import HP_STATE  # noqa: F401
from .const_mapping import HP_RELAIS_STATE_2ND_HEATING_STAGE  # noqa: F401
from .const_mapping import HP_OPERATING_STATE  # noqa: F401
from .const_mapping import HP_REQUEST_TYPE  # noqa: F401
from .const_mapping import BOIL_CIRCULATION_PUMP_STATE  # noqa: F401
from .const_mapping import BOIL_OPERATING_STATE  # noqa: F401
from .const_mapping import HC_OPERATING_STATE  # noqa: F401
from .const_mapping import HC_OPERATING_MODE  # noqa: F401
from .const_mapping import BUFF_OPERATING_STATE  # noqa: F401
from .const_mapping import BUFF_REQUEST_TYPE  # noqa: F401
from .const_mapping import SOL_OPERATING_STATE  # noqa: F401
from .const_mapping import MAIN_CIRCULATION_PUMP_STATE  # noqa: F401
from .const_mapping import MAIN_AMBIENT_OPERATING_STATE  # noqa: F401
from .const_mapping import MAIN_E_MANAGER_OPERATING_STATE  # noqa: F401

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Lambda Heat Pumps sensors."""
    _LOGGER.debug("Setting up Lambda sensors for entry %s", entry.entry_id)

    # Get coordinator from hass.data
    coordinator_data = hass.data[DOMAIN][entry.entry_id]
    if not coordinator_data or "coordinator" not in coordinator_data:
        _LOGGER.error("No coordinator found for entry %s", entry.entry_id)
        return

    coordinator = coordinator_data["coordinator"]
    _LOGGER.debug("Found coordinator: %s", coordinator)

    # Get device counts from config
    num_hps = entry.data.get("num_hps", 1)
    num_boil = entry.data.get("num_boil", 1)
    num_buff = entry.data.get("num_buff", 0)
    num_sol = entry.data.get("num_sol", 0)
    num_hc = entry.data.get("num_hc", 1)

    # Hole den Legacy-Modbus-Namen-Switch aus der Config
    use_legacy_modbus_names = entry.data.get("use_legacy_modbus_names", False)
    name_prefix = entry.data.get("name", "").lower().replace(" ", "")

    # Create sensors for each device type using a generic loop
    sensors = []

    TEMPLATES = [
        ("hp", num_hps, HP_SENSOR_TEMPLATES),
        ("boil", num_boil, BOIL_SENSOR_TEMPLATES),
        ("buff", num_buff, BUFF_SENSOR_TEMPLATES),
        ("sol", num_sol, SOL_SENSOR_TEMPLATES),
        ("hc", num_hc, HC_SENSOR_TEMPLATES),
    ]

    for prefix, count, template in TEMPLATES:
        for idx in range(1, count + 1):
            base_address = generate_base_addresses(prefix, count)[idx]
            for sensor_id, sensor_info in template.items():
                address = base_address + sensor_info["relative_address"]
                if coordinator.is_register_disabled(address):
                    _LOGGER.debug(
                        "Skipping sensor %s (address %d) because register is "
                        "disabled",
                        f"{prefix}{idx}_{sensor_id}",
                        address,
                    )
                    continue
                device_class = sensor_info.get("device_class")
                if not device_class and sensor_info.get("unit") == "°C":
                    device_class = SensorDeviceClass.TEMPERATURE
                elif not device_class and sensor_info.get("unit") == "W":
                    device_class = SensorDeviceClass.POWER
                elif not device_class and sensor_info.get("unit") == "Wh":
                    device_class = SensorDeviceClass.ENERGY

                # Prüfe auf Override-Name
                override_name = None
                if (
                    use_legacy_modbus_names
                    and hasattr(coordinator, "sensor_overrides")
                ):
                    override_name = coordinator.sensor_overrides.get(
                        f"{prefix}{idx}_{sensor_id}"
                    )
                if override_name:
                    name = override_name
                    sensor_id_final = f"{prefix}{idx}_{sensor_id}"
                    # Data key (original format)
                    entity_id = (
                        f"sensor.{name_prefix}_{override_name}"
                    )
                    unique_id = f"{name_prefix}_{override_name}"
                else:
                    prefix_upper = prefix.upper()
                    if (
                        prefix == "hc"
                        and sensor_info.get("device_type") == "Climate"
                    ):
                        name = (
                            sensor_info["name"].format(idx)
                        )
                        if use_legacy_modbus_names:
                            sensor_id_final = f"{prefix}{idx}_{sensor_id}"
                            entity_id = (
                                f"sensor.{name_prefix}_{prefix}{idx}_"
                                f"{sensor_id}"
                            )
                        else:
                            sensor_id_final = f"{prefix}{idx}_{sensor_id}"
                            entity_id = f"sensor.{sensor_id_final}"
                    else:
                        name = (
                            f"{prefix_upper}{idx} {sensor_info['name']}"
                        )
                        if use_legacy_modbus_names:
                            sensor_id_final = f"{prefix}{idx}_{sensor_id}"
                            entity_id = (
                                f"sensor.{name_prefix}_{prefix}{idx}_"
                                f"{sensor_id}"
                            )
                        else:
                            sensor_id_final = f"{prefix}{idx}_{sensor_id}"
                            entity_id = f"sensor.{sensor_id_final}"
                    unique_id = entity_id.replace("sensor.", "")

                device_type = (
                    prefix.upper() if prefix in [
                        "hp",
                        "boil",
                        "hc",
                        "buff",
                        "sol",
                    ]
                    else sensor_info.get("device_type", "main")
                )

                sensors.append(
                    LambdaSensor(
                        coordinator=coordinator,
                        entry=entry,
                        sensor_id=sensor_id_final,
                        name=name,
                        unit=sensor_info.get("unit", ""),
                        address=address,
                        scale=sensor_info.get("scale", 1.0),
                        state_class=sensor_info.get("state_class", ""),
                        device_class=device_class,
                        relative_address=sensor_info.get(
                            "relative_address", 0
                        ),
                        data_type=sensor_info.get("data_type", None),
                        device_type=device_type,
                        txt_mapping=sensor_info.get("txt_mapping", False),
                        precision=sensor_info.get("precision", None),
                        entity_id=entity_id,
                        unique_id=unique_id,
                    )
                )

    # General Sensors (SENSOR_TYPES)
    for sensor_id, sensor_info in SENSOR_TYPES.items():
        address = sensor_info["address"]
        if coordinator.is_register_disabled(address):
            _LOGGER.debug(
                "Skipping general sensor %s (address %d) because register is "
                "disabled",
                sensor_id,
                address,
            )
            continue
        device_class = sensor_info.get("device_class")
        if not device_class and sensor_info.get("unit") == "°C":
            device_class = SensorDeviceClass.TEMPERATURE
        elif not device_class and sensor_info.get("unit") == "W":
            device_class = SensorDeviceClass.POWER
        elif not device_class and sensor_info.get("unit") == "Wh":
            device_class = SensorDeviceClass.ENERGY

        # Name und Entity-ID
        if use_legacy_modbus_names and "override_name" in sensor_info:
            name = sensor_info["override_name"]
            sensor_id_final = sensor_info["override_name"]
            _LOGGER.info(
                f"Override name for sensor '{sensor_id}': '{name}' "
                f"wird als Name und sensor_id verwendet."
            )
        else:
            name = sensor_info["name"]
            sensor_id_final = sensor_id

        if use_legacy_modbus_names:
            entity_id = f"sensor.{name_prefix}_{sensor_id_final}"
        else:
            entity_id = f"sensor.{sensor_id_final}"

        sensors.append(
            LambdaSensor(
                coordinator=coordinator,
                entry=entry,
                sensor_id=sensor_id_final,
                name=name,
                unit=sensor_info.get("unit", ""),
                address=address,
                scale=sensor_info.get("scale", 1.0),
                state_class=sensor_info.get("state_class", ""),
                device_class=device_class,
                relative_address=sensor_info.get("address", 0),
                data_type=sensor_info.get("data_type", None),
                device_type=sensor_info.get("device_type", None),
                txt_mapping=sensor_info.get("txt_mapping", False),
                precision=sensor_info.get("precision", None),
                entity_id=entity_id,
            )
        )

    _LOGGER.debug(
        "Created %d sensors",
        len(sensors),
    )
    async_add_entities(sensors)


class LambdaSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Lambda sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: LambdaDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_id: str,
        name: str,
        unit: str,
        address: int,
        scale: float,
        state_class: str,
        device_class: SensorDeviceClass,
        relative_address: int,
        data_type: str,
        device_type: str,
        txt_mapping: bool = False,
        precision: int | float | None = None,
        entity_id: str | None = None,
        unique_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_id = sensor_id
        self._attr_name = name
        self._attr_unique_id = unique_id or sensor_id
        self.entity_id = entity_id or f"sensor.{sensor_id}"
        self._unit = unit
        self._address = address
        self._scale = scale
        self._state_class = state_class
        self._device_class = device_class
        self._relative_address = relative_address
        self._data_type = data_type
        self._device_type = device_type
        self._txt_mapping = txt_mapping
        self._precision = precision

        _LOGGER.debug(
            "Sensor initialized with ID: %s and config: %s",
            sensor_id,
            {
                "name": name,
                "unit": unit,
                "address": address,
                "scale": scale,
                "state_class": state_class,
                "device_class": device_class,
                "relative_address": relative_address,
                "data_type": data_type,
                "device_type": device_type,
                "txt_mapping": txt_mapping,
                "precision": precision,
            },
        )

        self._is_state_sensor = txt_mapping

        if self._is_state_sensor:
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None
            self._attr_suggested_display_precision = None
        else:
            self._attr_native_unit_of_measurement = unit
            if precision is not None:
                self._attr_suggested_display_precision = precision
            if unit == "°C":
                self._attr_device_class = SensorDeviceClass.TEMPERATURE
            elif unit == "W":
                self._attr_device_class = SensorDeviceClass.POWER
            elif unit == "Wh":
                self._attr_device_class = SensorDeviceClass.ENERGY
            if state_class:
                if state_class == "total":
                    self._attr_state_class = SensorStateClass.TOTAL
                elif state_class == "total_increasing":
                    self._attr_state_class = SensorStateClass.TOTAL_INCREASING
                elif state_class == "measurement":
                    self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        use_legacy_modbus_names = self.coordinator.entry.data.get(
            "use_legacy_modbus_names", False
        )
        if (
            use_legacy_modbus_names
            and hasattr(self.coordinator, "sensor_overrides")
        ):
            override_name = self.coordinator.sensor_overrides.get(
                self._sensor_id
            )
            if override_name:
                # Verwende den Override-Namen als sensor_id
                _LOGGER.debug(
                    "Overriding sensor_id from %s to %s",
                    self._sensor_id,
                    override_name,
                )
                self._sensor_id = override_name
                return override_name
        return self._attr_name

    @property
    def native_value(self) -> float | str | None:
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self._sensor_id)
        if value is None:
            return None
        if self._is_state_sensor:
            try:
                numeric_value = int(float(value))
            except (ValueError, TypeError):
                return f"Unknown state ({value})"

            # Extract base name without index
            # (e.g. "HP1 Operating State" -> "Operating State")
            base_name = self._attr_name
            if self._device_type and self._device_type.upper() in base_name:
                # Remove prefix and index (e.g. "HP1 " or "BOIL2 ")
                base_name = ' '.join(base_name.split()[1:])
            # Ersetze auch Bindestriche durch Unterstriche
            mapping_name = (
                f"{self._device_type.upper()}_"
                f"{base_name.upper().replace(' ', '_').replace('-', '_')}"
            )
            try:
                state_mapping = globals().get(mapping_name)
                if state_mapping is not None:
                    return state_mapping.get(
                        numeric_value,
                        f"Unknown state ({numeric_value})"
                    )
                _LOGGER.warning(
                    "No state mapping found f. sensor '%s' (tried mapping: %s)"
                    "with value %s. Sensor details: device_type=%s, "
                    "register=%d, data_type=%s. This sensor is marked as state"
                    "sensor (txt_mapping=True) but no corresponding mapping "
                    "dictionary was found.",
                    self._attr_name,
                    mapping_name,
                    numeric_value,
                    self._device_type,
                    self._relative_address,
                    self._data_type,
                )
                return f"Unknown mapping for state ({numeric_value})"
            except Exception as e:
                _LOGGER.error(
                    "Error accessing mapping dictionary: %s",
                    str(e),
                )
                return f"Error loading mappings ({numeric_value})"
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def device_info(self):
        """Return device info for this sensor."""
        return build_device_info(self._entry)
