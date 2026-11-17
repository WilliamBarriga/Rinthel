"""Composition of the identity area: takes the adapters and returns its
state, its router and its error table."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from rinthel_tui.api.adapters import Adapters
from rinthel_tui.api.errors import ErrorTable
from rinthel_tui.api.identity.routes import ERRORS, router
from rinthel_tui.identity.domain.ports import DeckSessions, Identity


@dataclass(frozen=True)
class IdentityArea:
    identity: Identity
    # ``None``: Deck is disabled and a deleted user has no Sessions to retire.
    deck_sessions: DeckSessions | None
    router: APIRouter
    errors: ErrorTable


def compose(adapters: Adapters) -> IdentityArea:
    return IdentityArea(
        identity=adapters.identity, deck_sessions=adapters.deck_sessions, router=router, errors=ERRORS
    )
