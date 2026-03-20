"""Tests for output area widget."""

from textual.app import App, ComposeResult

from ananta.tui.widgets.output_area import OutputArea


class OutputAreaApp(App[None]):
    """Minimal app for testing OutputArea."""

    def compose(self) -> ComposeResult:
        yield OutputArea()


class TestOutputArea:
    """Tests for OutputArea widget."""

    async def test_add_user_message(self) -> None:
        """User messages are added to the output."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.add_user_message("Hello world")
            # Check that content was added
            assert output.query("Static")  # At least one Static widget

    async def test_add_response_markdown_on(self) -> None:
        """Response with markdown enabled renders Markdown widget."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = True
            output.add_response("**bold text**", thought_seconds=5.0)
            markdown_widgets = output.query("Markdown")
            assert len(markdown_widgets) > 0

    async def test_add_response_markdown_off(self) -> None:
        """Response with markdown disabled renders Static widget."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = False
            output.add_response("**bold text**", thought_seconds=3.0)
            # Should have Static widgets but no Markdown
            static_widgets = output.query("Static")
            assert len(static_widgets) > 0

    async def test_toggle_markdown(self) -> None:
        """Toggling markdown flips the flag."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            assert output.markdown_enabled is True  # default
            output.markdown_enabled = False
            assert output.markdown_enabled is False

    async def test_add_system_markdown_renders_markdown_when_enabled(self) -> None:
        """System markdown renders with Markdown widget when enabled."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = True
            output.add_system_markdown("## Heading\n\nSome **bold** text")
            markdown_widgets = output.query("Markdown")
            assert len(markdown_widgets) > 0

    async def test_add_system_markdown_renders_static_when_disabled(self) -> None:
        """System markdown renders with Static widget when markdown disabled."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.markdown_enabled = False
            output.add_system_markdown("## Heading\n\nSome **bold** text")
            # Should have Static but no Markdown
            markdown_widgets = output.query("Markdown")
            assert len(markdown_widgets) == 0
            static_widgets = output.query("Static")
            assert len(static_widgets) > 0

    async def test_focus_border_shown(self) -> None:
        """OutputArea shows a border when focused."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.focus()
            await pilot.pause()
            border = output.styles.border
            # At least one side should have a visible border type
            assert any(edge[0] not in ("", "none", "hidden") for edge in border)

    async def test_no_border_when_unfocused(self) -> None:
        """OutputArea has no visible border when not focused."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            pilot.app.set_focus(None)
            await pilot.pause()
            border = output.styles.border
            assert all(edge[0] in ("", "none", "hidden") for edge in border)

    async def test_clear_removes_all_children(self) -> None:
        """clear() removes all child widgets from the output area."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            output.add_user_message("Hello")
            output.add_user_message("World")
            output.add_system_message("Info")
            await pilot.pause()

            # Verify widgets exist before clear
            assert len(output.children) > 0

            output.clear()
            await pilot.pause()

            # All children should be removed
            assert len(output.children) == 0

    async def test_scroll_to_bottom_on_add(self) -> None:
        """Adding content scrolls to bottom."""
        async with OutputAreaApp().run_test() as pilot:
            output = pilot.app.query_one(OutputArea)
            for i in range(20):
                output.add_user_message(f"Message {i}")
            # After adding many messages, scroll position should be at bottom
            # (Textual handles this; we just verify no error)
