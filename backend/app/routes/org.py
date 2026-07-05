from flask import Blueprint, jsonify
from ..models.organization import Organization

org_bp = Blueprint('org', __name__)


@org_bp.route('/<string:org_code>', methods=['GET'])
def get_org(org_code):
    """
    查詢建案代碼
    ---
    tags:
      - Org
    parameters:
      - in: path
        name: org_code
        type: string
        required: true
        description: 建案代碼（不區分大小寫）
    responses:
      200:
        description: 建案存在，回傳名稱
        schema:
          type: object
          properties:
            name:
              type: string
              example: 幸福花園社區
            org_code:
              type: string
              example: HAPPY-0001
      404:
        description: 建案代碼無效
    """
    org = Organization.query.filter_by(org_code=org_code.upper(), is_active=True).first()
    if not org:
        return jsonify({'error': '建案代碼無效'}), 404
    return jsonify({'name': org.name, 'org_code': org.org_code}), 200
