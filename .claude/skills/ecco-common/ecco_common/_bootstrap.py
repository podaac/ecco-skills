"""
ecco_common._bootstrap — helper so a skill script in a sibling skill directory can
import ecco_common without installing it.

Each skill script does, at the top:

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                    "..", "..", "ecco-common"))
    from ecco_common import load_grid, load_field

This file exists mainly as documentation of that convention; the one-liner above is
what skills actually use (kept inline so a script has zero prior dependencies).
"""
