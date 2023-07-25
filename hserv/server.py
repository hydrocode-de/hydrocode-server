from typing import Union, Optional, cast, Dict, Any, Union, List, TYPE_CHECKING
from typing_extensions import Literal
from dataclasses import dataclass, field
import re
import io
import os
import shutil

from fabric import Connection, Result

if TYPE_CHECKING:
    from hserv.supabase.controller import SupabaseController
    from hserv.webproxy.proxy import WebProxy

@dataclass
class HydrocodeServer(object):
    connection: str = 'localhost'
    username: str = 'root'
    bypass_localhost: bool = False
    wd: Optional[str] = None
    
    _supabase_projects: Dict[str, 'SupabaseController'] = field(default_factory=dict, init=False)
    _webproxy_projects: Dict[str, 'WebProxy'] = field(default_factory=dict, init=False)

    @property
    def run(self):
        # create a remote warpper            
        def _run(*args, **kwargs):
            with Connection(self.connection, user=self.username) as con:
                return con.run(*args, **kwargs)
        
        # create a local wrapper
        def _run_local(*args, **kwargs):
            with Connection(self.connection) as con:
                res = con.local(*args, **kwargs)
                if res is None:
                    return Result(connection=con)
                else:
                    return res

        # check which one to use
        if self.bypass_localhost and 'localhost' in self.connection:
            return _run_local
        else:
            return _run

    @property
    def put(self):
        # create a remote wrapper
        def _put(*args, **kwargs):
            with Connection(self.connection, user=self.username) as con:
                return con.put(*args, **kwargs)
        
        def _put_local(local: Union[str, io.IOBase], remote: Optional[str] = None):
            # check combination
            if not isinstance(local, str) and remote is None:
                raise ValueError("If local is not a string, remote must be specified.")
            elif isinstance(local, str) and remote is None:
                remote = local
            
            # check if the pass object is a string
            if isinstance(local, str):
                shutil.copyfile(local, cast(str, remote))
            
            # otherwise, check the type
            with open(cast(str, remote), 'w' if isinstance(local, io.StringIO) else 'wb') as f:
                cast(io.IOBase, local).seek(0)
                f.write(cast(io.IOBase, local).read())
        
        # check which one to use
        if self.bypass_localhost and 'localhost' in self.connection:
            return _put_local
        else:
            return _put

    @property
    def get(self):
        # create a remote wrapper
        def _get(*args, **kwargs):
            with Connection(self.connection, user=self.username) as con:
                return con.get(*args, **kwargs)
        
        def _get_local(remote: str, local: Optional[Union[str, io.IOBase]] = None):
            # if local is None, use the basename of remote
            if local is None:
                local = os.path.basename(remote)
            
            # if local is a string, copy the file
            if isinstance(local, str):
                shutil.copyfile(remote, local)
            else:
                # otherwise, read in the file as BytesIO
                with open(remote, 'rb') as f:
                    # check the buffer type
                    if isinstance(local, io.StringIO):
                        local.write(f.read().decode())
                    else:
                        local.write(f.read())

        # check which one to use
        if self.bypass_localhost and 'localhost' in self.connection:
            return _get_local
        else:
            return _get                

    def exists(self, path: str) -> bool:
        # create the remote wrapper
        res = self.run(f"cd {self.cwd}; python -c \"import os; print(os.path.exists('{path}'))\"", hide=True)
        return res.stdout.strip() == 'True'

    @property
    def cwd(self):
        if self.wd is None:
            return self.run("pwd", hide=True).stdout.strip()
        else:
            return self.wd

    def cp(self, src: str, dst: str):
        self.run(f"cp {src} {dst}", hide=True)

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
            nginx_version=self._extract_semver('nginx -v 2>&1'),
            certbot_version=self._extract_semver('certbot --version'),
            curl_version=self._extract_semver('curl --version'),
        )

        # return
        return info
    
    def get_free_port(self) -> int:
        cmd = "python -c \"import socket; s = socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()\""

        res = self.run(cmd, hide='both')
        return int(res.stdout)

    def update_dependencies(self, quiet: bool = False) -> None:
        self.run("apt update && apt upgrade -y", hide=quiet)

    def install_dependencies(self, deps: Union[List[str], str] = 'all', quiet: bool = False) -> None:
        # first update the system
        self.update_dependencies(quiet=quiet)

        if deps == 'all':
            deps = ['curl', 'git', 'docker', 'nginx', 'certbot']
        elif isinstance(deps, str):
            deps = [deps]

        # first do curl, as docker needs curl as well
        if 'curl' in deps:
            self.run('apt install -y curl', hide=quiet)

        # install git
        if 'git' in deps:
            self.run('apt install -y git', hide=quiet)
        
        # docker
        if 'docker' in deps:
            # install docker dependencies
            self.run('apt install -y ca-certificates gnupg', hide=quiet)

            # add the docker gpg key
            self.run('install -m 0755 -d /etc/apt/keyrings', hide=quiet)
            self.run('curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg', hide=quiet)
            self.run('chmod a+r /etc/apt/keyrings/docker.gpg', hide=quiet)

            # add docker to the sources
            self.run('echo "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" |  tee /etc/apt/sources.list.d/docker.list > /dev/null', hide=quiet)

            # update again
            self.run('apt update', hide=quiet)

            # finally install
            self.run('apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin', hide=quiet)

        # nginx
        if 'nginx' in deps:
            self.run('apt install -y nginx', hide=quiet)
        
        # install certbot
        if 'certbot' in deps:
            self.run('apt install -y certbot python3-certbot-nginx', hide=quiet)

    def supabase(self, project: str, **kwargs) -> 'SupabaseController':
        # check if we have an instance of that project
        if project in self._supabase_projects:
            return self._supabase_projects[project]
        else:
            # initialize a new supabase controller
            from hserv.supabase.controller import SupabaseController

            # update the kwargs
            kwargs.setdefault('public_url', self.connection)
            kwargs.setdefault('path', self.cwd)

            # always overwrite the server reference
            kwargs['server'] = self

            # instantiate the controller
            controller = SupabaseController(project, **kwargs)

            # cache the controller
            self._supabase_projects[project] = controller

            # return
            return controller

    def webproxy(self, project: str, type: Union[Literal['nginx'], Literal['apache']]) -> 'WebProxy':
        # check if we have an instance of that project
        if project in self._webproxy_projects:
            return self._webproxy_projects[project]

        # initialize a new supabase controller
        if type == 'nginx':
            from hserv.webproxy.nginx import NginxProxy as Proxy
            base_path = 'etc/nginx'
        elif type == 'apache':
            raise NotImplementedError("Apache is not yet supported.")
            base_path = 'etc/apache2'
        else:
            raise ValueError(f"Unknown webproxy type: {type}")

        # instantiate the controller
        proxy = Proxy(server=self, base_path=base_path)

        # cache the instance
        self._webproxy_projects[project] = proxy

        # return
        return proxy