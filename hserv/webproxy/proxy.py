from typing import Optional
import abc
from dataclasses import dataclass, field

from hserv.server import HydrocodeServer

@dataclass
class WebProxy(abc.ABC):
    base_path: str
    server: HydrocodeServer = field(default_factory=HydrocodeServer, repr=False)

    @abc.abstractmethod
    def new_site_link(self, name: str, domain: Optional[str] = None, config_path: Optional[str] = None) -> None:
        pass

    @abc.abstractmethod
    def remove_site_link(self, name: str, remove_config: bool = False) -> None:
        pass

    @abc.abstractmethod
    def reload(self) -> None:
        pass

