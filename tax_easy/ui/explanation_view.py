"""Embedded WebView rendering the step-by-step calculation trace as HTML."""

from __future__ import annotations

import wx
import wx.html2

from tax_easy.engine.html_report import render
from tax_easy.engine.models import CalculationResult
from tax_easy.rules.schema import TaxYearRules


class ExplanationView(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.webview = wx.html2.WebView.New(self)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def show_result(self, result: CalculationResult, rules: TaxYearRules, filing_status: str):
        html = render(result, rules, filing_status)
        self.webview.SetPage(html, "")

    def clear(self):
        self.webview.SetPage("<html><body></body></html>", "")
