from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models.announcement import (
    Announcement, AnnouncementCategory, AnnouncementAttachment,
)
from ..models.announcement_read import AnnouncementRead
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_announcement_bp = Blueprint('resident_announcement', __name__)


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    org_id = claims.get('org_id')
    if not org_id:
        return None, None
    resident = db.session.get(Resident, int(get_jwt_identity()))
    return resident, org_id


@resident_announcement_bp.route('', methods=['GET'])
@jwt_required()
def list_announcements():
    """
    取得社區公告列表（住戶）
    ---
    tags:
      - Resident - Announcement
    security:
      - Bearer: []
    parameters:
      - in: query
        name: category_id
        type: integer
        description: 篩選特定類別
    responses:
      200:
        description: 公告列表（僅含有效公告）及該 org 全部類別
      403:
        description: 僅住戶可使用
      400:
        description: 無效的 category_id
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    now = datetime.now(timezone.utc)

    query = Announcement.query.filter_by(organization_id=org_id).filter(
        (Announcement.expires_at == None) | (Announcement.expires_at > now)
    )

    category_id = request.args.get('category_id')
    if category_id:
        try:
            query = query.filter(Announcement.category_id == int(category_id))
        except (ValueError, TypeError):
            return jsonify({'error': '無效的 category_id'}), 400

    announcements = query.order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc(),
    ).all()

    read_ids = {
        r.announcement_id
        for r in AnnouncementRead.query.filter_by(
            resident_id=resident.id, organization_id=org_id
        ).all()
    }

    result = []
    for a in announcements:
        result.append({
            'id': a.id,
            'title': a.title,
            'content_preview': a.content[:80],
            'category': a.category.to_dict() if a.category else None,
            'is_pinned': a.is_pinned,
            'has_attachment': len(a.attachments) > 0,
            'is_read': a.id in read_ids,
            'created_at': a.created_at.isoformat() if a.created_at else None,
        })

    categories = (
        AnnouncementCategory.query
        .filter_by(organization_id=org_id)
        .order_by(AnnouncementCategory.id.asc())
        .all()
    )

    return jsonify({
        'categories': [c.to_dict() for c in categories],
        'announcements': result,
    }), 200


@resident_announcement_bp.route('/<int:announcement_id>', methods=['GET'])
@jwt_required()
def get_announcement(announcement_id):
    """
    取得公告詳情（住戶）
    ---
    tags:
      - Resident - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
    responses:
      200:
        description: 公告詳情（含附件清單），首次查看自動建立已讀記錄
      403:
        description: 僅住戶可使用
      404:
        description: 找不到公告或公告已到期
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    now = datetime.now(timezone.utc)

    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=org_id
    ).first()

    if not announcement:
        return jsonify({'error': '找不到公告'}), 404

    if announcement.expires_at and announcement.expires_at <= now:
        return jsonify({'error': '此公告已到期'}), 404

    existing_read = AnnouncementRead.query.filter_by(
        announcement_id=announcement_id, resident_id=resident.id
    ).first()
    if not existing_read:
        db.session.add(AnnouncementRead(
            announcement_id=announcement_id,
            resident_id=resident.id,
            organization_id=org_id,
        ))
        db.session.commit()
        app_logger.info(
            f"[ANNOUNCEMENT] Read | resident_id={resident.id} | "
            f"announcement_id={announcement_id} | org_id={org_id}"
        )

    return jsonify({
        'id': announcement.id,
        'title': announcement.title,
        'content': announcement.content,
        'category': announcement.category.to_dict() if announcement.category else None,
        'is_pinned': announcement.is_pinned,
        'attachments': [a.to_dict() for a in announcement.attachments],
        'created_at': announcement.created_at.isoformat() if announcement.created_at else None,
        'updated_at': announcement.updated_at.isoformat() if announcement.updated_at else None,
    }), 200


@resident_announcement_bp.route(
    '/<int:announcement_id>/attachments/<int:attachment_id>/download',
    methods=['GET'],
)
@jwt_required()
def download_attachment(announcement_id, attachment_id):
    """
    下載附件（住戶）
    ---
    tags:
      - Resident - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
      - in: path
        name: attachment_id
        type: integer
        required: true
    responses:
      200:
        description: "附件檔案串流（Content-Disposition: attachment）"
      403:
        description: 僅住戶可使用
      404:
        description: 找不到公告、公告已到期或找不到附件
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    now = datetime.now(timezone.utc)

    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=org_id
    ).first()

    if not announcement:
        return jsonify({'error': '找不到公告'}), 404

    if announcement.expires_at and announcement.expires_at <= now:
        return jsonify({'error': '此公告已到期'}), 404

    attachment = AnnouncementAttachment.query.filter_by(
        id=attachment_id,
        announcement_id=announcement_id,
        organization_id=org_id,
    ).first()

    if not attachment:
        return jsonify({'error': '找不到附件'}), 404

    app_logger.info(
        f"[ANNOUNCEMENT] Download | resident_id={resident.id} | "
        f"announcement_id={announcement_id} | attachment_id={attachment_id} | org_id={org_id}"
    )

    return send_file(
        attachment.file_path,
        mimetype=attachment.mime_type,
        as_attachment=True,
        download_name=attachment.original_filename,
    )
