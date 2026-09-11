from app.cities.base import BaseCityRules
from app.cities.herzliya.rules import HerzliyaCityRules
from app.cities.tel_aviv.rules import TelAvivCityRules

CITY_REGISTRY: dict[str, type[BaseCityRules]] = {
    "herzliya": HerzliyaCityRules,
    "tel_aviv": TelAvivCityRules,
}


def get_city_rules(city_code: str) -> BaseCityRules:
    try:
        return CITY_REGISTRY[city_code]()
    except KeyError as exc:
        raise ValueError(f"No city strategy registered for '{city_code}'") from exc


__all__ = ["BaseCityRules", "CITY_REGISTRY", "get_city_rules"]
