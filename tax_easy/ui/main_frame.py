"""Top-level window: year/status selectors, input form, results, and explanation."""

from __future__ import annotations

import datetime

import wx

from tax_easy.engine.calculator import compute
from tax_easy.rules.provider import RulesUnavailable, available_years, get_rules
from tax_easy.rules.schema import MFJ, SINGLE, TaxYearRules
from tax_easy.storage import persistence
from tax_easy.ui.explanation_view import ExplanationView
from tax_easy.ui.input_panel import EVT_INPUT_CHANGED_BINDER, InputPanel
from tax_easy.ui.results_panel import ResultsPanel

RECOMPUTE_DELAY_MS = 300


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="TaxEasy", size=(1100, 750))

        self.current_rules: TaxYearRules | None = None
        # The year/status a loaded TaxpayerInput actually belongs to --
        # distinct from reading self.year_choice/status_choice live, since
        # wx fires EVT_CHOICE/EVT_COMBOBOX *after* the dropdown's own
        # selection has already changed. Reading the dropdowns fresh inside
        # a pending debounced save (armed by an edit made under the OLD
        # status) would silently save that edit under the NEW status
        # instead once the switch happens. These track what's actually
        # loaded so a save always targets the right file.
        self._active_year: int | None = None
        self._active_status: str | None = None
        self._recompute_timer = wx.CallLater(RECOMPUTE_DELAY_MS, self._recompute)
        self._recompute_timer.Stop()

        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)

        top_bar = wx.Panel(panel, style=wx.BORDER_THEME)
        top_bar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_bar_sizer.Add(wx.StaticText(top_bar, label="Filing year"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        # Only bundled/cached years are selectable -- there is no fetch or
        # manual-entry fallback for other years (see rules/provider.py).
        ready_years = available_years()
        newest_year = max(ready_years) if ready_years else datetime.date.today().year

        # Reopen to whatever year/status was showing last session, rather
        # than always defaulting to the newest year and Single -- falls
        # back to the newest year if there's no saved selection yet, or if
        # the saved year is no longer available.
        last_selection = persistence.load_last_selection()
        if last_selection is not None and last_selection[0] in ready_years:
            default_year, default_status = last_selection
        else:
            default_year, default_status = newest_year, SINGLE

        self.year_choice = wx.ComboBox(
            top_bar, choices=[str(y) for y in ready_years], value=str(default_year),
            style=wx.CB_DROPDOWN | wx.CB_READONLY, size=(90, -1),
        )
        top_bar_sizer.Add(self.year_choice, 0, wx.RIGHT, 28)

        top_bar_sizer.Add(wx.StaticText(top_bar, label="Filing status"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.status_choice = wx.Choice(top_bar, choices=["Single", "Married Filing Jointly"])
        self.status_choice.SetSelection(0 if default_status == SINGLE else 1)
        top_bar_sizer.Add(self.status_choice, 0)

        # wrap in an outer sizer so the bar gets vertical padding beyond
        # what the controls themselves need
        top_bar_outer = wx.BoxSizer(wx.VERTICAL)
        top_bar_outer.Add(top_bar_sizer, 0, wx.ALL, 14)
        top_bar.SetSizer(top_bar_outer)

        outer.Add(top_bar, 0, wx.EXPAND | wx.ALL, 12)

        splitter = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE)
        self.input_panel = InputPanel(splitter)

        right_notebook = wx.Notebook(splitter)
        self.results_panel = ResultsPanel(right_notebook)
        self.explanation_view = ExplanationView(right_notebook)
        right_notebook.AddPage(self.results_panel, "Summary")
        right_notebook.AddPage(self.explanation_view, "Calculation Detail")

        splitter.SplitVertically(self.input_panel, right_notebook, sashPosition=520)
        splitter.SetMinimumPaneSize(320)
        outer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(outer)

        self.year_choice.Bind(wx.EVT_COMBOBOX, self._on_year_or_status_changed)
        self.year_choice.Bind(wx.EVT_TEXT_ENTER, self._on_year_or_status_changed)
        self.status_choice.Bind(wx.EVT_CHOICE, self._on_year_or_status_changed)
        self.input_panel.Bind(EVT_INPUT_CHANGED_BINDER, self._on_input_changed)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self.Centre()
        wx.CallAfter(self._load_current_year)

    def _filing_status(self) -> str:
        return SINGLE if self.status_choice.GetSelection() == 0 else MFJ

    def _year(self) -> int:
        try:
            return int(self.year_choice.GetValue())
        except ValueError:
            return datetime.date.today().year

    def _load_current_year(self):
        # Flush any pending debounced save FIRST, against the year/status
        # that's still active (i.e. what the form's current contents
        # actually belong to) -- not the dropdowns, which may already show
        # the new selection by the time this runs (see _active_year comment
        # in __init__).
        if self._recompute_timer.IsRunning():
            self._recompute_timer.Stop()
        self._save_current_input()

        year = self._year()
        status = self._filing_status()

        self.current_rules = self._resolve_rules(year)
        if self.current_rules is None:
            self._active_year = None
            self._active_status = None
            self.results_panel.clear()
            self.explanation_view.clear()
            return

        saved_input = persistence.load(year, status)
        self.input_panel.load(saved_input)
        self._active_year = year
        self._active_status = status
        persistence.save_last_selection(year, status)
        self._recompute()

    def _resolve_rules(self, year: int) -> TaxYearRules | None:
        try:
            return get_rules(year)
        except RulesUnavailable as exc:
            wx.MessageBox(str(exc), "Rules unavailable", wx.OK | wx.ICON_WARNING)
            return None

    def _on_year_or_status_changed(self, evt):
        self._load_current_year()

    def _on_close(self, evt):
        # Always flush on close, unconditionally -- don't gate this on
        # self._recompute_timer.IsRunning(). An edit fires InputChangedEvent
        # via wx.PostEvent (queued, not delivered synchronously), so the
        # timer that IsRunning() checks may not be armed yet even though the
        # in-memory widgets already hold the new value (e.g. closing right
        # after add_row()/a keystroke, before the event loop has dispatched
        # the queued event and _on_input_changed has had a chance to run).
        # Checking IsRunning() would silently skip the save in that window.
        # _save_current_input() itself is cheap and already a no-op if
        # nothing has been loaded yet, so it's safe to call unconditionally.
        self._recompute_timer.Stop()
        self._save_current_input()
        evt.Skip()

    def _on_input_changed(self, evt):
        self._recompute_timer.Stop()
        self._recompute_timer = wx.CallLater(RECOMPUTE_DELAY_MS, self._recompute_and_save)

    def _recompute_and_save(self):
        self._save_current_input()
        self._recompute()

    def _save_current_input(self):
        if self.current_rules is None or self._active_year is None or self._active_status is None:
            return
        input_ = self.input_panel.build_input(self._active_year, self._active_status)
        persistence.save(input_)

    def _recompute(self):
        if self.current_rules is None:
            return
        year = self._year()
        status = self._filing_status()
        input_ = self.input_panel.build_input(year, status)
        result = compute(input_, self.current_rules)
        self.results_panel.show_result(result)
        self.explanation_view.show_result(result, self.current_rules, status)
