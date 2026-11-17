"""The errors of Local models. The HTTP layer maps each to its status."""


class CatalogUnavailable(Exception):
    """The catalog file exists but cannot be read as a catalog."""


class UnknownModel(Exception):
    """No catalog entry has that id."""


class NotActivable(Exception):
    """The entry exists but cannot be activated (its problem is the message)."""


class TurnsInFlight(Exception):
    """A turn is being generated: switching now would cut it."""
