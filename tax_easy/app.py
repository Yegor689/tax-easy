"""wx.App bootstrap."""

from __future__ import annotations

import wx

from tax_easy.ui.main_frame import MainFrame


class TaxEasyApp(wx.App):
    def OnInit(self):
        frame = MainFrame()
        frame.Show()
        return True
