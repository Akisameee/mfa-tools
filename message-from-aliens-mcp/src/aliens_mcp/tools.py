"""Shared tool entry points; operations and state live in GameService."""

from .service import GameService

service = GameService()

look_json = service.look_json

look = service.look

click = service.click

note = service.note

wait = service.wait

glyph = service.glyph

launch_game = service.launch_game

status = service.status

reset_session = service.reset_session
