import pytest
from app import create_app
from app.extensions import db as _db
from app.models.organization import Organization
from app.models.admin import Admin


@pytest.fixture(scope='session')
def app():
    _app = create_app('testing')
    with _app.app_context():
        _db.create_all()

        org = Organization(name='測試社區', org_code='TEST-0001', is_active=True)
        _db.session.add(org)
        _db.session.flush()

        admin = Admin(
            organization_id=org.id,
            name='測試管理員',
            employee_id='ID-0001',
            department='管理部',
        )
        admin.set_password('password123')
        _db.session.add(admin)
        _db.session.commit()

        yield _app
        _db.drop_all()


@pytest.fixture(scope='session')
def client(app):
    return app.test_client()
