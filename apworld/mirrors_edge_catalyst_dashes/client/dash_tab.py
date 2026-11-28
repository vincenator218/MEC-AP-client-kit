"""
The client's "Dashes" tab: every dash, whether its Dash Unlock is held, whether it is finished, its
stars, and the time to beat for the next star. Unlocked dashes first, in the game's dash order;
locked ones below. Rebuilt only when something it shows changes (checked once a second).

The rows come from plan.dash_board (pure, tested); this file is only the Kivy side, and is
imported from make_gui, so the client runs without it when there is no GUI.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView

from .plan import dash_board, race_time, stars_checked

if TYPE_CHECKING:
    from .client import MECDContext

HEADERS = ("Dash", "District", "Unlock", "Finish", "Stars", "Next star")
WIDTHS = (dp(230), dp(100), dp(90), dp(80), dp(70), dp(140))


def _cell(text: str, bold: bool = False, faded: bool = False, width: float = dp(100)) -> MDLabel:
    label = MDLabel(text=f"[b]{text}[/b]" if bold else text, markup=True, size_hint_x=None,
                    width=width, shorten=True, shorten_from="right")
    if faded:
        label.opacity = 0.5
    return label


class DashTab(MDBoxLayout):
    def __init__(self, ctx: "MECDContext", **kwargs) -> None:
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), **kwargs)
        self.ctx = ctx
        self._shown = None
        self.summary = MDLabel(text="", markup=True, size_hint_y=None, height=dp(30))
        self.add_widget(self.summary)
        self.grid = GridLayout(cols=len(HEADERS), size_hint=(None, None), row_default_height=dp(28),
                               row_force_default=True, spacing=(dp(6), 0))
        self.grid.bind(minimum_height=self.grid.setter("height"),
                       minimum_width=self.grid.setter("width"))
        scroll = MDScrollView(do_scroll_x=True)
        scroll.add_widget(self.grid)
        self.add_widget(scroll)
        self.refresh()
        Clock.schedule_interval(lambda _dt: self.refresh(), 1)

    def _state(self):
        c = self.ctx
        if c.slot_data is None:
            return None
        checked = set(c.checked_locations) | set(c.sent)
        return (tuple(sorted(c.have().items())), frozenset(checked), frozenset(c.missing_locations),
                c.slot_data.get("stars_required", 0))

    def refresh(self) -> None:
        state = self._state()
        if state == self._shown:
            return
        self._shown = state
        self.grid.clear_widgets()
        if state is None:
            self.summary.text = "Connect to your slot to see your dashes."
            return
        have, checked, missing, need = state
        from collections import Counter
        rows = dash_board(Counter(dict(have)), checked, missing)
        unlocked = [r for r in rows if r.unlocked]
        locked = [r for r in rows if not r.unlocked]
        self.summary.text = (f"[b]Stars: {stars_checked(checked)} / {need} needed[/b]    "
                             f"Dashes unlocked: {len(unlocked)} / {len(rows)}    "
                             f"Fully done: {sum(r.done for r in unlocked)}")
        for h, w in zip(HEADERS, WIDTHS):
            self.grid.add_widget(_cell(h, bold=True, width=w))
        for r in unlocked + locked:
            finish = "n/a" if r.finished is None else ("done" if r.finished else "to do")
            nxt = "all stars" if r.next_star_cs is None else f"beat {race_time(r.next_star_cs)}"
            if r.star_checks == 0:
                nxt = "-"
            cells = (r.dash, r.district, "unlocked" if r.unlocked else "locked", finish,
                     f"{r.stars} / {r.star_checks}", nxt)
            for text, w in zip(cells, WIDTHS):
                self.grid.add_widget(_cell(text, bold=r.unlocked and r.done and text == r.dash,
                                           faded=not r.unlocked, width=w))
