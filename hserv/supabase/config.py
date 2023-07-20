from dataclasses import dataclass, field
import os
import io

from .controller import SupabaseController



@dataclass
class SupabaseConfig:
    controller: SupabaseController = field(repr=False)

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
        self._kong = kongBuf.getvalue()

    def save(self):
        # load the current config into buffers
        envBuf = io.StringIO(self._env)
        kongBuf = io.StringIO(self._kong)

        # send to the server
        self.controller.server.put(envBuf, self._env_path)
        self.controller.server.put(kongBuf, self._kong_path)


    def __getattr__(self, name: str):
        if name in self._env:
            return 'Found in ENV'
        elif name in self._kong:
            return 'Found in KONG'
        else:
            raise AttributeError(F"The configuration value '{name}' is not kwown.")

    def get(self, name: str, default=None):
        try:
            return getattr(self, name)
        except AttributeError:
            return default
        
        

    # def __setattr__(self, name, value):
    #     if name in ["path", "mode", "_config"]:
    #         super().__setattr__(name, value)
    #     else:
    #         self._config[name] = value

    # def __delattr__(self, name):
    #     if name in self._config:
    #         del self._config[name]
    #     else:
    #         raise AttributeError(f"'SupabaseConfig' object has no attribute '{name}'")

