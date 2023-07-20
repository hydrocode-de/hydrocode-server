from typing import cast
from dataclasses import dataclass
import re

from fabric import Connection


@dataclass
class HydrocodeServer(object):
    connection: str = 'localhost'

    @property
    def run(self):
        # create a remote warpper            
        def _run(*args, **kwargs):
            with Connection(self.connection) as con:
                return con.run(*args, **kwargs)
        
        # create a local wrapper
        def _run_local(*args, **kwargs):
            with Connection(self.connection) as con:
                return con.local(*args, **kwargs)

        # check which one to use
        if 'localhost' in self.connection:
            return _run_local
        else:
            return _run

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

    @property
    def info(self) -> dict:
        # container for info
        info = dict(
            git_version=self._extract_semver('git --version'),
            docker_version=self._extract_semver('docker --version'),
            nginx_version=self._extract_semver('nginx -v'),
            certbot_version=self._extract_semver('certbot --version'),
            curl_version=self._extract_semver('curl --version'),
        )

        # return
        return info
    
    def get_free_port(self) -> int:
        cmd = "import socket; s = socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()"

        res = self.run(cmd, hide='both')
        return int(res.stdout)

    def supabase(self, project: str):
        pass