"""Build the Flow user guide: screenshots, then a PDF.

    python tools/docs/make_manual.py          # images + docs/Flow-User-Guide.pdf

Qt renders both halves, so this needs nothing beyond the PySide6 that Flow
already depends on -- no LaTeX, no wkhtmltopdf, no reportlab.
"""

import html as html_mod
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import shots                              # noqa: E402  (sets up sys.path)

from PySide6.QtCore import QMarginsF, QSizeF, QUrl     # noqa: E402
from PySide6.QtGui import (QImage, QPageLayout, QPageSize, QPdfWriter,
                           QTextDocument)

OUT_PDF = os.path.join(ROOT, "docs", "Flow-User-Guide.pdf")
DPI = 96
IMG_WIDTH = 660          # px at 96 dpi: A4 minus 15 mm margins


# -- page furniture --------------------------------------------------------

CSS = """
body   { font-family: 'Segoe UI', 'DejaVu Sans', sans-serif;
         font-size: 10.5pt; color: #1b1b1b; }
h1     { font-size: 25pt; color: #123a5c; margin-top: 26px; }
h2     { font-size: 16pt; color: #123a5c; margin-top: 22px; }
h3     { font-size: 12.5pt; color: #2b2b2b; margin-top: 16px; }
p, li  { line-height: 148%; }
code   { font-family: 'Consolas', 'DejaVu Sans Mono', monospace;
         font-size: 9.5pt; background: #eef1f4; }
pre    { font-family: 'Consolas', 'DejaVu Sans Mono', monospace;
         font-size: 9pt; background: #eef1f4; padding: 8px; }
table  { border-collapse: collapse; }
th     { background: #e7ecf1; text-align: left; font-size: 9.5pt; }
td     { font-size: 9.5pt; }
.fig     { line-height: 100%; }
.caption { color: #5a6672; font-size: 9pt; }
.note    { background: #eef4fb; padding: 9px; }
.warn    { background: #fbf3e4; padding: 9px; }
"""


def figure(name, caption, images, width=IMG_WIDTH):
    """One screenshot with its caption, or a placeholder if it never rendered.

    Both width and height go on the tag: given width alone, QTextDocument
    draws the image scaled but still reserves its full original height, which
    leaves a page-long gap above every caption.
    """
    if name not in images:
        return ("<p class='warn'>[screenshot '%s' could not be rendered on "
                "this machine]</p>" % html_mod.escape(name))
    source = QImage(os.path.join(shots.OUT, images[name]))
    # Never upscale: a small grab blown up just looks broken on paper.
    width = min(width, source.width()) or width
    height = (round(width * source.height() / source.width())
              if source.width() else width)
    return ("<p class='fig'><img src='{0}' width='{1}' height='{2}'></p>"
            "<p class='caption'>{3}</p>").format(
                images[name], width, height, html_mod.escape(caption))


def table(headers, rows):
    head = "".join("<th>%s</th>" % h for h in headers)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r)
                   for r in rows)
    return ("<table width='100%' border='1' cellpadding='5' cellspacing='0'>"
            "<tr>{0}</tr>{1}</table>").format(head, body)


# -- the guide -------------------------------------------------------------

