from __future__ import annotations

from typing import Any


def get_model_config_option(session: object) -> Any | None:
    for option in getattr(session, "config_options", []) or []:
        config = getattr(option, "root", option)
        if getattr(config, "category", None) == "model":
            return config
    return None


def list_model_config_values(session: object) -> list[str]:
    model_config = get_model_config_option(session)
    if model_config is None:
        return []

    values: list[str] = []
    for candidate in getattr(model_config, "options", []) or []:
        value = getattr(candidate, "value", None)
        if isinstance(value, str) and value not in values:
            values.append(value)
    return values


def list_available_model_ids(session: object) -> list[str]:
    model_ids = list_model_config_values(session)
    if model_ids:
        return model_ids

    models = getattr(session, "models", None)
    if models is None:
        return []

    values: list[str] = []
    for model in getattr(models, "available_models", []) or []:
        model_id = getattr(model, "model_id", None)
        if isinstance(model_id, str) and model_id not in values:
            values.append(model_id)
    return values


def format_available_model_choices(session: object) -> list[str]:
    labels: list[str] = []
    model_config = get_model_config_option(session)
    if model_config is not None:
        for candidate in getattr(model_config, "options", []) or []:
            value = getattr(candidate, "value", None)
            if not isinstance(value, str):
                continue
            name = getattr(candidate, "name", None)
            label = f"{name} ({value})" if name and name != value else value
            if label not in labels:
                labels.append(label)
        if labels:
            return labels

    models = getattr(session, "models", None)
    if models is None:
        return labels

    for model in getattr(models, "available_models", []) or []:
        model_id = getattr(model, "model_id", None)
        if not isinstance(model_id, str):
            continue
        name = getattr(model, "name", None)
        label = f"{name} ({model_id})" if name and name != model_id else model_id
        if label not in labels:
            labels.append(label)
    return labels


def resolve_model(session: object) -> tuple[str | None, str | None]:
    models = getattr(session, "models", None)
    if models is not None:
        current_model_id = getattr(models, "current_model_id", None)
        available_models = getattr(models, "available_models", []) or []
        for model in available_models:
            if getattr(model, "model_id", None) == current_model_id:
                return getattr(model, "name", None), current_model_id
        if current_model_id:
            return current_model_id, current_model_id

    model_config = get_model_config_option(session)
    if model_config is None:
        return None, None

    current_value = getattr(model_config, "current_value", None)
    for candidate in getattr(model_config, "options", []) or []:
        if getattr(candidate, "value", None) == current_value:
            return getattr(candidate, "name", None), current_value
    if current_value:
        return current_value, current_value

    return None, None
