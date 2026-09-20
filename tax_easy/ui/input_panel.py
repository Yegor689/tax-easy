"""Form for entering incomes, stock sales, deductions, and payments."""

from __future__ import annotations

import wx
import wx.lib.scrolledpanel as scrolled

from tax_easy.engine.models import (
    Deductions,
    IncomeItem,
    Payments,
    StockSale,
    TaxpayerInput,
)

EVT_INPUT_CHANGED = wx.NewEventType()
EVT_INPUT_CHANGED_BINDER = wx.PyEventBinder(EVT_INPUT_CHANGED, 1)

SECTION_GAP = 16
FIELD_HEIGHT = 30
MONEY_FIELD_WIDTH = 180


def _relayout_ancestors(widget: wx.Window) -> None:
    """Re-layout every ancestor of `widget` up to the enclosing
    ScrolledPanel (InputPanel), then tell that ScrolledPanel to recompute
    its scrollable area.

    Adding/removing a row inside a nested control (e.g. a RepeatingMoneyList
    row) changes that control's best-size, but Layout() alone doesn't
    recompute each ancestor's own min-size in turn -- a Card's reported
    best-size can go stale even though its direct child re-laid-out
    correctly. Walking up and refreshing each Card's min-size fixes that
    part, but ScrolledPanel has its own separate problem: it caches its
    "virtual size" (the scrollable content height) once during
    SetupScrolling() and never recomputes it on a later plain Layout()
    call -- only FitInside() does that. Without it, content that grows
    after construction (or even the last card built during __init__,
    since SetupScrolling() runs once at the very end) can be silently
    clipped even though every individual widget reports the correct size.
    """
    node = widget.GetParent()
    scrolled_panel = None
    while node is not None:
        node.Layout()
        if isinstance(node, Card):
            node.SetMinSize(node.GetSizer().CalcMin())
        if isinstance(node, scrolled.ScrolledPanel):
            scrolled_panel = node
            break
        node = node.GetParent()
    if scrolled_panel is not None:
        scrolled_panel.FitInside()


class InputChangedEvent(wx.PyCommandEvent):
    def __init__(self, source):
        super().__init__(EVT_INPUT_CHANGED, source.GetId())
        self.SetEventObject(source)


def _filter_numeric_keypress(evt: wx.KeyEvent):
    """Reject any keystroke that isn't a digit, a single decimal point, or
    a control/navigation/editing key -- so the field can't hold non-numeric
    text in the first place instead of silently parsing it to 0 later.
    Allows Cmd/Ctrl shortcuts (copy/paste/select-all/undo) through
    unfiltered so paste is still validated by EVT_TEXT below.
    """
    keycode = evt.GetKeyCode()
    ctrl = evt.GetEventObject()

    if evt.CmdDown() or evt.ControlDown() or evt.AltDown():
        evt.Skip()
        return

    if keycode in (
        wx.WXK_BACK, wx.WXK_DELETE, wx.WXK_TAB, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER,
        wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME, wx.WXK_END,
        wx.WXK_ESCAPE,
    ):
        evt.Skip()
        return

    char = chr(keycode) if 0 <= keycode < 256 else ""

    if char == "." and "." not in ctrl.GetValue():
        evt.Skip()
        return

    if char.isdigit():
        evt.Skip()
        return

    # anything else (letters, extra decimal points, symbols) is swallowed


def _sanitize_pasted_text(evt: wx.CommandEvent):
    """EVT_TEXT handler that strips non-numeric characters after a paste
    or programmatic SetValue slips one through the keypress filter above."""
    ctrl = evt.GetEventObject()
    text = ctrl.GetValue()
    cleaned = []
    seen_dot = False
    for ch in text:
        if ch.isdigit():
            cleaned.append(ch)
        elif ch == "." and not seen_dot:
            cleaned.append(ch)
            seen_dot = True
    cleaned_text = "".join(cleaned)
    if cleaned_text != text:
        insertion_point = ctrl.GetInsertionPoint()
        ctrl.ChangeValue(cleaned_text)
        ctrl.SetInsertionPoint(min(insertion_point, len(cleaned_text)))
    evt.Skip()


