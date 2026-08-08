"""Throwaway diagnostic: why does the Apps tab show zero apps?

    python probe_software.py            # every Software on the site
    python probe_software.py <proj-id>  # plus the per-project filtering

Prints each Software with the three things that decide whether it is listed:
status, project links, and whether it has anything to launch.
"""

import sys

import config
import shotgun_api3

sg = shotgun_api3.Shotgun(
    config.SG_SITE,
    script_name=config.SG_SCRIPT_NAME,
    api_key=config.SG_SCRIPT_KEY,
)

project_id = int(sys.argv[1]) if len(sys.argv) > 1 else None

# No status filter here -- the point is to see what the status actually is.
sws = sg.find("Software", [], config.SOFTWARE_FIELDS)
print("Software entities on site: {0}\n".format(len(sws)))

for sw in sws:
    links = sw.get("projects") or []
    rez = sw.get(config.SOFTWARE_REZ_FIELD) or ""
    reasons = []
    if sw.get("sg_status_list") != "act":
        reasons.append("status is {0!r}, not 'act'".format(sw.get("sg_status_list")))
    if project_id and links and not any(p["id"] == project_id for p in links):
        reasons.append("not linked to project {0}".format(project_id))
    if not sw.get("linux_path") and not rez:
        reasons.append("no linux_path and no {0}".format(config.SOFTWARE_REZ_FIELD))

    print("{0:<24} status={1!r:<8} linux_path={2!r}".format(
        sw.get("code"), sw.get("sg_status_list"), sw.get("linux_path")))
    print("{0:<24} rez={1!r}  projects={2}".format(
        "", rez, [p["id"] for p in links] or "global"))
    print("{0:<24} {1}".format(
        "", "LISTED" if not reasons else "HIDDEN: " + "; ".join(reasons)))
    print()
