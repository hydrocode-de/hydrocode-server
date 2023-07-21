import abc
from dataclasses import dataclass, field

from hserv.server import HydrocodeServer

@dataclass
class WebProxy(abc.ABC):
    server: HydrocodeServer = field(default_factory=HydrocodeServer, repr=False)
