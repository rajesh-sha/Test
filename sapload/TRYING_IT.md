================================================================================
  SAP LOAD WORKBENCH
  Map an extract onto an SAP upload template, check every row, reconcile.
================================================================================

There are three ways to use this. Most people only need the first.


--------------------------------------------------------------------------------
  1.  THE EASY WAY  —  no installation at all
--------------------------------------------------------------------------------

    Double-click        SAP-Load-Workbench.html

It opens in your browser and works offline. Nothing to install, no Python,
no server, no admin rights. To give it to a colleague, email them that one
file — that is the whole tool.

    Step 1   Drag in the SAP upload template, then your extract.
    Step 2   Read what the template wants.
    Step 3   Check the mapping. Change anything wrong from the dropdown.
    Step 4   Read the problems. These are rows SAP would have rejected.
    Step 5   Download the filled template and the reconciliation pack.

Then upload the filled template to SAP exactly as you do today, and keep the
reconciliation pack. That pack is your evidence.

Try it first on the two files in  samples/  — the extract has deliberate
errors in it so you can see the checking work.

Your corrections are remembered in that browser, so the second run of the
same weekly extract needs no corrections at all.


--------------------------------------------------------------------------------
  2.  THE SAME THING, SCRIPTABLE  —  needs Python 3.9+
--------------------------------------------------------------------------------

Use this to put the weekly run on a schedule, or in a pipeline.

    python -m sapload.cli inspect "samples/Supplier Invoice_EN.xlsx"

    python -m sapload.cli build samples/fsm_subcontractor_claims.csv \
        "samples/Supplier Invoice_EN.xlsx" upload.xlsx \
        --memory mappings.json --recon recon.txt --max-rows 999

If something will not run:

    python check.py

That names the cause in plain terms rather than a stack trace.


--------------------------------------------------------------------------------
  3.  CONNECTED TO S/4HANA  —  read-only unless you say otherwise
--------------------------------------------------------------------------------

READ  sapload/SECURITY.md  BEFORE USING THIS.

Neither of the first two ways touches SAP at all. This one does, and it
changes what the tool is: connected, it becomes an interface, with the
governance that brings.

Credentials come from the environment. Never from a file here, never from
the command line — a command line ends up in shell history and in ps.

    export SAPLOAD_BASE_URL=https://my123456-api.s4hana.cloud.sap
    export SAPLOAD_USERNAME=YOUR_COMM_USER
    export SAPLOAD_PASSWORD=...

    python -m sapload.cli connect ping

Then the two things a read-only connection buys:

    # Live value help — catches a wrong cost centre or G/L account on your
    # desk instead of halfway through an SAP upload
    python -m sapload.cli connect value-help \
        --template "samples/Supplier Invoice_EN.xlsx" --cache valuehelp.json

    # Read the posted documents back and agree them to what you sent
    python -m sapload.cli connect reconcile \
        --sent samples/fsm_subcontractor_claims.csv \
        --reference claim_number --amount gross_amt --out posted.txt

Posting directly to SAP is built, tested and OFF. It requires
SAPLOAD_ALLOW_POST=1, set deliberately. Without it a write fails before a
network connection is even opened.

For anything touching finance, use OAuth SAML bearer rather than a shared
communication user, so the named person's identity reaches SAP and the audit
trail is per person. SECURITY.md explains how and why.


--------------------------------------------------------------------------------
  WHAT IT IS FOR, AND WHAT IT IS NOT
--------------------------------------------------------------------------------

For:      recurring, post-go-live loads through SAP's own spreadsheet upload
          apps — the weekly and month-end runs somebody does by hand today.

Not for:  initial migration at cutover. That belongs in the SAP S/4HANA
          Migration Cockpit, which has full object coverage and SAP support.


--------------------------------------------------------------------------------
  TEACHING IT YOUR VOCABULARY
--------------------------------------------------------------------------------

Everything the matcher knows about SAP field names is in ONE file:

    sapload/knowledge.json

Add your own terms to "synonyms" — each inner list is a set of words that
mean the same thing:

    ["your term", "what SAP calls it", "what the legacy system calls it"]

That is the whole change. No code, in either language. Then:

    python build.py

to fold it into SAP-Load-Workbench.html. The Python side picks it up with no
build at all.

This is deliberately the only place that changes as a client's vocabulary
changes, so the two runtimes cannot drift apart. A test enforces it.


--------------------------------------------------------------------------------
  TESTS
--------------------------------------------------------------------------------

    python -m unittest tests.test_sapload      # 36  the engine
    python -m unittest tests.test_smartmapper  # 23  the matcher
    python -m unittest tests.test_connect      # 35  the S/4 connection
    python -m unittest tests.test_build        #  9  the two runtimes agree
    python examples/demo_sapload.py            #     guided walkthrough


--------------------------------------------------------------------------------
  ONE THING TO VERIFY BEFORE PRODUCTION
--------------------------------------------------------------------------------

Upload a 10-row file with a deliberately bad row 6 and see what happens to
rows 1 to 5. Whether the earlier rows stay posted is not documented anywhere,
and at 800 claims a week it decides your re-submission procedure.
