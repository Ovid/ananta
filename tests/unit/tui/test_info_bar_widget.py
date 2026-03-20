"""Tests for info bar Textual widget."""

from textual.app import App, ComposeResult

from ananta.tui.widgets.info_bar import InfoBar


class InfoBarApp(App[None]):
    """Minimal app for testing InfoBar."""

    def compose(self) -> ComposeResult:
        yield InfoBar(project_name="test-project")


def _get_content(bar: InfoBar) -> str:
    """Extract the text content from an InfoBar widget."""
    return bar.content


class TestInfoBarWidget:
    """Tests for InfoBar Textual widget."""

    async def test_initial_render(self) -> None:
        """Info bar renders with project name on startup."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            text = _get_content(bar)
            assert "test-project" in text

    async def test_update_tokens(self) -> None:
        """Updating tokens refreshes the display."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            bar.update_tokens(prompt=5000, completion=1000)
            text = _get_content(bar)
            assert "6,000" in text
            assert "5,000" in text

    async def test_update_phase(self) -> None:
        """Updating phase refreshes the display."""
        async with InfoBarApp().run_test() as pilot:
            bar = pilot.app.query_one(InfoBar)
            bar.update_progress(elapsed=5.2, iteration=2, step="Generating code")
            text = _get_content(bar)
            assert "5.2s" in text
            assert "Iteration 2" in text
