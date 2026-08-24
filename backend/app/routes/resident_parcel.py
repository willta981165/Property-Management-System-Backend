from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from ..extensions import db
from ..models.parcel import Parcel, ParcelStatus
from ..models.resident import Resident
from ..utils.logger import app_logger

resident_parcel_bp = Blueprint('resident_parcel', __name__)

_OVERDUE_DAYS = 7
_CLOSED = {ParcelStatus.picked_up, ParcelStatus.returned, ParcelStatus.abnormal}


def _utc_now():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _get_resident():
    claims = get_jwt()
    if claims.get('user_type') != 'resident':
        return None, None
    org_id = claims.get('org_id')
    resident = db.session.get(Resident, int(get_jwt_identity()))
    return resident, org_id


def _lazy_overdue_single(parcel):
    if parcel.status == ParcelStatus.pending:
        if _aware(parcel.arrived_at) + timedelta(days=_OVERDUE_DAYS) < _utc_now():
            parcel.status = ParcelStatus.overdue
            db.session.commit()


def _lazy_overdue_batch(parcels):
    needs_commit = False
    for p in parcels:
        if p.status == ParcelStatus.pending:
            if _aware(p.arrived_at) + timedelta(days=_OVERDUE_DAYS) < _utc_now():
                p.status = ParcelStatus.overdue
                needs_commit = True
    if needs_commit:
        db.session.commit()


def _compute_days(parcel):
    days_waiting = (_utc_now() - _aware(parcel.arrived_at)).days
    if parcel.status == ParcelStatus.pending:
        return days_waiting, max(0, _OVERDUE_DAYS - days_waiting), None
    if parcel.status == ParcelStatus.overdue:
        return days_waiting, None, max(0, days_waiting - _OVERDUE_DAYS)
    return days_waiting, None, None


@resident_parcel_bp.route('', methods=['GET'])
@jwt_required()
def list_my_parcels():
    """
    取得我的包裹列表（住戶）
    ---
    tags:
      - Resident - Parcel
    security:
      - Bearer: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, overdue, closed]
        description: 篩選狀態；closed 包含 picked_up, returned, abnormal
    responses:
      200:
        description: 包裹列表
      403:
        description: 僅住戶可使用
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    query = Parcel.query.filter_by(resident_id=resident.id, organization_id=org_id)

    status_filter = (request.args.get('status') or '').strip()
    if status_filter == 'closed':
        query = query.filter(Parcel.status.in_(list(_CLOSED)))
    elif status_filter:
        try:
            query = query.filter(Parcel.status == ParcelStatus(status_filter))
        except ValueError:
            return jsonify({'error': '無效的狀態，可選 pending, overdue, closed'}), 400

    parcels = query.order_by(Parcel.arrived_at.desc()).all()
    _lazy_overdue_batch(parcels)

    result = []
    for p in parcels:
        days_waiting, days_remaining, overdue_days = _compute_days(p)
        result.append({
            'id': p.id,
            'parcel_code': p.parcel_code,
            'logistics_company': p.logistics_company,
            'size': p.size.value if p.size else None,
            'quantity': p.quantity,
            'storage_location': p.storage_location,
            'arrived_at': p.arrived_at.isoformat() if p.arrived_at else None,
            'status': p.status.value if p.status else None,
            'days_waiting': days_waiting,
            'days_remaining': days_remaining,
            'overdue_days': overdue_days,
        })

    return jsonify({'parcels': result}), 200


@resident_parcel_bp.route('/<int:parcel_id>', methods=['GET'])
@jwt_required()
def get_my_parcel(parcel_id):
    """
    取得包裹詳情（住戶）
    ---
    tags:
      - Resident - Parcel
    security:
      - Bearer: []
    parameters:
      - in: path
        name: parcel_id
        type: integer
        required: true
    responses:
      200:
        description: 包裹詳情
      403:
        description: 無權查看此包裹
      404:
        description: 找不到包裹
    """
    resident, org_id = _get_resident()
    if not resident:
        return jsonify({'error': '僅住戶可使用此功能'}), 403

    parcel = Parcel.query.filter_by(id=parcel_id, organization_id=org_id).first_or_404()

    if parcel.resident_id != resident.id:
        return jsonify({'error': '無權查看此包裹'}), 403

    _lazy_overdue_single(parcel)

    days_waiting, days_remaining, overdue_days = _compute_days(parcel)
    return jsonify({
        'id': parcel.id,
        'parcel_code': parcel.parcel_code,
        'logistics_company': parcel.logistics_company,
        'size': parcel.size.value if parcel.size else None,
        'quantity': parcel.quantity,
        'storage_location': parcel.storage_location,
        'notes': parcel.notes,
        'arrived_at': parcel.arrived_at.isoformat() if parcel.arrived_at else None,
        'status': parcel.status.value if parcel.status else None,
        'days_waiting': days_waiting,
        'days_remaining': days_remaining,
        'overdue_days': overdue_days,
        'abnormal_reason': parcel.abnormal_reason,
        'picked_up_at': parcel.picked_up_at.isoformat() if parcel.picked_up_at else None,
        'created_at': parcel.created_at.isoformat() if parcel.created_at else None,
    }), 200
