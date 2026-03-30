"""IP address filtering (allow/deny lists with CIDR support)"""

import ipaddress as _ipaddress
import logging as _logging


class IpFilter:
    """Filter IP addresses against allow/deny lists.

    Logic:
    1. If IP matches deny list -> reject
    2. If allow list is empty -> allow (unless denied)
    3. If allow list is not empty -> IP must be in it
    """

    def __init__(self, allow=None, deny=None, log=None):
        self._log = log if log else _logging.getLogger(__name__)
        self._allow = []
        self._deny = []
        for network in (allow or []):
            try:
                self._allow.append(
                    _ipaddress.ip_network(network, strict=False))
            except ValueError as err:
                self._log.warning("Invalid allow network '%s': %s",
                    network, err)
        for network in (deny or []):
            try:
                self._deny.append(
                    _ipaddress.ip_network(network, strict=False))
            except ValueError as err:
                self._log.warning("Invalid deny network '%s': %s",
                    network, err)

    @property
    def is_enabled(self):
        """Return True if filter has any rules"""
        return bool(self._allow or self._deny)

    def is_allowed(self, ip_str):
        """Return True if IP address is allowed.

        Args:
            ip_str: IP address as string (e.g. "192.168.1.100")

        Returns:
            True if allowed, False if denied
        """
        try:
            ip_addr = _ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # Check deny list first
        for network in self._deny:
            if ip_addr in network:
                return False
        # If allow list is empty, allow (not denied)
        if not self._allow:
            return True
        # Check allow list
        for network in self._allow:
            if ip_addr in network:
                return True
        return False


def create_filter(config, log=None):
    """Create IpFilter from server config.

    Args:
        config: Server config dict with optional 'allow' and 'deny' lists
        log: Logger instance

    Returns:
        IpFilter instance or None if no filtering configured
    """
    allow = config.get('allow')
    deny = config.get('deny')
    if not allow and not deny:
        return None
    return IpFilter(allow=allow, deny=deny, log=log)
