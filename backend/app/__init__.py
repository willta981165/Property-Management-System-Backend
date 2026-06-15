from flask import Flask
from flask_cors import CORS
from flasgger import Swagger
from .config import get_config
from .extensions import db, jwt, bcrypt, migrate

_swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "社區管理系統 API",
        "description": "Civic App 後端 API 文件",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "格式：Bearer <access_token>",
        }
    },
    "consumes": ["application/json"],
    "produces": ["application/json"],
}

_swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs",
}


def create_app(env=None):
    app = Flask(__name__)
    app.config.from_object(get_config(env))

    CORS(app)
    Swagger(app, config=_swagger_config, template=_swagger_template)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    from .routes.auth import auth_bp
    from .routes.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    @app.get('/health')
    def health():
        """
        健康檢查
        ---
        tags:
          - System
        responses:
          200:
            description: 服務正常運作
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: ok
        """
        return {'status': 'ok'}, 200

    return app