def build_html(images):
    f = lambda key, cap, w=IMG_WIDTH: figure(key, cap, images, w)   # noqa: E731
    parts = []
    add = parts.append

    add("<style>%s</style>" % CSS)

    # ---------------------------------------------------------------- cover
    add("""
    <h1>Flow — User Guide</h1>
    <p><b>5and8 pipeline desktop</b> &nbsp;·&nbsp; every screen, step by
    step.</p>
    <p>Flow is the desktop app artists open at the start of the day. It signs
    you in, shows the projects you are on, launches the DCCs with the project
    environment already set, and carries your task context into Maya, Nuke,
    Houdini, Blender, Silhouette, Substance, Rhino and 3DEqualizer so that
    saving, versioning and publishing land in the right folders without anyone
    typing a path.</p>
    <p>This guide walks every screen in the order you meet it. Each section is
    a numbered procedure followed by the screen it applies to.</p>

    <h3>Contents</h3>
    <ol>
      <li>Starting Flow and signing in</li>
      <li>Choosing a project</li>
      <li>The header bar</li>
      <li>The Apps tab — launching software</li>
      <li>The My Tasks tab</li>
      <li>The task right-click menu</li>
      <li>Launching a DCC against a task</li>
      <li>Inside the DCC — the 5and8 menu</li>
      <li>Publishing without opening a DCC</li>
      <li>Browsing versions</li>
      <li>Comparing two versions</li>
      <li>Notes and replies</li>
      <li>Needs Attention</li>
      <li>The Terminal pane</li>
      <li>Keyboard shortcuts</li>
      <li>When something goes wrong</li>
    </ol>
    """)

    # ------------------------------------------------------------- 1. start
    add("<h1>1. Starting Flow and signing in</h1>")
    add("""
    <ol>
      <li>Launch <b>Flow</b> from the desktop launcher, or run
          <code>flow.sh</code> from a terminal.</li>
      <li>The splash appears while Flow authenticates you and contacts
          ShotGrid. The status line under the wordmark says which step it is
          on — <i>Loading Pipeline</i>, <i>Connecting to ShotGrid</i>,
          <i>Preparing Workspace</i>.</li>
      <li>On a domain-joined workstation you are signed in silently with your
          Active Directory login and never see a prompt. Go to step 5.</li>
      <li>Otherwise the sign-in dialog opens. Type your workstation username
          and password and press <b>Sign in</b>. Only members of the studio's
          authorised AD group can get in; anyone else is refused with a
          message rather than a half-working window.</li>
      <li>The main window fades in behind the splash, already on the projects
          screen.</li>
    </ol>
    """)
    add(f("splash", "The splash: 5and8 wordmark, product name, and the "
                    "current startup step.", 560))
    add(f("login", "Sign-in, shown only when Windows/AD single sign-on is not "
                   "available. The username hint shows the domain prefix your "
                   "site expects.", 420))
    add("""
    <p class='note'><b>If sign-in fails</b> Flow stops rather than continuing
    unauthenticated: you get one dialog naming the reason (not in the
    authorised group, wrong password, domain controller unreachable). Nothing
    in the app is reachable until it succeeds.</p>
    """)

    # ---------------------------------------------------------- 2. projects
    add("<h1>2. Choosing a project</h1>")
    add("""
    <ol>
      <li>The projects screen lists every <b>Active</b> project you can see,
          as tiles. The count sits next to the heading.</li>
      <li>Type in <b>Search projects</b> to narrow the grid — it matches on the
          project name and on the short code under it.</li>
      <li>Click a tile to open the project.</li>
      <li>The header then shows <code>Flow &rsaquo; &lt;project&gt;</code>,
          and a <b>&lsaquo; Projects</b> button appears on the left to come
          back here.</li>
    </ol>
    """)
    add(f("projects", "Projects. The small grey line under each name is the "
                      "project's short code — the folder name on disk."))

    # ------------------------------------------------------------ 3. header
    add("<h1>3. The header bar</h1>")
    add("<p>The header is the same on every screen inside a project.</p>")
    add(table(
        ["Control", "What it does"],
        [["<b>&lsaquo; Projects</b>",
          "Back to the project grid."],
         ["<b>Breadcrumb</b>",
          "<code>Flow &rsaquo; &lt;project&gt;</code> — which show you are in."],
         ["<b>Search my tasks</b>",
          "Find a task across <i>all</i> your projects without remembering "
          "which show it is on. <code>Ctrl+K</code> focuses it; pick a result "
          "and Flow opens that project and selects the task for you."],
         ["<b>Needs Attention</b>",
          "Toggles the review screen (section 13). The button carries the "
          "unread count, so you can see there is feedback without going "
          "looking for it."],
         ["<b>Terminal</b>",
          "Shows what Flow is running in the background (section 14). "
          "<code>Ctrl+`</code>."],
         ["<b>Your name chip</b>",
          "Click for the profile menu: name, login, email, how you were "
          "signed in (AD single sign-on, password, developer override), the "
          "domain, and which ShotGrid <i>HumanUser</i> your email matched. "
          "If that last row says no user matched, your tasks will be empty — "
          "see section 16."]]))

    # -------------------------------------------------------------- 4. apps
    add("<h1>4. The Apps tab — launching software</h1>")
    add("""
    <ol>
      <li>Open a project. It lands on <b>Apps</b>.</li>
      <li>Each tile is a piece of software your studio has configured for this
          show, with its version underneath.</li>
      <li>Click a tile to launch it. Flow builds the environment first
          (studio defaults, then the project's own settings), then starts the
          application detached — closing Flow afterwards does not kill it.</li>
      <li>Watch the status line at the bottom, or open the <b>Terminal</b>
          pane, to see the exact command and environment it used.</li>
    </ol>
    <p class='warn'><b>Launching from this tab carries no task.</b> The status
    bar says so: <i>No task selected — apps launch without a publish
    context</i>. Save, Version Up and Publish inside the DCC all need a task,
    so if you intend to work on a shot, launch from <b>My Tasks</b>
    (section 7) instead.</p>
    """)
    add(f("apps", "The Apps tab. Tiles come from the Software entities in "
                  "ShotGrid; ones with no project link show on every show."))

    # ------------------------------------------------------------- 5. tasks
    add("<h1>5. The My Tasks tab</h1>")
    add("""
    <ol>
      <li>Click <b>My Tasks</b>. It lists the tasks assigned to you on this
          project.</li>
      <li>Use <b>Filter tasks</b> to narrow the list as you type.</li>
      <li>Click a row to select it. The status bar at the bottom then names
          the task that apps will launch against.</li>
      <li>Right-click a row for everything you can do with it (section 6).</li>
    </ol>
    """)
    add(table(
        ["Column", "Meaning"],
        [["Task", "The task name, e.g. Compositing."],
         ["Link", "The shot or asset the task hangs off."],
         ["Step", "The pipeline step — this decides the folder your scenes "
                  "save into."],
         ["Status", "The ShotGrid status. Change it in place from the "
                    "right-click menu."],
         ["Latest version", "The newest Version published against this task, "
                            "so you can see where the work got to without "
                            "opening anything."],
         ["Due", "The task's due date."]]))
    add("""
    <p>A coloured dot on a row means that task needs attention — a note, a
    reply, or a version pushed back for changes. Hover it for the reason, or
    open <b>Needs Attention</b> for the full list.</p>
    """)
    add(f("tasks", "My Tasks. Tasks are matched to you by email address, not "
                   "by login name."))

    # -------------------------------------------------------------- 6. menu
    add("<h1>6. The task right-click menu</h1>")
    add("""
    <p>Right-clicking a task row is where most of Flow's work happens. The
    menu is built for the row you clicked, so every action already knows the
    project, shot, task and step.</p>
    """)
    add(table(
        ["Menu entry", "What it does"],
        [["<b>Publish &rsaquo; Standalone Publish…</b>",
          "Upload a movie or an image to ShotGrid as a Version without "
          "opening a DCC. See section 9."],
         ["<b>Latest Version &rsaquo;</b>",
          "Jump straight to the newest Version on this task — play it, open "
          "it in RV, or open its page. Greyed out with a reason when nothing "
          "has been published yet."],
         ["<b>Versions &rsaquo; View Versions</b>",
          "Open the version browser for this task (section 10). Disabled when "
          "the task has no shot or asset linked, because there would be "
          "nothing to browse."],
         ["<b>Set status &rsaquo;</b>",
          "Change the task's ShotGrid status in place. The choices are read "
          "from your site's own status list, so they match ShotGrid exactly."],
         ["<b>Shot folder</b> / <b>Asset folder</b>",
          "Open the task's top folder in the file manager. Greyed out when "
          "the folder has not been created yet."],
         ["<b>Open folder &rsaquo;</b>",
          "The sub-folders — work, publish, renders and so on — plus "
          "<b>Copy path</b>. Entries that do not exist yet are greyed out "
          "rather than hidden, so you can see what the layout should be."],
         ["<b>&lt;DCC&gt; &lt;version&gt;</b>",
          "The bottom band lists every DCC found in the studio package tree. "
          "Picking one launches it <i>against this task</i> — the part that "
          "matters (section 7)."]]))
    add(f("task_menu", "The right-click menu on a task. The software at the "
                       "bottom is scanned fresh each time you open the menu, "
                       "so a newly released version appears without "
                       "restarting Flow.", 300))

    # ------------------------------------------------------------ 7. launch
    add("<h1>7. Launching a DCC against a task</h1>")
    add("""
    <ol>
      <li>Go to <b>My Tasks</b> and right-click the task you are working on.</li>
      <li>Pick the application and version from the bottom of the menu — for
          example <b>Maya &rsaquo; 2024 (latest)</b>. A package with only one
          version installed appears as a single line instead of a submenu.</li>
      <li>Flow resolves the package, injects the project environment and your
          task context, and starts the application.</li>
      <li>The Terminal pane shows the resolved command and the context
          variables if you want to check them.</li>
      <li>When the DCC finishes loading, a <b>5and8</b> menu is on its menu
          bar. That menu is how you save, version and publish (section 8).</li>
    </ol>
    <p class='note'><b>Why launch from a task and not from Apps?</b> The launch
    is what carries the context. Everything downstream — the folder your scene
    saves into, the version number, the publish name, the ShotGrid record —
    is derived from the task you launched against. A DCC opened from the Apps
    tab has no task, and its 5and8 menu will tell you to pick one and
    relaunch.</p>
    """)

    # --------------------------------------------------------------- 8. DCC
    add("<h1>8. Inside the DCC — the 5and8 menu</h1>")
    add("""
    <p>Every supported host gets the same menu, in the same order. The two
    entries that leave your workstation — Publish and Submit — sit in a band
    of their own so neither is hit on the way to Save.</p>
    """)
    add(table(
        ["Menu item", "What happens"],
        [["<b>Save</b>",
          "Saves over the scene that is open. If the scene has never been "
          "saved there is nothing to save over, so Flow tells you and runs "
          "<b>Version Up</b> instead rather than inventing a location."],
         ["<b>Save As…</b>",
          "A save dialog that opens <i>on the task's work folder</i> with the "
          "correct next pipeline name already filled in. Pressing Enter gives "
          "you the convention; Save As is for the exception. If you save "
          "outside the work folder, Flow says so — files out there are not "
          "counted when working out the next version."],
         ["<b>Version Up</b>",
          "Saves the open scene as the next version in the task's work "
          "folder. The number is one past the highest already on disk."],
         ["<b>Publish…</b>",
          "Shows you exactly what will happen — version number, work path, "
          "publish path — and asks for confirmation. On OK it saves the "
          "scene, copies it into the publish folder under the same name, "
          "verifies the copy, and registers a PublishedFile in ShotGrid."],
         ["<b>Submit to Deadline…</b>",
          "Saves the scene first (the farm renders the file on disk, so "
          "submitting unsaved would queue yesterday's work), then shows the "
          "plugin, frame range, pool and scene path for confirmation before "
          "the job is sent."],
         ["<b>Open Work Folder</b>",
          "Opens the folder your scenes save into."],
         ["<b>Open Publish Folder</b>",
          "Opens the folder publishes land in."],
         ["<b>Context</b>",
          "Prints where you are — project, entity, task, step, software — and "
          "where the next save and the next publish would go. The first thing "
          "to check when anything looks wrong."]]))

    add("<h3>8.1 The naming convention</h3>")
    add("""
    <p>You never type a scene name. Flow builds it from the launch context:</p>
    <pre>uat6_SEQ001_AD1030_lighting_jitesh_v0001.ma</pre>
    <p>project &nbsp;·&nbsp; sequence &nbsp;·&nbsp; shot &nbsp;·&nbsp; step
    &nbsp;·&nbsp; artist &nbsp;·&nbsp; version, four digits.</p>
    <p>The next version number is worked out from the files on disk, not from
    ShotGrid — so a slow or unreachable site can never block you from saving
    work in progress. If the file the next number points at somehow already
    exists, Flow refuses rather than overwriting it: someone else is probably
    working in the same folder.</p>
    """)

    add("<h3>8.2 Where files go</h3>")
    add("""
    <p>Work and publish folders sit beside each other under the shot or asset
    root, so "everything under <code>publish/</code> is safe to reference"
    stays true whatever anyone saves next door.</p>
    """)
    add(table(
        ["Host", "Work folder", "Publish folder", "Scene"],
        [["Maya", "maya/scenes/&lt;step&gt;", "maya/publish/&lt;step&gt;", ".ma"],
         ["Nuke", "nuke/&lt;step&gt;/scene", "nuke/&lt;step&gt;/publish", ".nk"],
         ["Houdini", "houdini/hip/&lt;step&gt;", "houdini/publish/&lt;step&gt;",
          ".hip"],
         ["Blender", "blender/scenes/&lt;step&gt;",
          "blender/publish/&lt;step&gt;", ".blend"],
         ["Silhouette", "silhouette/&lt;step&gt;/scene",
          "silhouette/&lt;step&gt;/publish", ".sfx"],
         ["3DEqualizer", "3DE/&lt;step&gt;/scene", "3DE/&lt;step&gt;/publish",
          ".3de"],
         ["Substance", "substance/&lt;step&gt;/scene",
          "substance/&lt;step&gt;/publish", ".spp"],
         ["Rhino", "rhino/&lt;step&gt;/scene", "rhino/&lt;step&gt;/publish",
          ".3dm"]]))
    add("""
    <p class='note'><b>If a publish half-finishes</b> the file is already
    copied and verified on disk before ShotGrid is contacted, so a site
    outage means "published, not registered" — never a missing file. The
    message says exactly that, and a supervisor can register it afterwards.</p>
    """)

    # ----------------------------------------------------------- 9. publish
    add("<h1>9. Publishing without opening a DCC</h1>")
    add("""
    <p>Use this when what you have is already a movie or a frame — a playblast,
    a turntable, a render, a reference grab — and there is no scene to
    version.</p>
    <ol>
      <li>In <b>My Tasks</b>, right-click the task and choose
          <b>Publish &rsaquo; Standalone Publish…</b></li>
      <li>Check the context block at the top: project, shot, task, department
          and the user the Version will be created under.</li>
      <li>Drop your movie or image onto the dialog, or press
          <b>Choose Image / Movie…</b>. Dropping a movie and a scene file
          together is understood as one gesture — both fields fill in.</li>
      <li>Optionally point <b>the scene file this came from</b> at the .nk,
          .ma or .hip that produced it, so the Version records its source.</li>
      <li><b>Version name</b> is pre-filled with the next name in the
          convention. Leave it unless you have a reason.</li>
      <li>Add a <b>Description</b> — what changed in this version. This is
          what a supervisor reads first.</li>
      <li>Read the <b>preflight</b> panel. Green ticks are checks that passed;
          an amber row is a warning with the reason next to it. A warning does
          not stop you, but you must tick <b>I understand the warnings
          above</b> before <b>Publish Version</b> becomes available.</li>
      <li>Press <b>Publish Version</b>. The result page confirms it, offers a
          box to post a note on the new Version, and a button to open it.</li>
    </ol>
    """)
    add(f("publish", "The publish dialog as it opens: context filled in, "
                     "version name already correct, nothing chosen yet.", 620))
    add(f("publish_filled", "After a file is chosen: thumbnail, resolution and "
                            "size are read off the media, and the preflight "
                            "has run. The amber row here is the media sitting "
                            "outside the approved project paths.", 620))

    # ---------------------------------------------------------- 10. browser
    add("<h1>10. Browsing versions</h1>")
    add("""
    <ol>
      <li>Right-click a task and choose <b>Versions &rsaquo; View
          Versions</b>.</li>
      <li>The list opens newest first. The toggle at the top right switches
          between this task only and <b>All tasks on &lt;shot&gt;</b> — use it
          to see what lighting handed you before you comp it.</li>
      <li>Narrow the list with the search box (it matches name, description,
          artist, task and shot) or the <b>Department</b>, <b>User</b>,
          <b>Status</b>, <b>Date</b> and <b>Sort</b> filters.</li>
      <li>Click a version. Its thumbnail appears on the left and the tabs on
          the right fill in: <b>Details</b>, <b>Notes</b> and
          <b>Activity</b>.</li>
      <li>Use the buttons along the bottom: <b>Play</b>, <b>Open in RV</b>,
          <b>Compare…</b>, <b>Publish New Version</b>, <b>Open in
          ShotGrid</b>.</li>
      <li><b>Load more</b> at the bottom pages through a long history rather
          than fetching thousands of rows up front.</li>
    </ol>
    """)
    add(f("browser", "The version browser. Right-clicking a row gives the same "
                     "actions as the buttons, plus copy-path and copy-name."))

    # ---------------------------------------------------------- 11. compare
    add("<h1>11. Comparing two versions</h1>")
    add("""
    <ol>
      <li>From the version browser, select a version and press
          <b>Compare…</b>; or from <b>Needs Attention</b>, press
          <b>Compare with previous</b> on a card.</li>
      <li>Version A is on the left, version B on the right, each with its
          artist, date, and a line saying what it is showing — full-resolution
          media from this machine, or the ShotGrid thumbnail when the media is
          on a mount you do not have.</li>
      <li>Switch viewing mode with the four buttons underneath.</li>
      <li><b>Fit</b> and <b>Actual size</b> control zoom; <b>Open in RV</b>
          hands both versions to RV when you need a real player.</li>
      <li>The table at the bottom lists both versions field by field, with the
          differences highlighted. The notes on both versions are listed
          beside it, so you can read the feedback against the picture.</li>
    </ol>
    """)
    add(table(
        ["Mode", "Use it for"],
        [["<b>Side by Side</b>", "General review — both frames at once."],
         ["<b>A/B</b>", "Flipping one over the other in the same spot, which "
                        "is how you catch a small move."],
         ["<b>Wipe</b>", "Dragging a divider across the frame; best for grade "
                         "and edge work."],
         ["<b>Difference</b>", "What actually changed, and nothing else."]]))
    add(f("compare", "Side by Side."))
    add(f("compare_wipe", "Wipe, with the divider dragged to the middle."))

    # ------------------------------------------------------------ 12. notes
    add("<h1>12. Notes and replies</h1>")
    add("""
    <ol>
      <li>Open a version in the browser and click the <b>Notes</b> tab.</li>
      <li>Each message shows who wrote it and their role — <i>artist</i>,
          <i>manager</i>, <i>client</i> — so you can tell a supervisor's note
          from a client's at a glance.</li>
      <li>Type in <b>Add note</b> and press <b>Post Note</b> to leave
          feedback on that version.</li>
      <li>Press <b>Reply</b> on a message to answer it; the button becomes
          <b>Post Reply</b> and <b>Cancel reply</b> backs out.</li>
      <li>Your own messages have <b>Edit</b> and <b>Delete</b>. Other
          people's do not.</li>
      <li><b>Refresh Notes</b> re-reads the thread if someone is typing at the
          same time as you.</li>
      <li>The <b>Activity</b> tab beside it is the version's history —
          status changes and events, not conversation.</li>
    </ol>
    """)
    add(f("notes", "The Notes tab: a supervisor's note and the artist's reply "
                   "on the same version.", 620))

    # ------------------------------------------------- 13. needs attention
    add("<h1>13. Needs Attention</h1>")
    add("""
    <p>This is the "what changed while I was working" screen. It answers a
    different question from My Tasks, which is why it lives in the header with
    a count on it rather than as another tab.</p>
    <p>It gathers three things:</p>
    <ul>
      <li>Notes somebody else left on <b>your</b> versions;</li>
      <li>Replies to notes <b>you</b> wrote, wherever those notes live;</li>
      <li>Versions a supervisor pushed back for changes.</li>
    </ul>
    <ol>
      <li>Click <b>Needs Attention</b> in the header.</li>
      <li>Unread items carry a dot. The header counts both totals —
          <i>3 items, 3 unread</i>.</li>
      <li>Each card names who, what, which shot and version, when, and quotes
          the message.</li>
      <li><b>Open Version</b> takes you to it; <b>Compare with previous</b>
          puts it beside the version before it.</li>
      <li>Opening an item marks it read. <b>Mark all read</b> clears the
          badge in one go; <b>Refresh</b> re-checks.</li>
    </ol>
    <p>The same information drives the dot on task rows in My Tasks, so you
    can also see which task the feedback belongs to without coming here.</p>
    """)
    add(f("review", "Needs Attention."))

    # --------------------------------------------------------- 14. terminal
    add("<h1>14. The Terminal pane</h1>")
    add("""
    <ol>
      <li>Press <code>Ctrl+`</code>, or click <b>Terminal</b> in the
          header.</li>
      <li>It opens as a pane at the bottom of the window and follows what
          Flow is doing: the resolved package request, the command line, the
          environment variables handed to the DCC, and then the application's
          own output.</li>
      <li><b>Follow</b> keeps it scrolled to the newest line. Turn it off to
          read back without being dragged forward.</li>
      <li><b>Copy</b> puts the visible log on the clipboard, <b>Save…</b>
          writes it to a file, <b>Clear</b> empties the pane.</li>
      <li>Close it with the <b>×</b>, the header button, or
          <code>Ctrl+`</code> again.</li>
    </ol>
    <p>When you report a launch problem, this pane is what to send.</p>
    """)
    add(f("console", "The Terminal following a Maya launch. Lines starting "
                     "with # are the launch header Flow writes itself."))

    # -------------------------------------------------------- 15. shortcuts
    add("<h1>15. Keyboard shortcuts</h1>")
    add(table(
        ["Keys", "Action"],
        [["<code>Ctrl+K</code>", "Focus <b>Search my tasks</b> in the header."],
         ["<code>Ctrl+`</code>", "Show or hide the Terminal pane."],
         ["<code>Esc</code>", "Close the dialog you are in."],
         ["<code>Enter</code>",
          "In Save As inside a DCC: accept the pipeline name Flow "
          "suggested."]]))
    add("""
    <p>Flow can also be started with flags from a terminal:</p>
    <pre>flow.sh --verbose     log every command and environment detail
flow.sh --console     open with the Terminal pane already showing</pre>
    """)

    # ------------------------------------------------------ 16. troubleshoot
    add("<h1>16. When something goes wrong</h1>")
    add(table(
        ["What you see", "What it means and what to do"],
        [["<b>My Tasks is empty</b>",
          "Flow matches tasks to you by <i>email address</i>, not login. Click "
          "your name chip: if the ShotGrid row says no user matched your "
          "address, your ShotGrid account has a different email on it. Send "
          "that line to your pipeline TD."],
         ["<b>The Apps tab is empty</b>",
          "No Software entities are configured for this show. You can still "
          "launch a DCC by right-clicking a task — that path reads the studio "
          "package tree instead."],
         ["<b>No 5and8 menu in the DCC</b>",
          "The DCC was not launched from Flow, or the pipeline package has "
          "not been rebuilt on this machine. Relaunch from a task; if it is "
          "still missing, that is one for the pipeline team."],
         ["<b>&quot;This session was launched without a task&quot;</b>",
          "You launched from the Apps tab. Close the DCC, go to My Tasks, "
          "right-click the task and launch from there."],
         ["<b>&quot;The next version already exists on disk&quot;</b>",
          "Someone else is probably saving into the same work folder. Check "
          "with them before saving — Flow will not overwrite it."],
         ["<b>&quot;Published, not registered&quot;</b>",
          "The file is safely published on disk; only the ShotGrid record "
          "failed. Nothing is lost. Report it so the record can be created."],
         ["<b>Compare says &quot;no media on this machine&quot;</b>",
          "The version's media is on a mount you do not have. Flow falls back "
          "to the ShotGrid thumbnail where there is one; otherwise ask for "
          "access to the mount."],
         ["<b>A launch failed</b>",
          "Open the Terminal pane, press <b>Copy</b>, and paste it into your "
          "report. The resolved command and environment are in there."]]))

    add("""
    <p class='caption'>Flow — 5and8. Screens in this guide are rendered from
    the application itself, so they stay in step with the build.</p>
    """)

    return "".join(parts)


# -- render ---------------------------------------------------------------

def write_pdf(html, path):
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    writer.setResolution(DPI)
    writer.setTitle("Flow — User Guide")

    doc = QTextDocument()
    # Images are referenced by bare file name; this is what resolves them.
    doc.setBaseUrl(QUrl.fromLocalFile(shots.OUT + os.sep))
    doc.setHtml(html)
    doc.setPageSize(QSizeF(writer.pageLayout()
                           .paintRectPixels(DPI).size().toSizeF()))
    doc.print_(writer)


def main():
    images = shots.all_shots()             # brings up QApplication too
    os.makedirs(os.path.dirname(OUT_PDF), exist_ok=True)
    write_pdf(build_html(images), OUT_PDF)
    print("\nwrote", OUT_PDF)
    return 0


if __name__ == "__main__":
    sys.exit(main())
