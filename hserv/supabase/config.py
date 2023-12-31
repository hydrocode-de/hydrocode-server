from typing import Any, Dict, List, Union, TYPE_CHECKING
from dataclasses import dataclass, field
import os
import io
import re
import yaml

if TYPE_CHECKING:
    from .controller import SupabaseController


ENV_LOOKUP: Dict[str, List[str]] = dict(
    postgres_password=["POSTGRES_PASSWORD"],
    jwt_secret=["JWT_SECRET"],
    anon_jwt=["ANON_KEY"],
    service_jwt=["SERVICE_ROLE_KEY"],
    public_url=["SITE_URL"],
    site_url=["SITE_URL"],
    api_url=["SUPABASE_PUBLIC_URL", "API_EXTERNAL_URL"],
    postgres_port=["POSTGRES_PORT"],
    public_port=["STUDIO_PORT"],
    api_port=["KONG_HTTP_PORT"],
    organization=["STUDIO_DEFAULT_ORGANIZATION"],
    project=["STUDIO_DEFAULT_PROJECT"],
    smtp_mail=["SMTP_ADMIN_EMAIL"],
    smtp_host=["SMTP_HOST"],
    smtp_port=["SMTP_PORT"],
    smtp_user=["SMTP_USER"],
    smtp_password=["SMTP_PASS"],
    smtp_name=["SMTP_SENDER_NAME"],
)

@dataclass
class SupabaseConfig:
    controller: 'SupabaseController' = field(repr=False)

    def __post_init__(self):
        # set the paths to the relevant config files
        self._env_path = os.path.join(self.controller.docker_path, ".env")
        self._kong_path = os.path.join(self.controller.docker_path, 'volumes', 'api', 'kong.yml')
        
        # if the .env file does not exist, but the default does, copy it
        default_env = os.path.join(self.controller.docker_path, '.env.example')
        if not self.controller.server.exists(self._env_path) and self.controller.server.exists(default_env):
            self.controller.server.cp(default_env, self._env_path)

        # create buffers for the config
        envBuf = io.StringIO()
        kongBuf = io.StringIO()

        # load the config into buffer
        self.controller.server.get(self._env_path, envBuf)
        self.controller.server.get(self._kong_path, kongBuf)
        envBuf.seek(0)
        kongBuf.seek(0)

        # set as attributes
        self._env = envBuf.getvalue()
        self._kong = yaml.load(kongBuf, Loader=yaml.Loader)

    def save(self):
        # load the current config into buffers
        envBuf = io.StringIO(self._env)
        kongBuf = io.StringIO()
        yaml.dump(self._kong, kongBuf)

        # seek to the beginning
        envBuf.seek(0)
        kongBuf.seek(0)

        # send to the server
        self.controller.server.put(envBuf, self._env_path)
        self.controller.server.put(kongBuf, self._kong_path)

    def get(self, name: str, default: Any = 'raise'):
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
            if default == 'raise':
                raise AttributeError(f"Attribute '{name}' is not a valid environment configuration value.")
            else:
                return default
        else:
            return regex.group(1)
    
    def set(self, name: str, value: Union[str, int]):
        # make a list first
        if name in ENV_LOOKUP:
            names = ENV_LOOKUP[name]
        else:
            names = [name]
        
        # check that all names are in the env
        if not all([n in self._env for n in names]):
            raise AttributeError(f"Attribute '{name}' is not a valid environment configuration value.")
        
        # still here means replace the config
        env = self._env
        for n in names:
            # get the current value
            current_val = self.get(n)
            env = env.replace(f"{n}={current_val}", f"{n}={value}")
        
        # finally set the new env
        self._env = env
