import collections
import concurrent.futures
import dataclasses
import functools
import logging
import os
import shlex
import subprocess
import tempfile
from typing import Any, List, Mapping, MutableMapping, Optional

import mkdocs.utils
from markdown import Markdown
from mkdocs.config import Config, config_options
from mkdocs.config.base import ValidationError  # pytype: disable=import-error
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

log = logging.getLogger(f"mkdocs.plugins.{__name__}")
log.addFilter(mkdocs.utils.warning_filter)
basic_log = logging.getLogger(__name__)
basic_log.propagate = False


@dataclasses.dataclass
class IdentifierConfig:
    language: str
    validators: List[str]


class _IdentifierConfigs(config_options.OptionallyRequired):
    def __init__(self):
        super().__init__(required=True)

    def run_validation(self, value):
        if not isinstance(value, dict):
            raise ValidationError(f"Expected a dict, got {type(value)}")

        for ident, config in value.items():
            if not isinstance(config, dict) or not config:
                raise ValidationError(
                    f"Expected a dict as the value for {ident!r}, got {type(config)}"
                )

            config.setdefault("language", ident)
            config.setdefault("validators", [])
            try:
                value[ident] = config = IdentifierConfig(**config)
            except TypeError as e:
                raise ValidationError(str(e))

            if not isinstance(config.language, (str, type(None))):
                raise ValidationError(
                    f"Expected 'language' to be a string, got {type(config.language)}"
                )
            if not isinstance(config.validators, list):
                raise ValidationError(
                    f"Expected 'validators' to be a list of strings, got {type(config.validators)}"
                )
            for v in config.validators:
                if not isinstance(v, str):
                    raise ValidationError(
                        f"Expected 'validators' to be a list of strings, but one item is {type(v)}"
                    )

        return value


_Result = collections.namedtuple("_Result", "file src command future")


class CodeValidatorPlugin(BasePlugin):
    config_scheme = (
        ("enabled", config_options.Type(bool, default=True)),
        ("enable_on_env", config_options.Type(str, default=None)),
        ("identifiers", _IdentifierConfigs()),
    )

    def on_config(self, config: Config, **kwargs) -> Config:
        enable_on_env = self.config["enable_on_env"]
        self.enabled = self.config["enabled"] or (
            enable_on_env and _strtobool(os.getenv(enable_on_env, "0"))
        )

        fences = (
            config.setdefault("mdx_configs", {})
            .setdefault("pymdownx.superfences", {})
            .setdefault("custom_fences", [])
        )
        for ident, ident_config in self.config["identifiers"].items():
            fence = {
                "name": ident,
                "class": ident,
                "validator": self.validator,
                "format": functools.partial(self.formatter, ident_config),
            }
            fences.append(fence)
        return config

    def on_pre_build(self, config: Config, **kwargs):
        self._pool = concurrent.futures.ThreadPoolExecutor(5, thread_name_prefix=__name__)
        self._results = collections.deque()

    def on_page_markdown(self, markdown: str, page: Page, **kwargs) -> str:
        self.current_file = page.file.src_path
        self._check_errors(False)
        return markdown

    def on_post_build(self, config: Config, **kwargs):
        self._check_errors(True)
        for r in self._results:
            r.future.cancel()
        self._pool.shutdown()

    def validator(
        self,
        language: str,
        inputs: Mapping[str, Any],
        options: MutableMapping[str, Any],
        attrs: MutableMapping[str, Any],
        md: Markdown,
    ):
        return (
            self._get_default_fence(md)["validator"](language, inputs, options, attrs, md)
            and "nocheck" not in inputs
        )

    def formatter(
        self,
        config: IdentifierConfig,
        src: str,
        language: str,
        class_name: Optional[str],
        options: Mapping[str, Any],
        md: Markdown,
        **kwargs,
    ):
        if self.enabled:
            for validator_cmd in config.validators:
                assert isinstance(validator_cmd, str)
                future = self._pool.submit(_validate, src, validator_cmd)
                self._results.append(_Result(self.current_file, src, validator_cmd, future))

        kwargs.setdefault("classes", []).append(language)

        return self._get_default_fence(md)["formatter"](
            src=src,
            language=config.language,
            class_name=class_name,
            options=options,
            md=md,
            **kwargs,
        )

    @classmethod
    def _get_default_fence(cls, md: Markdown) -> Mapping[str, Any]:
        return md.preprocessors["fenced_code_block"].extension.superfences[0]

    def _check_errors(self, all_errors):
        while self._results and (all_errors or self._results[0].future.done()):
            file, src, command, future = self._results.popleft()
            try:
                future.result(timeout=300)
            except subprocess.CalledProcessError as e:
                msg = (
                    f"In file '{file}' a code block failed the check `{command}`:",
                    "-------- Input --------",
                    src,
                    "",
                    "-------- Output --------",
                    e.stdout.decode(errors="replace").rstrip(),
                )
                log.warning(msg[0])
                basic_log.warning("\n".join(msg[1:]))


@functools.lru_cache(maxsize=None)
def _validate(src: str, command: str):
    src += "\n"
    cmd = shlex.split(command)
    if "$<" in cmd:
        f = tempfile.NamedTemporaryFile(delete=False)
        cmd = [f.name if s == "$<" else s for s in cmd]
        try:
            with f:
                f.write(src.encode())
            log.debug(cmd)
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        finally:
            try:
                os.remove(f.name)
            except OSError:
                pass
    else:
        log.debug(cmd)
        subprocess.run(
            cmd, input=src.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
        )


def _strtobool(val: str) -> bool:
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    if val in ("n", "no", "f", "false", "off", "0"):
        return False
    raise ValueError("invalid truth value %r" % val)
