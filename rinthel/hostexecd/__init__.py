"""hostexecd: a small FastAPI process that runs shell commands on the host for
the ``rinthel_host_exec`` tool of an admin's Session in Deck. The daemon starts
and stops it as a managed service (Linux only); it is kept apart from
``rinthel_tui`` so its blast radius is its own. See ``docs/07-host-exec.md``."""

__version__ = "0.1.0"
