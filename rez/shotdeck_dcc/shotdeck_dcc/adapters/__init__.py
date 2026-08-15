"""Host-specific code. One module per DCC, imported only inside that DCC.

Every adapter offers the same three things to the shared code above it:

    install()            build the ShotDeck menu
    save_scene(path)     save the open scene to path
    message(text)        put text where this host shows messages

The menu itself is described once, in ACTIONS, so the hosts differ only in how
they build menus rather than in what is on them.
"""

# (label, callable name on the adapter module). None is a separator.
#
# Grouped by what the artist is doing: working on the scene, handing it off,
# then finding things. Publish sits alone between the two so it is hard to hit
# by accident.
ACTIONS = [
    ("Save", "action_save"),
    ("Save As...", "action_save_as"),
    ("Version Up", "action_version_up"),
    (None, None),
    ("Publish...", "action_publish"),
    (None, None),
    ("Open Work Folder", "action_open_work_folder"),
    ("Open Publish Folder", "action_open_publish_folder"),
    ("Context", "action_context"),
]

MENU_NAME = "ShotDeck"
