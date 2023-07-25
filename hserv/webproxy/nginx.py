from dataclasses import field
from typing import Optional
import os
import io

import nginx

from .proxy import WebProxy
from hserv.supabase.controller import SupabaseController


class NginxProxy(WebProxy):
    base_path = field(default="/etc/nginx")
    
    def _set_base_config(self, supabase: SupabaseController, domain: str, conf: Optional[nginx.Conf] = None) -> nginx.Conf:
        # initialize a new config
        if conf is None:
            conf = nginx.Conf()

        # map the connection_upgrade
        conf.add(nginx.Map(
            '$http_upgrade $connection_upgrade',
            nginx.Key('default', 'upgrade'),
            nginx.Key("''", 'close'),
        ))
        
        # create the two upsreams for supabase and kong
        conf.add(nginx.Upstream('supabase', nginx.Key('server', f"localhost:{supabase.public_port}")))
        conf.add(nginx.Upstream('kong', nginx.Key('server', f'localhost:{supabase.kong_port}')))

        # build the main server
        s = nginx.Server()

        # add config
        s.add(
            nginx.Key('listen', '80'),
            nginx.Key('server_name', domain),

            # add the REST location
            nginx.Location(
                '~ ^/rest/v1/(.*)$',
                nginx.Key('proxy_set_header', 'Host $host'),
                nginx.Key('proxy_pass', 'http://kong'),
                nginx.Key('proxy_redirect', 'off')
            ),

            # add the AUTH location
            nginx.Location(
                '~ ^/auth/v1/(.*)$',
                nginx.Key('proxy_set_header', 'Host $host'),
                nginx.Key('proxy_pass', 'http://kong'),
                nginx.Key('proxy_redirect', 'off')
            ),

            # add the REALTIME location
            nginx.Location(
                '~ ^/realtime/v1/(.*)$',
                nginx.Key('proxy_redirect', 'off'),
                nginx.Key('proxy_pass', 'http://kong'),
                nginx.Key('proxy_http_version', '1.1'),
                nginx.Key('proxy_set_header', 'Upgrade $http_upgrade'),
                nginx.Key('proxy_set_header', 'Connection $connection_upgrade'),
                nginx.Key('proxy_set_header', 'Host $host'),
            ),

            # add the supabase STUDIO location
            nginx.Location(
                '/',
                nginx.Key('proxy_set_header', 'Host $host'),
                nginx.Key('proxy_pass', 'http://supabase'),
                nginx.Key('proxy_redirect', 'off'),
                nginx.Key('proxy_set_header', 'Upgrade $http_upgrade')
            ),
        )

        # append server section
        conf.add(s)

        return conf

    def new_site_link(self, name: str, domain: Optional[str] = None, config_path: Optional[str] = None) -> None:
        # get the supabase controller
        supabase = self.server.supabase(name)

        # generate a domain if none is given
        if domain is None:
            domain = supabase.public_url

        # generate the config
        conf = self._set_base_config(supabase, domain=domain)

        # create a config path is none is given
        if config_path is None:
            config_path = os.path.join(supabase.path, 'nginx')

        # check if the path exits
        if not self.server.exists(config_path):
            self.server.run(f"mkdir -p {config_path}")
        
        # dump the config
        confBuf = io.BytesIO(nginx.dumps(conf).encode())
        confBuf.seek(0)
        self.server.put(confBuf, os.path.join(config_path, f'{domain}.conf'))

        # symlink the config to sites-enabled
        src = os.path.join(config_path, f'{domain}.conf')
        dst = os.path.join(self.base_path, 'sites-enabled', f'{domain}.conf')
        self.server.run(f"ln -s {src if src.startswith('/') else '/%s' % src} {dst if dst.startswith('/') else '/%s' % dst}")

    def remove_site_link(self, name: str, remove_config: bool = False) -> None:
        # get a supabase controller
        supabase = self.server.supabase(name)

        # remove the symlink
        self.server.run(f"rm {os.path.join(self.base_path, 'sites-enabled', f'{supabase.public_url}.conf')}")

        # remove the nginx subfolder
        if remove_config:
            self.server.run(f"rm -rf {os.path.join(supabase.path, 'nginx')}")

    def reload(self) -> None:
        self.server.run("service nginx reload")