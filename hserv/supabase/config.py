from typing import Dict, List, Union, TYPE_CHECKING
from dataclasses import dataclass, field
import os
import io
import re
import yaml

if TYPE_CHECKING:
    from .controller import SupabaseController


ENV_LOOKUP: Dict[str, List[str]] = dict(
    pg_password=["POSTGRES_PASSWORD"],
    jwt_secret=["JWT_SECRET"],
    anon_jwt=["ANON_KEY"],
    service_jwt=["SERVICE_ROLE_KEY"],
    public_url=["SITE_URL"],
    site_url=["SITE_URL"],
    api_url=["SUPABASE_PUBLIC_URL", "API_EXTERNAL_URL"],
    pg_port=["POSTGRES_PORT"],
    public_port=["STUDIO_PORT"],
    api_port=["KONG_HTTP_PORT"],
)

@dataclass
class SupabaseConfig:
    controller: 'SupabaseController' = field(repr=False)

    def __post_init__(self):
        # set the paths to the relevant config files
        self._env_path = os.path.join(self.controller.docker_path, ".env")
        self._kong_path = os.path.join(self.controller.docker_path, 'volumes', 'api', 'kong.yml')
        
        # create buffers for the config
        envBuf = io.StringIO()
        kongBuf = io.StringIO()

        # load the config into buffer
        self.controller.server.get(self._env_path, envBuf)
        self.controller.server.get(self._kong_path, kongBuf)

        # set as attributes
        self._env = envBuf.getvalue()
        self._kong = yaml.load(kongBuf, Loader=yaml.FullLoader)

    def save(self):
        # load the current config into buffers
        envBuf = io.StringIO(self._env)
        kongBuf = io.StringIO()
        yaml.dump(self._kong, kongBuf)

        # send to the server
        self.controller.server.put(envBuf, self._env_path)
        self.controller.server.put(kongBuf, self._kong_path)

    def __getattr__(self, name: str):
        # first check if name is in the lookup table
        if name in ENV_LOOKUP:
            names = ENV_LOOKUP[name]
        else:
            names = [name]

        # use only the first, as all have the same value
        name = names[0]

        # extract
        regex = re.search(r'%s=(.+)[\n\r]' % name, self._env)
        if regex is None:
            raise AttributeError(f"Attriubte '{name}' is not a valid environment configuration value.")
        else:
            return regex.group(1)

    def get(self, name: str, default=None):
        try:
            return getattr(self, name)
        except AttributeError:
            return default
    
    def __setattr__(self, name: str, value: Union[str, int]):
        # make a list first
        if name in ENV_LOOKUP:
            names = ENV_LOOKUP[name]
        else:
            names = [name]
        
        # check that all names are in the env
        if not all([n in self._env for n in names]):
            super().__setattr__(name, value)
            return 
        
        # still here means replace the config
        env = self._env
        for n in names:
            # get the current value
            current_val = getattr(self, n)
            env.replace(f"{n}={current_val}", f"{n}={value}")
        
        # finally set the new env
        self._env = env
