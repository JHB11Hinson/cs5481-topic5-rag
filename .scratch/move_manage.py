"""Move the manage control out of the list, and check the message rhythm.

With the gaps collapsed, "Manage" landed immediately above the first date group and read
as a second, competing heading. It now lives as an icon in the wordmark row; the selection
bar only exists while a selection is being made, so the default sidebar is: brand, new
chat, list — nothing else.
"""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("ragqa/niceui.py")
text = PATH.read_text(encoding="utf-8")

OLD_BRAND = """            with ui.row().classes("ds-brand w-full items-center"):
                html(WHALE)
                html('<div class="ds-wordmark">Doc<span>QA</span></div>')"""
NEW_BRAND = """            with ui.row().classes("ds-brand w-full items-center justify-between no-wrap"):
                with ui.row().classes("items-center no-wrap").style("gap: 8px"):
                    html(WHALE)
                    html('<div class="ds-wordmark">Doc<span>QA</span></div>')
                self.manage_button = (
                    ui.button(icon="checklist", on_click=self._toggle_manage)
                    .props("flat round dense size=sm color=grey-7")
                    .tooltip("Select conversations to delete")
                )"""
assert OLD_BRAND in text
text = text.replace(OLD_BRAND, NEW_BRAND, 1)

OLD_MANAGE = """            with ui.row().classes("w-full items-center justify-between ds-manage"):
                ui.button("Manage", on_click=self._toggle_manage).props("flat dense no-caps size=sm").classes("ds-foot")
                self.delete_button = (
                    ui.button("Delete", on_click=self._delete_selected)
                    .props("flat dense no-caps size=sm color=negative")
                    .classes("ds-foot")
                )
                self.delete_button.set_visibility(False)"""
NEW_MANAGE = """            # Only exists while selecting: the default sidebar is brand, new chat, list.
            self.manage_bar = ui.row().classes("w-full items-center justify-between ds-manage")
            with self.manage_bar:
                ui.checkbox("Select all", on_change=self._toggle_all).props("dense size=sm").classes("ds-foot")
                self.delete_button = ui.button("Delete", on_click=self._delete_selected).props(
                    "flat dense no-caps size=sm color=negative"
                )
            self.manage_bar.set_visibility(False)"""
assert OLD_MANAGE in text
text = text.replace(OLD_MANAGE, NEW_MANAGE, 1)

OLD_TOGGLE = """    def _toggle_manage(self) -> None:
        self.manage = not self.manage
        if not self.manage:
            self.selected.clear()
        self.delete_button.set_visibility(self.manage)
        self._refresh_list()"""
NEW_TOGGLE = """    def _toggle_manage(self) -> None:
        self.manage = not self.manage
        if not self.manage:
            self.selected.clear()
        self.manage_bar.set_visibility(self.manage)
        self.manage_button.props(f"color={'primary' if self.manage else 'grey-7'}")
        self._refresh_list()"""
assert OLD_TOGGLE in text
text = text.replace(OLD_TOGGLE, NEW_TOGGLE, 1)

with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("manage control moved into the wordmark row")
