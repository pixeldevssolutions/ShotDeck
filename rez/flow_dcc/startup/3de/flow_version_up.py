# 3DE4.script.name: Version Up
# 3DE4.script.gui: Main Window::5and8
# 3DE4.script.comment: Save the next version in the task's work folder.
#
# One entry of the Flow menu. 3DE builds its menus from these headers at
# startup, so the menu is these files -- see flow_dcc/adapters/tde4.py.

import flow_dcc

adapter = flow_dcc.adapter("tde4")
adapter.action_version_up()
