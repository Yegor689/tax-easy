"""Live-updating summary of the calculation result."""

from __future__ import annotations

import wx

from tax_easy.engine.models import CalculationResult

OWED_COLOUR = wx.Colour(198, 40, 40)
REFUND_COLOUR = wx.Colour(46, 125, 50)


def _card_colours(window: wx.Window) -> tuple[wx.Colour, wx.Colour]:
    """Card fill/border colours, adapted to light vs dark mode by nudging
    away from the window's own background rather than using fixed values."""
    base = window.GetBackgroundColour()
    is_dark = base.GetLuminance() < 0.5
    if is_dark:
        fill = wx.Colour(
            min(255, base.Red() + 14), min(255, base.Green() + 14), min(255, base.Blue() + 14)
        )
        border = wx.Colour(
            min(255, base.Red() + 46), min(255, base.Green() + 46), min(255, base.Blue() + 46)
        )
    else:
        fill = wx.Colour(
            max(0, base.Red() - 6), max(0, base.Green() - 6), max(0, base.Blue() - 6)
        )
        border = wx.Colour(
            max(0, base.Red() - 32), max(0, base.Green() - 32), max(0, base.Blue() - 32)
        )
    return fill, border


class _BorderedPanel(wx.Panel):
    """A wx.Panel with an explicit fill and hand-drawn border, since native
    wx.BORDER_THEME rendering is barely visible against a dark background
    on some platforms."""

    def __init__(self, parent):
        super().__init__(parent)
        fill, border = _card_colours(parent)
        self.SetBackgroundColour(fill)
        self._border_colour = border
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, evt):
        dc = wx.PaintDC(self)
        dc.SetPen(wx.Pen(self._border_colour, 1))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        w, h = self.GetSize()
        dc.DrawRectangle(0, 0, w, h)


class ResultsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        outer = wx.BoxSizer(wx.VERTICAL)

        self.balance_card = _BorderedPanel(self)
        balance_sizer = wx.BoxSizer(wx.VERTICAL)
        self.balance_kind_label = wx.StaticText(self.balance_card, label="ESTIMATED BALANCE DUE")
        kind_font = self.balance_kind_label.GetFont()
        kind_font.SetPointSize(kind_font.GetPointSize() - 1)
        self.balance_kind_label.SetFont(kind_font)
        self.balance_kind_label.SetForegroundColour(wx.Colour(140, 140, 140))

        self.balance_amount_label = wx.StaticText(self.balance_card, label="—")
        amount_font = self.balance_amount_label.GetFont()
        amount_font.SetPointSize(amount_font.GetPointSize() + 14)
        amount_font.MakeBold()
        self.balance_amount_label.SetFont(amount_font)

        balance_sizer.Add(self.balance_kind_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, 16)
        balance_sizer.Add(self.balance_amount_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.balance_card.SetSizer(balance_sizer)
        outer.Add(self.balance_card, 0, wx.EXPAND | wx.ALL, 12)

        detail_card = _BorderedPanel(self)
        detail_sizer = wx.BoxSizer(wx.VERTICAL)
        detail_title = wx.StaticText(detail_card, label="Breakdown")
        title_font = detail_title.GetFont()
        title_font.MakeBold()
        detail_title.SetFont(title_font)
        detail_sizer.Add(detail_title, 0, wx.TOP | wx.LEFT | wx.RIGHT, 14)

        grid = wx.FlexGridSizer(cols=2, gap=(12, 10))
        grid.AddGrowableCol(0, 1)
        self.total_income = self._value_row(detail_card, grid, "Total income")
        self.deduction_used = self._value_row(detail_card, grid, "Deduction used")
        self.ordinary_taxable = self._value_row(detail_card, grid, "Ordinary taxable income")
        self.ordinary_tax = self._value_row(detail_card, grid, "Tax on ordinary income")
        self.ltcg_tax = self._value_row(detail_card, grid, "Tax on long-term gains")
        self._separator(detail_card, grid)
        self.total_tax = self._value_row(detail_card, grid, "Total federal tax", bold=True)
        self.total_payments = self._value_row(detail_card, grid, "Payments already made")
        detail_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 14)
        detail_card.SetSizer(detail_sizer)

        outer.Add(detail_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        hint = wx.StaticText(
            self,
            label="See the “Calculation Detail” tab for a full step-by-step breakdown of this result.",
        )
        hint.SetForegroundColour(wx.Colour(140, 140, 140))
        outer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        scope_card = _BorderedPanel(self)
        scope_sizer = wx.BoxSizer(wx.VERTICAL)
        scope_title = wx.StaticText(scope_card, label="What this estimate covers")
        scope_font = scope_title.GetFont()
        scope_font.MakeBold()
        scope_title.SetFont(scope_font)
        scope_sizer.Add(scope_title, 0, wx.TOP | wx.LEFT | wx.RIGHT, 14)

        # Wrapped to a fixed width chosen to fit within the splitter's
        # minimum pane size on the input side, matching the right pane's
        # typical width once the window is at a reasonably small size --
        # see the matching constant/comment in InputPanel.HINT_WRAP_WIDTH
        # for why a fixed width is used instead of wrapping to the
        # control's live size.
        scope_text = wx.StaticText(
            scope_card,
            label=(
                "Federal ordinary income tax, standard vs. itemized deductions, and "
                "short/long-term capital gains, for Single and Married Filing Jointly.\n\n"
                "Not included: Alternative Minimum Tax (AMT), Net Investment Income Tax, "
                "self-employment tax, and credits (e.g. Child Tax Credit). If any of "
                "these apply to you, your actual balance will differ from this estimate."
            ),
        )
        scope_text.SetForegroundColour(wx.Colour(150, 150, 150))
        scope_text.Wrap(460)
        scope_sizer.Add(scope_text, 0, wx.ALL, 14)
        scope_card.SetSizer(scope_sizer)
        outer.Add(scope_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        outer.AddStretchSpacer(1)

        self.SetSizer(outer)

    def _value_row(self, parent, grid: wx.FlexGridSizer, label: str, bold: bool = False) -> wx.StaticText:
        label_ctrl = wx.StaticText(parent, label=label)
        value = wx.StaticText(parent, label="—", style=wx.ALIGN_RIGHT)
        if bold:
            for ctrl in (label_ctrl, value):
                font = ctrl.GetFont()
                font.MakeBold()
                ctrl.SetFont(font)
        grid.Add(label_ctrl, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        grid.Add(value, 0, wx.ALIGN_RIGHT)
        return value

    def _separator(self, parent, grid: wx.FlexGridSizer):
        line1 = wx.StaticLine(parent)
        line2 = wx.StaticLine(parent)
        grid.Add(line1, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)
        grid.Add(line2, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)

    def show_result(self, result: CalculationResult):
        if result.balance_due >= 0:
            self.balance_kind_label.SetLabel("ESTIMATED BALANCE DUE")
            self.balance_amount_label.SetLabel(f"${result.balance_due:,.2f}")
            self.balance_amount_label.SetForegroundColour(OWED_COLOUR)
        else:
            self.balance_kind_label.SetLabel("ESTIMATED REFUND")
            self.balance_amount_label.SetLabel(f"${-result.balance_due:,.2f}")
            self.balance_amount_label.SetForegroundColour(REFUND_COLOUR)

        self.total_income.SetLabel(f"${result.total_income:,.2f}")
        self.deduction_used.SetLabel(
            f"${result.deduction_used:,.2f} ({'itemized' if result.used_itemized else 'standard'})"
        )
        self.ordinary_taxable.SetLabel(f"${result.ordinary_taxable_income:,.2f}")
        self.ordinary_tax.SetLabel(f"${result.ordinary_tax:,.2f}")
        self.ltcg_tax.SetLabel(f"${result.ltcg_tax:,.2f}")
        self.total_tax.SetLabel(f"${result.total_tax:,.2f}")
        self.total_payments.SetLabel(f"${result.total_payments:,.2f}")

        self.Layout()

    def clear(self):
        self.balance_kind_label.SetLabel("NO DATA")
        self.balance_amount_label.SetLabel("—")
        self.balance_amount_label.SetForegroundColour(wx.NullColour)
        for ctrl in (
            self.total_income, self.deduction_used, self.ordinary_taxable,
            self.ordinary_tax, self.ltcg_tax, self.total_tax, self.total_payments,
        ):
            ctrl.SetLabel("—")
        self.Layout()
