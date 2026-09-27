# 3DE4.script.name: Save As...
# 3DE4.script.gui: Main Window::5and8
# 3DE4.script.comment: Save to a path you pick, named the pipeline way.
#
# One entry of the Flow menu. 3DE builds its menus from these headers at
# startup, so the menu is these files -- see flow_dcc/adapters/tde4.py.

import flow_dcc

adapter = flow_dcc.adapter("tde4")
adapter.action_save_as()
