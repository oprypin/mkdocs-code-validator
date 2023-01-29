# mkdocs-code-validator

**Checks Markdown code blocks in a [MkDocs][] site against user-defined actions**

[![PyPI](https://img.shields.io/pypi/v/mkdocs-code-validator)](https://pypi.org/project/mkdocs-code-validator/)
[![License](https://img.shields.io/github/license/oprypin/mkdocs-code-validator)](https://github.com/oprypin/mkdocs-code-validator/blob/master/LICENSE.md)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/oprypin/mkdocs-code-validator/ci.yml.svg)](https://github.com/oprypin/mkdocs-code-validator/actions?query=event%3Apush+branch%3Amaster)

```shell
pip install mkdocs-code-validator
```

## Usage

Activate the plugin in **mkdocs.yml**. The `identifiers` config is mandatory. And the plugin **doesn't work without [pymdownx.superfences][]**:

```yaml
plugins:
  - search
  - code-validator:
      identifiers:
        bash:
          validators:
            - grep a
markdown_extensions:
  - pymdownx.superfences
```

The above contrived config checks that every <code>```bash</code> code block in the Markdown files of this MkDocs site must contain the letter "a", otherwise a warning will appear.

The content of each code block is piped as stdin to the command. The exit code of the command is what's checked: a non-zero code will produce a warning (which in MkDocs you can make fatal with the `--strict` flag). The output of the command is not used in any way, only preserved on the screen as part of a warning.

You can add any number of identifiers, and within them any number of `validators` commands, each of them has the ability to produce a warning.

If stdin is not usable with your command, the input can be passed as a temporary file instead -- that is done if the command contains the exact argument `$<` (which is then replaced with a file path). For the above example, changing the command to `grep a $<` would be equivalent (other than technicalities).

The commands do *not* allow freeform shell syntax, it's just one subprocess to call with its arguments. To explicitly opt into a shell, just run it as (e.g.) `sh -c 'if grep a; then exit 1; fi'`. Or, with a temporary file: `sh -c 'if grep a "$1"; then exit 1; fi' $<`.

The definition of what a code block is is all according to the [pymdownx.superfences][] extension. It must be enabled; the plugin won't do anything without it.


[mkdocs]: https://www.mkdocs.org/
[documentation site]: https://oprypin.github.io/mkdocs-code-validator
[pymdownx.superfences]: https://facelessuser.github.io/pymdown-extensions/extensions/superfences/
