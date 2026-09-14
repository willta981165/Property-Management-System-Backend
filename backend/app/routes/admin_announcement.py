import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g, current_app
from ..extensions import db
from ..models.announcement import (
    Announcement, AnnouncementCategory, AnnouncementAttachment,
)
from ..utils.decorators import admin_required
from ..utils.logger import app_logger

admin_announcement_bp = Blueprint('admin_announcement', __name__)
admin_announcement_category_bp = Blueprint('admin_announcement_category', __name__)

_VALID_COLORS = {'green', 'orange', 'red', 'blue', 'gray'}


# ── 公告管理 ──

@admin_announcement_bp.route('', methods=['GET'])
@admin_required
def list_announcements():
    """
    取得公告列表（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: query
        name: category_id
        type: integer
        description: 篩選特定類別
      - in: query
        name: status
        type: string
        enum: [active, expired]
        description: 篩選狀態；active=有效，expired=已到期，留空=全部
    responses:
      200:
        description: 公告列表
      400:
        description: 無效的篩選參數
    """
    query = Announcement.query.filter_by(organization_id=g.org_id)

    category_id = request.args.get('category_id')
    if category_id:
        try:
            query = query.filter(Announcement.category_id == int(category_id))
        except (ValueError, TypeError):
            return jsonify({'error': '無效的 category_id'}), 400

    now = datetime.now(timezone.utc)
    status_filter = (request.args.get('status') or '').strip()
    if status_filter == 'active':
        query = query.filter(
            (Announcement.expires_at == None) | (Announcement.expires_at > now)
        )
    elif status_filter == 'expired':
        query = query.filter(
            Announcement.expires_at != None,
            Announcement.expires_at <= now,
        )
    elif status_filter:
        return jsonify({'error': '無效的 status，可選 active, expired'}), 400

    announcements = query.order_by(
        Announcement.is_pinned.desc(),
        Announcement.created_at.desc(),
    ).all()

    result = []
    for a in announcements:
        result.append({
            'id': a.id,
            'title': a.title,
            'content_preview': a.content[:80],
            'category': a.category.to_dict() if a.category else None,
            'is_pinned': a.is_pinned,
            'is_expired': bool(a.expires_at and a.expires_at < now),
            'expires_at': a.expires_at.isoformat() if a.expires_at else None,
            'attachment_count': len(a.attachments),
            'created_at': a.created_at.isoformat() if a.created_at else None,
            'updated_at': a.updated_at.isoformat() if a.updated_at else None,
        })

    return jsonify({'total': len(result), 'announcements': result}), 200


@admin_announcement_bp.route('', methods=['POST'])
@admin_required
def create_announcement():
    """
    新增公告（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [title, content]
          properties:
            title:
              type: string
              example: 9/15 全社區水塔年度高壓清洗作業通知
            content:
              type: string
              example: 為維護社區用水衛生...
            category_id:
              type: integer
              example: 1
            is_pinned:
              type: boolean
              example: false
            expires_at:
              type: string
              example: "2026-09-20"
    responses:
      201:
        description: 公告發布成功
      400:
        description: 欄位驗證錯誤
    """
    data = request.get_json(silent=True) or {}

    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()

    if not title:
        return jsonify({'error': 'title 為必填'}), 400
    if not (1 <= len(title) <= 50):
        return jsonify({'error': 'title 長度須在 1~50 字元'}), 400
    if not content:
        return jsonify({'error': 'content 為必填'}), 400

    category_id = data.get('category_id')
    if category_id is not None:
        cat = AnnouncementCategory.query.filter_by(
            id=category_id, organization_id=g.org_id
        ).first()
        if not cat:
            return jsonify({'error': '找不到指定的公告類別'}), 400

    is_pinned = bool(data.get('is_pinned', False))

    expires_at = None
    expires_at_str = (data.get('expires_at') or '').strip()
    if expires_at_str:
        try:
            expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({'error': 'expires_at 格式錯誤，應為 YYYY-MM-DD'}), 400
        if expires_at.date() < datetime.now(timezone.utc).date():
            return jsonify({'error': 'expires_at 不得早於今天'}), 400

    announcement = Announcement(
        organization_id=g.org_id,
        category_id=category_id,
        title=title,
        content=content,
        is_pinned=is_pinned,
        expires_at=expires_at,
        created_by_admin_id=g.admin.id,
    )
    db.session.add(announcement)
    db.session.commit()

    app_logger.info(
        f"[ANNOUNCEMENT] Created | admin_id={g.admin.id} | "
        f"announcement_id={announcement.id} | org_id={g.org_id}"
    )
    return jsonify({
        'message': '公告發布成功',
        'announcement': announcement.to_dict(include_attachments=True),
    }), 201


