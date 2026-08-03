"""CLI entrypoint for chatpost."""

import click

from chatpost import __version__
from chatpost.commands.zhihu import zhihu_group


@click.group()
@click.version_option(__version__, prog_name="chatpost")
def main() -> None:
    """chatpost command line interface."""


main.add_command(zhihu_group)


if __name__ == "__main__":
    main()
