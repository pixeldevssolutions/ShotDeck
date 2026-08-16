Silhouette startup hook -- not wired yet, on purpose.

Maya and Nuke are wired in package.py because their startup mechanisms are
documented and stable (userSetup.py on PYTHONPATH; init.py/menu.py on
NUKE_PATH). The Silhouette build on the 5and8 farm has not been inspected, and
guessing an environment variable produces a package that looks installed and
silently does nothing -- the worst outcome of the three.

To finish it:

  1. Find the version and its Python module:

       rez env silhouette shotdeck_dcc -- sfx --version
       # then, from Silhouette's own script console:
       exec(open("$SHOTDECK_DCC_ROOT/probe_silhouette.py").read())

     The probe prints the interpreter, which host module exists (fx,
     silhouette, ...), any attribute whose name mentions menu/action/save/
     project, the script search paths it exposes, and the SHOTDECK_* variables.

  2. Put the startup script this build expects in this folder.

  3. Point Silhouette at it from package.py's commands(), next to the maya and
     nuke blocks, e.g.

       if "silhouette" in resolve:
           env.<THE_REAL_VAR>.prepend("{root}/startup/silhouette")

  4. Fill in _build_menu() in shotdeck_dcc/adapters/silhouette.py, and extend
     SAVE_METHODS there if the probe names a different save entry point.

Until then, inside Silhouette this works:

    import shotdeck_dcc
    shotdeck_dcc.install()          # loads, reports the missing menu API
    shotdeck_dcc.adapter().action_save_next_version()