@admin_announcement_bp.route('/<int:announcement_id>', methods=['GET'])
@admin_required
def get_announcement(announcement_id):
    """
    取得公告詳情（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
    responses:
      200:
        description: 公告詳情（含附件與已讀數）
      404:
        description: 找不到公告
    """
    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=g.org_id
    ).first_or_404()

    read_count = len(announcement.reads)
    return jsonify(announcement.to_dict(include_attachments=True, read_count=read_count)), 200


@admin_announcement_bp.route('/<int:announcement_id>', methods=['PUT'])
@admin_required
def update_announcement(announcement_id):
    """
    編輯公告（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
            content:
              type: string
            category_id:
              type: integer
            is_pinned:
              type: boolean
            expires_at:
              type: string
              description: "YYYY-MM-DD，傳 null 代表移除期限"
    responses:
      200:
        description: 公告更新成功
      400:
        description: 欄位驗證錯誤
      404:
        description: 找不到公告
    """
    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=g.org_id
    ).first_or_404()

    data = request.get_json(silent=True) or {}

    if 'title' in data:
        title = (data['title'] or '').strip()
        if not (1 <= len(title) <= 50):
            return jsonify({'error': 'title 長度須在 1~50 字元'}), 400
        announcement.title = title

    if 'content' in data:
        content = (data['content'] or '').strip()
        if not content:
            return jsonify({'error': 'content 不可為空'}), 400
        announcement.content = content

    if 'category_id' in data:
        category_id = data['category_id']
        if category_id is not None:
            cat = AnnouncementCategory.query.filter_by(
                id=category_id, organization_id=g.org_id
            ).first()
            if not cat:
                return jsonify({'error': '找不到指定的公告類別'}), 400
        announcement.category_id = category_id

    if 'is_pinned' in data:
        announcement.is_pinned = bool(data['is_pinned'])

    if 'expires_at' in data:
        expires_at_val = data['expires_at']
        if expires_at_val is None:
            announcement.expires_at = None
        else:
            expires_at_str = (expires_at_val or '').strip()
            try:
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                return jsonify({'error': 'expires_at 格式錯誤，應為 YYYY-MM-DD'}), 400
            if expires_at.date() < datetime.now(timezone.utc).date():
                return jsonify({'error': 'expires_at 不得早於今天'}), 400
            announcement.expires_at = expires_at

    db.session.commit()

    app_logger.info(
        f"[ANNOUNCEMENT] Updated | admin_id={g.admin.id} | "
        f"announcement_id={announcement_id} | org_id={g.org_id}"
    )
    return jsonify({
        'message': '公告更新成功',
        'announcement': announcement.to_dict(include_attachments=True),
    }), 200


