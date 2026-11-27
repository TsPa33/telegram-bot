"""Windows smoke test for the workflow at the smallest supported window size."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest import TestCase, skipUnless
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader


@skipUnless(os.name == 'nt', 'GUI geometry acceptance on native Windows runner')
class GUIWorkflowTest(TestCase):
    def test_actions_are_visible_without_scrolling(self):
        from unittest.mock import patch
        source = Path(__file__).with_name('carpot_local_aleto.pyw')
        loader = SourceFileLoader('local_aleto_gui_test', str(source))
        app = module_from_spec(spec_from_loader(loader.name, loader))
        loader.exec_module(app)
        with TemporaryDirectory() as temporary:
            with patch.object(app, 'DATA_DIR', Path(temporary)), patch.object(
                    app, 'DB_PATH', Path(temporary) / 'local_aleto.sqlite3'):
                root = tk.Tk()
                try:
                    root.geometry('980x660+0+0')
                    gui = app.MainWindow(root)
                    root.update()
                    self.assertFalse(gui.candidate_panel.winfo_ismapped())
                    for widget in (gui.start_btn, gui.export_btn, gui.upload_btn,
                                   gui.discover_btn, gui.vehicle_box):
                        self.assertTrue(widget.winfo_ismapped(), repr(widget))
                        self.assertGreater(widget.winfo_height(), 15)
                        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                             root.winfo_rooty() + root.winfo_height())
                    gui.events.put(('candidates',
                                    ['https://aleto.ua/car/polestar-2-2021-/']))
                    gui._poll()
                    root.update()
                    self.assertTrue(gui.candidate_panel.winfo_ismapped())
                    self.assertEqual(gui.catalogue.get(), 'https://aleto.ua/car/polestar-2-2021-/')
                    gui.query.set('підшипник')
                    gui._reset_filters()
                    self.assertEqual(gui.query.get(), '')
                finally:
                    root.destroy()
