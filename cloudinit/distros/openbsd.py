# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import distros
from cloudinit import log as logging
from cloudinit.distros import netbsd

LOG = logging.getLogger(__name__)


class Distro(netbsd.NetBSD):
    hostname_conf_fn = "/etc/myname"
    init_cmd = ["rcctl"]

    def _read_hostname(self, filename, default=None):
        return distros.util.load_file(self.hostname_conf_fn)

    def _write_hostname(self, hostname, filename):
        content = hostname + "\n"
        distros.util.write_file(self.hostname_conf_fn, content)

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        return ["usermod", "-G", group_name, member_name]

    def manage_service(self, action: str, service: str):
        """
        Perform the requested action on a service. This handles OpenBSD's
        'rcctl'.
        May raise ProcessExecutionError
        """
        init_cmd = self.init_cmd
        cmds = {
            "stop": ["stop", service],
            "start": ["start", service],
            "enable": ["enable", service],
            "disable": ["disable", service],
            "restart": ["restart", service],
            "reload": ["restart", service],
            "try-reload": ["restart", service],
            "status": ["check", service],
        }
        cmd = list(init_cmd) + list(cmds[action])
        return distros.subp.subp(cmd, capture=True)

    def lock_passwd(self, name):
        try:
            distros.subp.subp(["usermod", "-p", "*", name])
        except Exception:
            distros.util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def unlock_passwd(self, name):
        pass

    def _get_pkg_cmd_environ(self):
        """Return env vars used in OpenBSD package_command operations"""
        e = os.environ.copy()
        return e
