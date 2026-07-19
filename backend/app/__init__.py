# Callers: run.py imports create_app from here. All blueprints registered here.
# Change: add logs dir double-check + global before/after_request log hooks.
# User instruction: "建立log機制...在本地產一個資料夾放logging.txt...每天晚上12點撥離成logging0719.txt"
import logging
import os
import time

from flask import Flask, g
from flask import request as flask_request
from flask_cors import CORS
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from flasgger import Swagger

from .config import get_config
from .extensions import db, jwt, bcrypt, migrate
from .utils.logger import LOG_DIR, app_logger

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
    # --- logs 目錄 double-check（已存在則不重建，參考 energy-dashboard application.py 模式）---
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

    app = Flask(__name__)
    app.config.from_object(get_config(env))

    CORS(app)
    Swagger(app, config=_swagger_config, template=_swagger_template)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    # --- 全域 request log ---
    @app.before_request
    def _before():
        g.req_start = time.time()
        try:
            verify_jwt_in_request(optional=True)
            claims = get_jwt()
            g.log_user_id   = get_jwt_identity()
            g.log_user_type = claims.get('user_type', '-')
            g.log_org_id    = claims.get('org_id', '-')
        except Exception:
            g.log_user_id   = '-'
            g.log_user_type = '-'
            g.log_org_id    = '-'

    @app.after_request
    def _after(response):
        ms  = int((time.time() - g.get('req_start', time.time())) * 1000)
        ip  = flask_request.headers.get('X-Forwarded-For', flask_request.remote_addr)
        uid = g.get('log_user_id', '-') or '-'
        ut  = g.get('log_user_type', '-') or '-'
        oid = g.get('log_org_id', '-') or '-'
        lvl = logging.WARNING if response.status_code >= 400 else logging.INFO
        app_logger.log(
            lvl,
            f"[REQUEST] {flask_request.method} {flask_request.path} | "
            f"ip={ip} | user_id={uid} | user_type={ut} | org_id={oid} | "
            f"status={response.status_code} | ms={ms}ms",
        )
        return response

    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.org import org_bp
    from .routes.admin_facility import admin_facility_bp
    from .routes.admin_booking import admin_booking_bp
    from .routes.resident_booking import resident_booking_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(org_bp, url_prefix='/api/org')
    app.register_blueprint(admin_facility_bp, url_prefix='/api/admin/facilities')
    app.register_blueprint(admin_booking_bp, url_prefix='/api/admin')
    app.register_blueprint(resident_booking_bp, url_prefix='/api')

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
