from typing import Union, Optional
from typing_extensions import Literal
from dataclasses import dataclass, field
import os
import json
from string import ascii_letters, digits
from random import choice
import re
import io

import jwt

from hserv.server import HydrocodeServer
from hserv.supabase.config import SupabaseConfig


@dataclass
class SupabaseController(object):
    project: str
    path: str = field(default=os.path.expanduser('~'))
    docker_path: str = field(init=False, repr=False)
    server: HydrocodeServer = field(default_factory=HydrocodeServer, repr=False)
    quiet: bool = field(default=False, repr=False)
    jwt_secret: str = field(init=False, repr=False)

    postgres_password: str = field(init=False, repr=False)
    postgres_port: int = field(init=False, repr=False)

    # development only, this will be configured later, and derived from the project
    public_url: str = field(default="localhost")
    public_port: int = field(default=3000, repr=False)
    kong_port: int = field(init=False, repr=False)

    def __post_init__(self):      
        # check that the project is added to the path
        if not self.path.endswith(self.project):
            self.path = os.path.join(self.path, self.project)
        
        # set the docker path
        self.docker_path = os.path.join(self.path, 'supabase', 'docker')

        # check that the path exists
        if not self.server.exists(self.path):
            self.server.run(f"mkdir -p {self.path}", hide=True)

        # check that the config exists
        if not self.server.exists(os.path.join(self.path, '.config')):
            # generate a secret key
            secret = "".join([choice(ascii_letters + digits) for i in range(64)])
            pw = "".join([choice(ascii_letters + digits) for i in range(64)])

            # get free ports for postgres and kong
            pg_port = self.server.get_free_port()
            kong_port = self.server.get_free_port()

            # create a config file for the project
            configBuf = io.BytesIO(json.dumps(dict(
                    public_url=self.public_url,
                    jwt_secret=secret,
                    postgres_password=pw,
                    public_port=self.public_port,
                    postgres_port=pg_port,
                    kong_port=kong_port,
                )).encode())
            self.server.put(configBuf, os.path.join(self.path, '.config'))
            
        # read from config
        self.reload_config()
        
    def start(self):
        # check that docker is installed and running
        if self.server.info.get('docker_version', 'unknown') == 'unknown':
            raise RuntimeError("Docker is not installed on the server.")

        # run docker compose up
        self.server.run(f"cd {self.docker_path}; docker compose up -d", hide=self.quiet)

    def stop(self):
        # check that docker is installed and running
        if self.server.info.get('docker_version', 'unknown') == 'unknown':
            raise RuntimeError("Docker is not installed on the server.")
        # stop the compose project
        self.server.run(f"cd {self.docker_path}; docker compose down", hide=self.quiet)

    def setup(self, public_port: Optional[int] = None, kong_port: Optional[int] = None, postgres_port: Optional[int] = None):
        # if not downloaded, do that
        if not self.is_downloaded:
            self.download()

        # get the config
        if public_port is None or kong_port is None or postgres_port is None:
            config = self.config

            # check if any of the ports should be overwritten
            config['public_port'] = public_port or config['public_port']
            config['kong_port'] = kong_port or config['kong_port']
            config['postgres_port'] = postgres_port or config['postgres_port']

            # overwrite and reload
            self.config = config
            self.reload_config()

        # after download, update the settings
        self.update_supabase_config(jwt=True, postgres=True, domain=True)

    def update(self, rewrite_config=False):
        # check that git is installed
        if self.server.info.get('git_version', 'unknown') == 'unknown':
            raise RuntimeError("Git is not installed on the server.")
        
        # check that docker is installed
        if self.server.info.get('docker_version', 'unknown') == 'unknown':
            raise RuntimeError("Docker is not installed on the server.")

        # run the git pull command
        self.server.run(f"cd {os.path.join(self.path, 'supabase')}; git pull", hide=self.quiet)

        # if we need to rewrite the condig, do that
        if rewrite_config:
            self.update_supabase_config(jwt=True, postgres=True, domain=True)

        # run docker compose up
        # TODO before running this, check if the containers are running
        self.server.run(f"cd {self.docker_path}; docker compose up -d", hide=self.quiet)

    def remove(self):
        # first stop the docker service
        self.stop()

        # remove the path
        self.server.run(f"rm -rf {self.path}")

    @property
    def config(self) -> dict:
        # load the config into memory
        confBuf = io.BytesIO()
        self.server.get(os.path.join(self.path, '.config'), confBuf)
        return json.loads(confBuf.getvalue().decode())
    
    @config.setter
    def config(self, value: dict):
        # load the config dict into a buffer object
        confBuf = io.BytesIO(json.dumps(value).encode())

        # put the config to the server
        self.server.put(confBuf, os.path.join(self.path, '.config'))

    def reload_config(self):
        # get the config
        config = self.config

        # sync the settings
        self.jwt_secret = config['jwt_secret']
        self.postgres_password = config['postgres_password']
        self.postgres_port = config['postgres_port']
        self.kong_port = config['kong_port']
        self.public_port = config['public_port']

    @property
    def is_downloaded(self):
        # check if the supabase docker folder exists
        return self.server.exists(os.path.join(self.path, 'supabase', 'docker'))
    
    @property
    def is_configured(self):
        # get the env file
        envBuf = io.BytesIO()
        self.server.get(os.path.join(self.docker_path, '.env'), envBuf)
        
        # get the conf as string
        conf = envBuf.getvalue().decode()
        
        # make sure the passwords match
        return self.postgres_password in conf and self.jwt_secret in conf

    @property
    def site_url(self):
        if self.public_port == 80:
            return self.public_url
        else:
            return f"{self.public_url}:{self.public_port}"

    def download(self):
        # first verify that git is installed
        if self.server.info.get('git_version', 'unknown') == 'unknown':
            raise RuntimeError("Git is not installed on the server.")
    
        if not self.quiet:
            print(f"Initializing new project at: {self.path}")

        # build the command
        cloneCmd = f"cd {self.path}; git clone --depth 1 https://github.com/supabase/supabase"

        # run git to clone the supabase repo
        self.server.run(cloneCmd, hide=self.quiet)

        # copy over the example env file
        src = os.path.join(self.docker_path, '.env.example')
        dst = os.path.join(self.docker_path, '.env')
        self.server.cp(src, dst)

        if not self.quiet:
            print(f"Supabase downloaded.\nCreated config file at: {dst}")

    def generate_jwt(self, role: Union[Literal['anon'], Literal['service_role']]) -> str:
        # create the payload
        payload = dict(role=role, iss='supabase', iat=1689717600, exp=1847570400)

        # create headers
        headers = dict(alg='HS256', typ='JWT')

        encoded_jwt = jwt.encode(payload, self.jwt_secret, algorithm='HS256', headers=headers)

        return encoded_jwt

    def update_supabase_config(self, jwt=False, postgres=False, domain=False):
        # instantiate a Config object
        conf = SupabaseConfig(self)
        
        # update the postgres password
        if postgres:
            # set the password
            conf.set('postgres_password',  self.postgres_password)
            conf.set('postgres_port', self.postgres_port)
        
        # update the jwt secret
        if jwt:
            # replace jwt secret
            conf.set('jwt_secret',  self.jwt_secret)

            # repalce the api keys in the environment file
            conf.set('anon_jwt', self.generate_jwt('anon'))
            conf.set('service_jwt', self.generate_jwt('service_role'))

            # extract the kong config directly, there is no better way as of now
            kong = conf._kong

            # replace the keys in the API config
            anon = [c for c in kong['consumers'] if c['username'] == 'anon'][0]
            anon['keyauth_credentials'] = [{"key": self.generate_jwt('anon')}]

            service = [c for c in kong['consumers'] if c['username'] == 'service_role'][0]
            service['keyauth_credentials'] = [{"key": self.generate_jwt('service_role')}]
            kong['consumers'] = [anon, service]

            # save kong config back to the config object
            conf._kong = kong
        
        if domain:
            # replace the domain
            conf.set('site_url',self.site_url)

            # replace API url
            conf.set('api_url', f"{self.public_url}:{self.kong_port}")

            # replace ports
            conf.set('api_port', self.kong_port)
            conf.set('public_port', self.public_port)
        
        # finally save the config
        conf.save()

    def _curl_json(self, url: str) -> dict:
        # check that curl is available
        if self.server.info.get('curl_version', 'unknown') == 'unknown':
            raise RuntimeError("Curl is not installed on the server.")
        
        try:
            result = self.server.run(f'curl -H "Accept: application/json" {url}', hide='both')
        except Exception as e:
            return dict(error=str(e))
        return json.loads(result.stdout)

    def health(self) -> dict:
        message = dict(
            supabase_studio='error' not in self._curl_json(f"{self.site_url}/api/profile"),
            supabase_api='error' not in self._curl_json(f"{self.public_url}:{self.kong_port}")
        )

        return message

    def __call__(self):
        # check if the project is downloaded
        if not self.is_downloaded:
            self.setup()
        elif not self.is_configured:
            self.update_supabase_config(jwt=True, postgres=True, domain=True)
        
        # TODO change here then
        else:
            return self.health()
