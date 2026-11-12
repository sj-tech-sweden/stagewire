"""NetBox IPAM/DCIM integration for Stagewire.

Optional integration that lets technicians pull IP addresses and structured
cabling context from a NetBox instance that is the organisation's source of
truth for IPAM/DCIM, and mirror Stagewire AVL devices into NetBox.

Everything here degrades gracefully: when the integration is disabled or
unconfigured the rest of Stagewire works exactly as before (network settings
remain a local manual entry).
"""
