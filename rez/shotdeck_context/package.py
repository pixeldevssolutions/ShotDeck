name = "shotdeck_context"

version = "1.0.0"

description = \
    "Reads the ShotGrid launch context ShotDeck hands to a DCC, so publish " \
    "tools know which task they are publishing to."

authors = ["pipeline"]

# Pure Python, no compiled extensions -- one variant per platform is enough to
# keep the install layout consistent with the studio's other packages.
variants = [
    ["platform-linux", "arch-x86_64"],
]

build_command = "python {root}/REZ_INSTALLER.py"


def commands():
    env.PYTHONPATH.prepend("{root}/python")

    # Where ShotDeck writes context files. Only set as a default -- ShotDeck
    # itself exports SHOTDECK_CONTEXT_FILE per launch, which is what tools read.
    if "SHOTDECK_CONTEXT_DIR" not in env:
        env.SHOTDECK_CONTEXT_DIR = "~/.shotdeck/context"
