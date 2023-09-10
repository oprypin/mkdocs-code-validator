from __future__ import annotations

import collections
import concurrent.futures
import functools
import logging
import os
import shlex
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping, MutableSequence

from mkdocs.config import Config
from mkdocs.config import config_options as opt
from mkdocs.plugins import BasePlugin

if TYPE_CHECKING:
    from markdown import Markdown
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.pages import Page

log = logging.getLogger(f"mkdocs.plugins.{__name__}")
basic_log = logging.getLogger(__name__)
basic_log.propagate = False


class IdentifierConfig(Config):
    language = opt.Type(str)
    validators = opt.ListOfItems(opt.Type(str), default=[])


class _IdentifierConfigs(opt.BaseConfigOption[Mapping[str, IdentifierConfig]]):
    def __init__(self):
        super().__init__()
        self.option_type = opt.DictOfItems(opt.SubConfig(IdentifierConfig))

    def run_validation(self, value: object) -> Mapping[str, IdentifierConfig]:
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    v.setdefault("language", k)
        return self.option_type.run_validation(value)


_Result = collections.namedtuple("_Result", "file src command future")


class PluginConfig(Config):
    enabled = opt.Type(bool, default=True)
    identifiers = _IdentifierConfigs()


class CodeValidatorPlugin(BasePlugin[PluginConfig]):
    def on_config(self, config: MkDocsConfig, **kwargs) -> MkDocsConfig:
        self.enabled = self.config.enabled

        fences = (
            config.setdefault("mdx_configs", {})
            .setdefault("pymdownx.superfences", {})
            .setdefault("custom_fences", [])
        )
        for ident, ident_config in self.config.identifiers.items():
            fence = {
                "name": ident,
                "class": ident,
                "validator": self.validator,
                "format": functools.partial(self.formatter, ident_config),
            }
            fences.append(fence)
        return config

    def on_pre_build(self, config: MkDocsConfig, **kwargs):
        self._pool = concurrent.futures.ThreadPoolExecutor(5, thread_name_prefix=__name__)
        self._results: MutableSequence[_Result] = collections.deque()

    def on_page_markdown(self, markdown: str, page: Page, **kwargs) -> str:
        self.current_file = page.file.src_uri
        self._check_errors(False)
        return markdown

    def on_post_build(self, config: MkDocsConfig, **kwargs):
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
        class_name: str | None,
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
