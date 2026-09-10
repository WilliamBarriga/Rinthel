import sys

from textual.app import App

from rinthel_tui import config
from rinthel_tui.theme.cyberpunk_theme import CYBERPUNK_THEME
from rinthel_tui.tui.screens.splash import SplashScreen


class RinthelApp(App):
    """Reemplaza rinthel-boot.sh — arranca en SplashScreen -> MenuScreen."""

    CSS_PATH = "theme/rinthel.tcss"
    TITLE = "RinthelTUI"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.register_theme(CYBERPUNK_THEME)
        self.theme = "cyberpunk"

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())


def main() -> None:
    try:
        config.CONFIG.apply_env()
    except config.ConfigError as exc:
        print(f"[rinthel] config inválida: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    RinthelApp().run()


if __name__ == "__main__":
    main()
