from typing import Optional, Union
from dataclasses import dataclass
import re
import os

from fabric import Connection


@dataclass
class HydrocodeServer(object):
    connection: Optional[Union[Connection, str]] = None
    supabase_location: Optional[str] = os.path.expanduser('~')

    def __post_init__(self):
        # set connection to localhost if None
        if self.connection is None:
            self.connection = 'localhost'
        
        # create a connection
        if isinstance(self.connection, str):
            self.connection = Connection(self.connection)

    @property
    def run(self):
        if 'localhost' in self.connection.host.lower():
            return self.connection.local
        else:
            return self.connection.run

    def _extract_semver(self, command: str) -> str:
        # get git version
        try:
            v = self.run(command, hide='both')
            s = re.search(r'(\d+\.\d+\.\d+)', v.stdout)
        except Exception:
            s = None
        
        # check if s is None
        if s is None:
            return 'unknown'
        else:
            return s.group(1)

    def info(self) -> dict:
        # container for info
        info = dict(
            git_version=self._extract_semver('git --version'),
            docker_version=self._extract_semver('docker --version'),
            nginx_version=self._extract_semver('nginx -v'),
            certbot_version=self._extract_semver('certbot --version'),
        )

        # return
        return info