@admin_announcement_bp.route('/<int:announcement_id>', methods=['DELETE'])
@admin_required
def delete_announcement(announcement_id):
    """
    刪除公告（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
    responses:
      200:
        description: 公告已刪除
      404:
        description: 找不到公告
    """
    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=g.org_id
    ).first_or_404()

    for att in announcement.attachments:
        try:
            os.remove(att.file_path)
        except FileNotFoundError:
            pass

    db.session.delete(announcement)
    db.session.commit()

    app_logger.warning(
        f"[ANNOUNCEMENT] Deleted | admin_id={g.admin.id} | "
        f"announcement_id={announcement_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '公告已刪除'}), 200


@admin_announcement_bp.route('/<int:announcement_id>/attachments', methods=['POST'])
@admin_required
def upload_attachment(announcement_id):
    """
    上傳附件（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - in: path
        name: announcement_id
        type: integer
        required: true
      - in: formData
        name: file
        type: file
        required: true
        description: 上傳的附件（PDF、Word、Excel、圖片、純文字）
    responses:
      201:
        description: 附件上傳成功
      400:
        description: 欄位驗證錯誤或不支援的檔案類型
      404:
        description: 找不到公告
    """
    announcement = Announcement.query.filter_by(
        id=announcement_id, organization_id=g.org_id
    ).first_or_404()

    file = request.files.get('file')
    if not file:
        return jsonify({'error': '請提供 file 欄位'}), 400

    allowed_mimes = current_app.config.get('ALLOWED_MIME_TYPES', set())
    if file.mimetype not in allowed_mimes:
        return jsonify({'error': f'不支援的檔案類型：{file.mimetype}'}), 400

    original_filename = file.filename or 'unknown'
    ext = os.path.splitext(original_filename)[1]
    stored_filename = f"{uuid.uuid4()}{ext}"

    upload_root = current_app.config['UPLOAD_FOLDER']
    save_dir = os.path.join(upload_root, str(announcement_id))
    os.makedirs(save_dir, exist_ok=True)

    file_path = os.path.join(save_dir, stored_filename)
    file.save(file_path)
    file_size = os.path.getsize(file_path)

    attachment = AnnouncementAttachment(
        announcement_id=announcement_id,
        organization_id=g.org_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        mime_type=file.mimetype,
        file_size=file_size,
    )
    db.session.add(attachment)
    db.session.commit()

    app_logger.info(
        f"[ANNOUNCEMENT] Attachment uploaded | admin_id={g.admin.id} | "
        f"announcement_id={announcement_id} | attachment_id={attachment.id} | org_id={g.org_id}"
    )
    return jsonify({
        'message': '附件上傳成功',
        'attachment': attachment.to_dict(),
    }), 201


@admin_announcement_bp.route('/<int:announcement_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@admin_required
def delete_attachment(announcement_id, attachment_id):
    """
    刪除附件（管理員）
    ---
    tags:
      - Admin - Announcement
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
        description: 附件已移除
      404:
        description: 找不到附件
    """
    attachment = AnnouncementAttachment.query.filter_by(
        id=attachment_id,
        announcement_id=announcement_id,
        organization_id=g.org_id,
    ).first_or_404()

    file_path = attachment.file_path
    db.session.delete(attachment)
    db.session.commit()

    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass

    app_logger.warning(
        f"[ANNOUNCEMENT] Attachment deleted | admin_id={g.admin.id} | "
        f"announcement_id={announcement_id} | attachment_id={attachment_id} | org_id={g.org_id}"
    )
    return jsonify({'message': '附件已移除'}), 200


# ── 公告類別管理 ──

@admin_announcement_category_bp.route('', methods=['GET'])
@admin_required
def list_categories():
    """
    取得公告類別列表（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    responses:
      200:
        description: 類別列表
    """
    categories = (
        AnnouncementCategory.query
        .filter_by(organization_id=g.org_id)
        .order_by(AnnouncementCategory.id.asc())
        .all()
    )
    return jsonify({'categories': [c.to_dict() for c in categories]}), 200


@admin_announcement_category_bp.route('', methods=['POST'])
@admin_required
def create_category():
    """
    新增公告類別（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, color]
          properties:
            name:
              type: string
              example: 活動通知
            color:
              type: string
              enum: [green, orange, red, blue, gray]
              example: blue
    responses:
      201:
        description: 類別新增成功
      400:
        description: 欄位驗證錯誤
    """
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    color = (data.get('color') or '').strip()

    if not name:
        return jsonify({'error': 'name 為必填'}), 400
    if not (1 <= len(name) <= 30):
        return jsonify({'error': 'name 長度須在 1~30 字元'}), 400
    if color not in _VALID_COLORS:
        return jsonify({'error': f'color 只接受 {", ".join(sorted(_VALID_COLORS))}'}), 400

    existing = AnnouncementCategory.query.filter_by(
        organization_id=g.org_id, name=name
    ).first()
    if existing:
        return jsonify({'error': '此類別名稱已存在'}), 400

    category = AnnouncementCategory(
        organization_id=g.org_id,
        name=name,
        color=color,
    )
    db.session.add(category)
    db.session.commit()

    app_logger.info(
        f"[ANNOUNCEMENT] Category created | admin_id={g.admin.id} | "
        f"category_id={category.id} | name={name} | org_id={g.org_id}"
    )
    return jsonify({'message': '類別新增成功', 'category': category.to_dict()}), 201


@admin_announcement_category_bp.route('/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """
    刪除公告類別（管理員）
    ---
    tags:
      - Admin - Announcement
    security:
      - Bearer: []
    parameters:
      - in: path
        name: category_id
        type: integer
        required: true
    responses:
      200:
        description: 類別已刪除
      400:
        description: 此類別仍有公告在使用，無法刪除
      404:
        description: 找不到類別
    """
    category = AnnouncementCategory.query.filter_by(
        id=category_id, organization_id=g.org_id
    ).first_or_404()

    has_announcements = Announcement.query.filter_by(category_id=category_id).first()
    if has_announcements:
        return jsonify({'error': '此類別仍有公告在使用，請先移除或重新分類後再刪除'}), 400

    category_name = category.name
    db.session.delete(category)
    db.session.commit()

    app_logger.warning(
        f"[ANNOUNCEMENT] Category deleted | admin_id={g.admin.id} | "
        f"category_id={category_id} | name={category_name} | org_id={g.org_id}"
    )
    return jsonify({'message': '類別已刪除'}), 200
