"""

"""

from framework.routing import Rule, json_renderer
from website.routes import OsfWebRenderer

from website.addons.s3 import views

# TODO clean me up redo naming scheme

settings_routes = {
    'rules': [
        Rule(
            [
                '/project/<pid>/s3/settings/',
                '/project/<pid>/node/<nid>/s3/settings/',
            ],
            'post',
            views.config.s3_node_settings,
            json_renderer,
        ),
        Rule(
            [
                '/project/<pid>/s3/authorize/',
                '/project/<pid>/node/<nid>/s3/authorize/',
            ],
            'post',
            views.config.s3_authorize_node,
            json_renderer,
        ),
        Rule(
            '/settings/s3/',
            'post',
            views.config.s3_authorize_user,
            json_renderer,
        ),
        Rule(
            '/settings/s3/',
            'delete',
            views.config.s3_remove_user_settings,
            json_renderer,
        ),
    ],
    'prefix': '/api/v1',
}

api_routes = {
    'rules': [
        Rule([
            '/project/<pid>/s3/delete/<path:path>/',
            '/project/<pid>/node/<nid>/s3/delete/<path:path>/',
        ], 'delete', views.crud.s3_delete, json_renderer),
        Rule([
            '/project/<pid>/s3/upload/',
            '/project/<pid>/node/<nid>/s3/upload/'
        ], 'post', views.crud.s3_upload, json_renderer),
        Rule([
            '/project/<pid>/s3/download/<path:path>/',
            '/project/<pid>/node/<nid>/s3/download/<path:path>/'
        ], 'get', views.crud.s3_download, json_renderer),
        Rule([
            '/project/<pid>/s3/render/<path:path>/',
            '/project/<pid>/node/<nid>/s3/render/<path:path>/',
        ], 'get', views.crud.ping_render, json_renderer,),
        Rule([
            '/project/<pid>/s3/hgrid/',
            '/project/<pid>/node/<nid>/s3/hgrid/',
            '/project/<pid>/s3/hgrid/<path:path>/',
            '/project/<pid>/node/<nid>/s3/hgrid/<path:path>/',
        ], 'get', views.hgrid.s3_hgrid_data_contents, json_renderer),
        Rule([
            '/project/<pid>/s3/hgrid/dummy/',
            '/project/<pid>/node/<nid>/s3/hgrid/dummy/',
        ], 'get', views.hgrid.s3_dummy_folder, json_renderer),
        Rule([
            '/project/<pid>/s3/newbucket/',
            '/project/<pid>/node/<nid>/s3/newbucket/',
        ], 'post', views.utils.create_new_bucket, json_renderer),
    ],
    'prefix': '/api/v1',
}


nonapi_routes = {
    'rules': [
        Rule(
            [
                '/project/<pid>/s3/view/<path:path>/',
                '/project/<pid>/node/<nid>/s3/view/<path:path>/'
            ],
            'get',
            views.crud.s3_view,
            OsfWebRenderer('../addons/s3/templates/s3_render.mako'),
        ),
    ]
}