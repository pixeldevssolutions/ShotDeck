# 3DE4.script.name: Open Work Folder
# 3DE4.script.gui: Main Window::5and8
# 3DE4.script.comment: Open the task's work folder in a file manager.
#
# One entry of the Flow menu. 3DE builds its menus from these headers at
# startup, so the menu is these files -- see flow_dcc/adapters/tde4.py.

import flow_dcc

adapter = flow_dcc.adapter("tde4")
adapter.action_open_work_folder()
