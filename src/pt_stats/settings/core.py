from pydantic import BaseModel, ConfigDict, PrivateAttr
import pydantic
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from typing import Protocol, Self, Any, IO, TypeVar, Callable, ParamSpec
import typing
import os
from pathlib import Path
import textwrap
import re as regex
from . import utils

class Settings(BaseModel):
    """
    Base class for configuration settings with YAML serialization/deserialization
    that preserves comments.
    """
    
    model_config = ConfigDict(extra='forbid')
    
    # Internal attributes for preserving the YAML with comments
    _yaml: CommentedMap = PrivateAttr(default_factory=lambda: CommentedMap())

    @classmethod
    def from_yaml(
        cls, 
        src: str | os.PathLike | bytes | bytearray | IO[str] | IO[bytes],
        *,
        replace_env_vars: bool = False
    ) -> Self:
        """
        Load settings from a YAML file or file-like object, preserving comments.
        
        If `replace_env_vars` is True, environment variables in the format
        "${ENV_VAR}" will be replaced with their corresponding values.
        """
        
        yaml = YAML(typ="rt")
        yaml.preserve_quotes = True
        
        # Load the YAML file
        if isinstance(src, (str, os.PathLike)):
            src = Path(src)
            with open(src, 'r', encoding='utf-8') as f:
                raw_yaml = yaml.load(f)
        
        elif isinstance(src, (bytes, bytearray)) or hasattr(src, 'read'):
            raw_yaml = yaml.load(src)
        
        else:
            raise TypeError(f"Unsupported type for 'src': {type(src)}")
        
        # Optionally replace environment variables
        if replace_env_vars:
            raw_yaml = utils.replace_env_vars(raw_yaml)
        
        # Validate the settings
        instance = cls.model_validate(raw_yaml)
        
        # Attach the YAML and link children
        instance._link_children(raw_yaml)
        return instance
    
    def _link_children(self, raw_yaml) -> None:
        """
        Walk through all fields to find nested Settings instances and link set
        their pointers.
        """
        self._yaml = raw_yaml
        for field_name, value in self:
            if isinstance(value, Settings):
                nested_yaml = raw_yaml.get(field_name, CommentedMap())
                value._link_children(nested_yaml)
                
            elif isinstance(value, list):
                nested_yaml = raw_yaml.get(field_name, CommentedSeq())
                for idx, item in enumerate(value):
                    if isinstance(item, Settings):
                        item._link_children(nested_yaml[idx] if idx < len(nested_yaml) else CommentedMap())
    
    def to_yaml(
        self, 
        dst: str | os.PathLike | bytes | bytearray | IO[str] | IO[bytes], *, 
        enable_comments: bool=True,
        fill_default_comments: bool=False,
        comment_width: int = 80
    ) -> None:
        if isinstance(dst, (str, os.PathLike)):
            dst = Path(dst)
            with open(dst, 'w', encoding='utf-8') as f:
                self.to_yaml(f, fill_default_comments=fill_default_comments, comment_width=comment_width)
            return
        
        # Now dst must be a file-like object
        if enable_comments == False:
            # Simple dump without comments
            yaml = YAML()
            yaml.dump(self.model_dump(), dst)
            return
        
        # Dump with comment preservation
        yaml = YAML(typ="rt")
        yaml.indent(mapping=2, sequence=4, offset=2)
        yaml.preserve_quotes = True
        
        ## Update the original YAML structure with current values
        self._update_yaml(
            cur_indent=0,
            fill_default_comments=fill_default_comments,
            comment_width=comment_width
        )
        yaml.dump(self._yaml, dst)
        
    def _update_yaml(
        self,
        *,
        cur_indent: int = 0,
        fill_default_comments: bool = False,
        comment_width: int = 80
    ):
        """
        Update the internal _yaml CommentedMap with current values from the
        Settings instance, preserving comments.
        """
        cmap = self._yaml
        first_element = True
        for field_name, value in self:
            if isinstance(value, Settings):
                value._update_yaml(
                    cur_indent=cur_indent + 2,
                    fill_default_comments=fill_default_comments,
                    comment_width=comment_width
                )
                cmap[field_name] = value._yaml
            
            elif isinstance(value, list):
                # List support is limited.
                #
                # The challenge is that we cannot easily map items from the
                # original list to the new list. If it mismatches, it would be a
                # mess to merge the inner values and comments.
                #
                # For now, if it is a list of Settings, we will just regenerate
                # the entire list with comments. Otherwise, a new list will be
                # created without comments.
                
                if all(isinstance(item, Settings) for item in value):
                    cseq = CommentedSeq()
                    cmap[field_name] = cseq
                    
                    for item in value:
                        item._update_yaml(
                            cur_indent=cur_indent + 4,
                            fill_default_comments=fill_default_comments,
                            comment_width=comment_width
                        )
                        cseq.append(item._yaml)
                else:
                    cmap[field_name] = self.model_dump(include={field_name})[field_name]
            
            else:
                cmap[field_name] = value
            
            if fill_default_comments:
                comment = self.get_comment(field_name, comment_width=comment_width)
                if comment is not None:
                    cmap.yaml_set_comment_before_after_key(
                        field_name, 
                        before=("\n" if not first_element else "") + comment,
                        indent=cur_indent
                    )
            
            first_element = False
    
    
    @classmethod
    def get_comment(cls, field_name: str, /, comment_width: int = 80) -> str | None:
        field_info = cls.model_fields.get(field_name)
        if field_info is None:
            raise ValueError(f"Field '{field_name}' not found in model '{cls.__name__}'")
        
        schema_extra = field_info.json_schema_extra or {}
        comment = schema_extra.get('comment', None)
        if comment is None:
            return None
        
        if not isinstance(comment, str):
            raise TypeError(f"Comment for field '{field_name}' must be a string, got {type(comment)}")
        
        # add a leading newline for better formatting
        return '\n'.join(textwrap.wrap(comment, width=comment_width))



def SettingField(comment: str | None = None, *args, **kwargs) -> Any:
    """
    A wrapper around pydantic.Field that extends a field's json_schema_extra for
    use in `Settings` classes.
    
    Other arguments are the same as pydantic.Field.
    """
    json_schema_extra = kwargs.get('json_schema_extra', {})
    if comment is not None:
        json_schema_extra['comment'] = comment
        
    kwargs['json_schema_extra'] = json_schema_extra
    field = pydantic.Field(*args, **kwargs)
    return field