def _money_ctrl(parent, value: float = 0.0, width: int = MONEY_FIELD_WIDTH) -> wx.TextCtrl:
    ctrl = wx.TextCtrl(parent, value=_fmt(value), size=(width, FIELD_HEIGHT), style=wx.TE_RIGHT)
    ctrl.Bind(wx.EVT_CHAR, _filter_numeric_keypress)
    ctrl.Bind(wx.EVT_TEXT, _sanitize_pasted_text)
    return ctrl


def _fmt(value: float) -> str:
    """Blank means zero, same convention as most tax/finance software --
    a fresh or all-zero form stays clean instead of showing a wall of 0s.
    This is purely cosmetic: saving and reloading a blank field round-trips
    as 0.0 exactly the same as typing "0" would."""
    return "" if value == 0 else f"{value:g}"


def _parse(text: str) -> float:
    text = text.strip().replace(",", "").replace("$", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _money_row(parent, sizer: wx.Sizer, ctrl: wx.TextCtrl):
    """Wraps a money field with a '$' prefix, added to `sizer` as one unit."""
    row = wx.BoxSizer(wx.HORIZONTAL)
    dollar = wx.StaticText(parent, label="$")
    dollar.SetForegroundColour(wx.Colour(140, 140, 140))
    row.Add(dollar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
    row.Add(ctrl, 0)
    sizer.Add(row, 0)


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


class Card(wx.Panel):
    """A visually grouped section: title + shaded, bordered body.

    Uses an explicit background fill and a hand-drawn border instead of
    wx.BORDER_THEME, whose native rendering is barely visible against a
    dark background on some platforms.
    """

    def __init__(self, parent, title: str):
        super().__init__(parent)
        fill, border = _card_colours(parent)
        self.SetBackgroundColour(fill)
        self._border_colour = border
        self.Bind(wx.EVT_PAINT, self._on_paint)

        outer = wx.BoxSizer(wx.VERTICAL)

        title_label = wx.StaticText(self, label=title)
        font = title_label.GetFont()
        font.SetPointSize(font.GetPointSize() + 1)
        font.MakeBold()
        title_label.SetFont(font)
        outer.Add(title_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, 14)

        self.body = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.body, 0, wx.EXPAND | wx.ALL, 14)

        self.SetSizer(outer)

    def add(self, window_or_sizer, proportion=0, flag=0, border=0):
        self.body.Add(window_or_sizer, proportion, flag, border)
        # Without this, the card's own best-size can go stale after content
        # is added post-construction -- its allocated height in the parent
        # sizer then falls short of what its content actually needs, and
        # the last-added row gets visually clipped (see the "Estimated tax
        # payments made" row clipping bug this was written to fix).
        self.Layout()
        self.SetMinSize(self.GetSizer().CalcMin())

    def _on_paint(self, evt):
        dc = wx.PaintDC(self)
        dc.SetPen(wx.Pen(self._border_colour, 1))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        w, h = self.GetSize()
        dc.DrawRectangle(0, 0, w, h)


class _RepeatingList(wx.Panel):
    """Shared plumbing for an add/remove list of rows: row container sizing,
    the relayout dance ScrolledPanel needs when rows come and go (see
    _relayout_ancestors), and the changed-event bridge to the parent form.

    Subclasses build each row's own widgets via _build_row() and convert
    rows to/from their own item type via items()/set_items().
    """

    def __init__(self, parent, add_label: str, on_change):
        super().__init__(parent)
        self.SetBackgroundColour(parent.GetBackgroundColour())
        self._on_change = on_change
        self._rows: list[tuple] = []

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.rows_sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.rows_sizer, 0, wx.EXPAND)

        add_btn = wx.Button(self, label=add_label)
        add_btn.Bind(wx.EVT_BUTTON, lambda evt: self.add_row())
        self.sizer.Add(add_btn, 0, wx.TOP, 6)
        self.SetSizer(self.sizer)

    def _build_row(self, row: wx.Panel, *args) -> tuple:
        """Build one row's widgets onto `row` and return the tuple to track
        in self._rows (last element must be `row` itself). Must bind each
        editable widget to self._changed and, for the remove button, to
        self._remove(row)."""
        raise NotImplementedError

    def add_row(self, *args) -> None:
        row = wx.Panel(self)
        row.SetBackgroundColour(self.GetBackgroundColour())
        entry = self._build_row(row, *args)

        self.rows_sizer.Add(row, 0, wx.EXPAND | wx.BOTTOM, 6)
        self._rows.append(entry)

        self.Layout()
        _relayout_ancestors(self)
        self._changed()

    def _remove(self, row):
        self._rows = [r for r in self._rows if r[-1] is not row]
        row.Destroy()
        self.Layout()
        _relayout_ancestors(self)
        self._changed()

    def _changed(self, evt=None):
        if evt is not None:
            evt.Skip()
        self._on_change()

    def _clear_rows(self):
        for entry in self._rows:
            entry[-1].Destroy()
        self._rows = []


