Random snippets relating to interfacing with Compendium (http://compendium.open.ac.uk/institute/about.htm).  
Initially written as proof of principle examples.

The included Python class generates some statistics about the Nodes in a compendium database:

    # How many non-deleted nodes
    # How many nodes of each type
    # Tag statistics
    # Decisions without evidence
    # Unanswered questions
    # Number of nodes created by each user
    # History of how many nodes were created/modified by each user on each day

These are saved as a CSV file (which will be appended if it already exists) and plotted using Matplotlib.

The php file does something similar but provides a very simple web UI.