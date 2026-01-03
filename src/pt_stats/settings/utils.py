from collections.abc import Mapping, Sequence
import os
from typing import Any
import re as regex

def replace_env_vars(obj: Mapping | Sequence, *, _path=None) -> Any:
    """
    Recursively replace environment variable placeholders in the given object.
    
    If a string value has the format "${ENV_VAR}", it will be replaced by the
    value of the environment variable "ENV_VAR".
    """
    
    pattern = regex.compile(r'^\$\{([^}]+)\}$')
    if _path is None:
        _path = "#"
    
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if isinstance(value, str):
                match = pattern.match(value)
                if match:
                    env_var = match.group(1)
                    env_value = os.getenv(env_var) or ""
                    obj[key] = env_value # type: ignore
            
            elif isinstance(value, (Mapping, Sequence)):
                obj[key] = replace_env_vars(value, _path=f"{_path}[{key!r}]") # type: ignore
        return obj
    
    elif isinstance(obj, Sequence) and not isinstance(obj, str):
        for idx, item in enumerate(obj):
            if isinstance(item, str):
                match = pattern.match(item)
                if match:
                    env_var = match.group(1)
                    env_value = os.getenv(env_var) or ""
                    obj[idx] = env_value # type: ignore
            
            elif isinstance(item, (Mapping, Sequence)):
                obj[idx] = replace_env_vars(item, _path=f"{_path}[{idx}]") # type: ignore
        return obj
    
    else:
        raise TypeError(f"Unsupported type at {_path}: {type(obj)}")