class RepeatingMoneyList(_RepeatingList):
    """A label + amount row list with add/remove, e.g. multiple income sources."""

    def __init__(self, parent, add_label: str, default_label: str, on_change):
        self._default_label = default_label
        super().__init__(parent, add_label, on_change)

    def _build_row(self, row, label: str = "", amount: float = 0.0):
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_ctrl = wx.TextCtrl(row, value=label or self._default_label, size=(200, FIELD_HEIGHT))
        dollar = wx.StaticText(row, label="$")
        dollar.SetForegroundColour(wx.Colour(140, 140, 140))
        amount_ctrl = _money_ctrl(row, amount)
        remove_btn = wx.Button(row, label="Remove", size=(72, FIELD_HEIGHT))

        row_sizer.Add(label_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row_sizer.Add(dollar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        row_sizer.Add(amount_ctrl, 0, wx.RIGHT, 8)
        row_sizer.Add(remove_btn, 0)
        row.SetSizer(row_sizer)

        label_ctrl.Bind(wx.EVT_TEXT, self._changed)
        amount_ctrl.Bind(wx.EVT_TEXT, self._changed)
        remove_btn.Bind(wx.EVT_BUTTON, lambda evt: self._remove(row))

        return (label_ctrl, amount_ctrl, row)

    def items(self) -> list[IncomeItem]:
        return [
            IncomeItem(label=label.GetValue() or self._default_label, amount=_parse(amount.GetValue()))
            for label, amount, _row in self._rows
        ]

    def set_items(self, items: list[IncomeItem]):
        self._clear_rows()
        for item in items:
            self.add_row(item.label, item.amount)
        if not items:
            self.add_row()


class StockSaleList(_RepeatingList):
    """Like RepeatingMoneyList but with a long-term/short-term toggle per row."""

    def __init__(self, parent, on_change):
        super().__init__(parent, "+ Add stock sale", on_change)

    def _build_row(self, row, label: str = "", gain: float = 0.0, long_term: bool = True):
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_ctrl = wx.TextCtrl(row, value=label or "Stock sale", size=(160, FIELD_HEIGHT))
        dollar = wx.StaticText(row, label="$")
        dollar.SetForegroundColour(wx.Colour(140, 140, 140))
        gain_ctrl = _money_ctrl(row, gain, width=140)
        lt_check = wx.CheckBox(row, label="Long-term")
        lt_check.SetValue(long_term)
        remove_btn = wx.Button(row, label="Remove", size=(72, FIELD_HEIGHT))

        row_sizer.Add(label_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row_sizer.Add(dollar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        row_sizer.Add(gain_ctrl, 0, wx.RIGHT, 10)
        row_sizer.Add(lt_check, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        row_sizer.Add(remove_btn, 0)
        row.SetSizer(row_sizer)

        label_ctrl.Bind(wx.EVT_TEXT, self._changed)
        gain_ctrl.Bind(wx.EVT_TEXT, self._changed)
        lt_check.Bind(wx.EVT_CHECKBOX, self._changed)
        remove_btn.Bind(wx.EVT_BUTTON, lambda evt: self._remove(row))

        return (label_ctrl, gain_ctrl, lt_check, row)

    def items(self) -> list[StockSale]:
        return [
            StockSale(label=label.GetValue() or "Stock sale", gain=_parse(gain.GetValue()), long_term=lt.GetValue())
            for label, gain, lt, _row in self._rows
        ]

    def set_items(self, items: list[StockSale]):
        self._clear_rows()
        for item in items:
            self.add_row(item.label, item.gain, item.long_term)


class InputPanel(scrolled.ScrolledPanel):
    def __init__(self, parent):
        super().__init__(parent)
        self._suspend_events = False
        # Inherit the real system/theme background instead of a transparent
        # placeholder -- Card reads this colour to compute its own fill and
        # border, so it needs to reflect what's actually on screen.
        self.SetBackgroundColour(parent.GetBackgroundColour())

        outer = wx.BoxSizer(wx.VERTICAL)

        income_card = Card(self, "Income")
        income_card.add(
            self._card_hint(income_card, "Wages, self-employment income, interest, or any other taxable income. Add one row per source."),
            0, wx.EXPAND | wx.BOTTOM, 6,
        )
        self.incomes = RepeatingMoneyList(income_card, "+ Add income", "Income", self._fire_changed)
        income_card.add(self.incomes, 0, wx.EXPAND)
        outer.Add(income_card, 0, wx.EXPAND | wx.ALL, 10)

        pay_card = Card(self, "Payments already made")
        pay_card.add(
            self._card_hint(pay_card, "Federal tax already paid toward this year's bill, so the estimate reflects what you still owe."),
            0, wx.EXPAND | wx.BOTTOM, 6,
        )
        withholding_label = wx.StaticText(pay_card, label="Withholding")
        withholding_font = withholding_label.GetFont()
        withholding_font.MakeItalic()
        withholding_label.SetFont(withholding_font)
        pay_card.add(withholding_label, 0, wx.BOTTOM, 4)
        pay_card.add(
            self._card_hint(
                pay_card,
                "Federal income tax already withheld from your paychecks this year "
                "(see your latest pay stub or W-2). Add one row per job/source.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 4,
        )
        self.withholding = RepeatingMoneyList(pay_card, "+ Add withholding", "Withholding", self._fire_changed)
        pay_card.add(self.withholding, 0, wx.EXPAND)

        pay_card.add((0, 12))
        estimated_label = wx.StaticText(pay_card, label="Estimated tax payments")
        estimated_font = estimated_label.GetFont()
        estimated_font.MakeItalic()
        estimated_label.SetFont(estimated_font)
        pay_card.add(estimated_label, 0, wx.BOTTOM, 4)
        pay_card.add(
            self._card_hint(
                pay_card,
                "Quarterly estimated tax payments sent directly to the IRS (Form "
                "1040-ES), e.g. for self-employment or investment income. Add one "
                "row per payment.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 4,
        )
        self.estimated_payments = RepeatingMoneyList(
            pay_card, "+ Add estimated payment", "Estimated payment", self._fire_changed
        )
        pay_card.add(self.estimated_payments, 0, wx.EXPAND)

        outer.Add(pay_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        stock_card = Card(self, "Stock sales")
        stock_card.add(
            self._card_hint(
                stock_card,
                "Gain (sale price minus cost basis) for each sale. Check “Long-term” "
                "if you held the position over a year — it's taxed at lower capital "
                "gains rates instead of as ordinary income.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 6,
        )
        self.stock_sales = StockSaleList(stock_card, self._fire_changed)
        stock_card.add(self.stock_sales, 0, wx.EXPAND)
        outer.Add(stock_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        ded_card = Card(self, "Deductions")
        ded_card.add(
            self._card_hint(
                ded_card,
                "These are used only if they add up to more than the standard deduction "
                "for your filing status — the calculator picks whichever is larger.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 6,
        )
        self.mortgage_interest = _money_ctrl(ded_card)
        self.other_salt = _money_ctrl(ded_card)
        for ctrl in (self.mortgage_interest, self.other_salt):
            ctrl.Bind(wx.EVT_TEXT, self._fire_changed)

        ded_card.add(
            self._field_with_caption(
                ded_card, "Mortgage interest paid", self.mortgage_interest,
                "Interest paid on a home mortgage this year, per Form 1098.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 10,
        )

        property_tax_label = wx.StaticText(ded_card, label="Property tax paid")
        property_tax_font = property_tax_label.GetFont()
        property_tax_font.MakeItalic()
        property_tax_label.SetFont(property_tax_font)
        ded_card.add(property_tax_label, 0, wx.BOTTOM, 4)
        ded_card.add(
            self._card_hint(
                ded_card,
                "Real estate property tax paid this year. Add one row per property.",
            ),
            0, wx.EXPAND | wx.BOTTOM, 4,
        )
        self.property_tax = RepeatingMoneyList(ded_card, "+ Add property", "Property tax", self._fire_changed)
        ded_card.add(self.property_tax, 0, wx.EXPAND | wx.BOTTOM, 10)

        ded_card.add(
            self._field_with_caption(
                ded_card, "Other state/local tax (SALT)", self.other_salt,
                "State/local income or sales tax paid (not property tax, entered above). "
                "Combined with property tax, this is capped by the IRS's SALT limit "
                "regardless of what you enter here.",
            ),
            0, wx.EXPAND,
        )

        ded_card.add((0, 10))
        other_label = wx.StaticText(ded_card, label="Other deductible categories")
        other_font = other_label.GetFont()
        other_font.MakeItalic()
        other_label.SetFont(other_font)
        ded_card.add(other_label, 0, wx.BOTTOM, 4)
        ded_card.add(
            self._card_hint(ded_card, "E.g. charitable donations, medical expenses above the deductible threshold."),
            0, wx.EXPAND | wx.BOTTOM, 4,
        )
        self.other_deductible = RepeatingMoneyList(ded_card, "+ Add deduction", "Deduction", self._fire_changed)
        ded_card.add(self.other_deductible, 0, wx.EXPAND)

        outer.Add(ded_card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(outer)
        self.SetupScrolling(scroll_x=False)
        # SetupScrolling() computes the scrollable virtual size once, from
        # the sizer as it stood at that moment -- a plain Layout() call
        # doesn't ask it to recompute that later. FitInside() is the call
        # that actually does, so it must run last (see _relayout_ancestors
        # for the same fix applied when rows are added/removed afterward).
        self.FitInside()

    # Wrap width chosen to fit within the splitter's minimum pane size
    # (see MainFrame.SetMinimumPaneSize) minus the Card's own padding
    # (14px each side) and InputPanel's outer margin (10px each side):
    # 320 - 28 - 20 = 272, rounded down for a small safety margin.
    # A wrap width tied to the panel's *current* size doesn't work here:
    # InputPanel is a ScrolledPanel with horizontal scrolling disabled, so
    # its sizer computes its minimum width from its widest unconstrained
    # child rather than the viewport -- the panel can be visually
    # shrunk by the splitter well below that computed minimum, and content
    # then clips instead of rewrapping. Wrapping to the guaranteed-minimum
    # width up front avoids relying on a resize signal that isn't
    # meaningful in a no-horizontal-scroll ScrolledPanel.
    HINT_WRAP_WIDTH = 260

    def _card_hint(self, parent: wx.Window, text: str) -> wx.Sizer:
        hint = wx.StaticText(parent, label=text)
        hint.SetForegroundColour(wx.Colour(150, 150, 150))
        font = hint.GetFont()
        font.SetPointSize(font.GetPointSize() - 1)
        hint.SetFont(font)
        hint.Wrap(self.HINT_WRAP_WIDTH)

        # extra top padding so hint text doesn't crowd the section title above it
        padded = wx.BoxSizer(wx.VERTICAL)
        padded.Add(hint, 0, wx.TOP, 6)
        return padded

    def _field_with_caption(
        self, parent: wx.Window, label: str, ctrl: wx.TextCtrl, caption: str
    ) -> wx.Sizer:
        """A label + '$' + money field row, with a small caption line
        underneath explaining what belongs in it. Used instead of a hover
        tooltip for fields people are likely to be unsure about -- a
        tooltip requires knowing to hover and wait, so it's easy to miss
        entirely at a glance."""
        block = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        dollar = wx.StaticText(parent, label="$")
        dollar.SetForegroundColour(wx.Colour(140, 140, 140))
        row.Add(dollar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        row.Add(ctrl, 0)
        block.Add(row, 0)

        caption_text = wx.StaticText(parent, label=caption)
        caption_text.SetForegroundColour(wx.Colour(150, 150, 150))
        caption_font = caption_text.GetFont()
        caption_font.SetPointSize(caption_font.GetPointSize() - 1)
        caption_text.SetFont(caption_font)
        caption_text.Wrap(self.HINT_WRAP_WIDTH)
        block.Add(caption_text, 0, wx.TOP, 3)

        return block

    def _fire_changed(self, evt=None):
        # Must Skip() so other handlers bound to the same control (e.g. the
        # numeric-input sanitizer in _money_ctrl) still run -- wx searches
        # bound handlers most-recently-bound first and stops at the first
        # one that doesn't call Skip().
        if evt is not None:
            evt.Skip()
        if self._suspend_events:
            return
        wx.PostEvent(self, InputChangedEvent(self))

    def get_deductions_and_payments(self) -> tuple[Deductions, Payments]:
        deductions = Deductions(
            mortgage_interest=_parse(self.mortgage_interest.GetValue()),
            property_tax=self.property_tax.items(),
            other_salt=_parse(self.other_salt.GetValue()),
            other_deductible={i.label: i.amount for i in self.other_deductible.items()},
        )
        payments = Payments(
            withholding=self.withholding.items(),
            estimated_payments=self.estimated_payments.items(),
        )
        return deductions, payments

    def load(self, input_: TaxpayerInput):
        self._suspend_events = True
        try:
            self.incomes.set_items(input_.incomes)
            self.stock_sales.set_items(input_.stock_sales)
            self.mortgage_interest.SetValue(_fmt(input_.deductions.mortgage_interest))
            self.property_tax.set_items(input_.deductions.property_tax)
            self.other_salt.SetValue(_fmt(input_.deductions.other_salt))
            self.other_deductible.set_items(
                [IncomeItem(label=k, amount=v) for k, v in input_.deductions.other_deductible.items()]
            )
            self.withholding.set_items(input_.payments.withholding)
            self.estimated_payments.set_items(input_.payments.estimated_payments)
        finally:
            self._suspend_events = False
        self.Layout()

    def build_input(self, year: int, filing_status: str) -> TaxpayerInput:
        deductions, payments = self.get_deductions_and_payments()
        return TaxpayerInput(
            year=year,
            filing_status=filing_status,
            incomes=self.incomes.items(),
            stock_sales=self.stock_sales.items(),
            deductions=deductions,
            payments=payments,
        )
