"""Host-specific code. One module per DCC, imported only inside that DCC.

Every adapter offers the same three things to the shared code above it:

    install()            build the ShotDeck menu
    save_scene(path)     save the open scene to path
    message(text)        put text where this host shows messages

The menu itself is described once, in ACTIONS, so the hosts differ only in how
they build menus rather than in what is on them.
"""

# (label, callable name on the adapter module)
ACTIONS = [
    ("Save Next Version", "action_save_next_version"),
    ("Open Work Folder", "action_open_work_folder"),
    (None, None),                     # separator
    ("Show ShotDeck Context", "action_show_context"),
]

MENU_NAME = "ShotDeck"
