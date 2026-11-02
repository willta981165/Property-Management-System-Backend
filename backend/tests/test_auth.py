ORG = 'TEST-0001'


class TestAdminRegister:
    def test_success(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': ORG,
            'name': '新管理員',
            'employee_id': 'ID-0099',
            'department': '工程部',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        assert res.status_code == 201
        assert 'access_token' in res.json

    def test_duplicate_employee_id(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': ORG,
            'name': '重複員工',
            'employee_id': 'ID-0001',
            'department': '管理部',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        assert res.status_code == 409

    def test_short_password(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': ORG,
            'name': '短密碼',
            'employee_id': 'ID-0050',
            'department': '管理部',
            'password': '123',
            'confirm_password': '123',
        })
        assert res.status_code == 400

    def test_invalid_employee_id_format(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': ORG,
            'name': '格式錯誤',
            'employee_id': 'WRONG',
            'department': '管理部',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        assert res.status_code == 400

    def test_password_mismatch(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': ORG,
            'name': '不一致',
            'employee_id': 'ID-0051',
            'department': '管理部',
            'password': 'password123',
            'confirm_password': 'different456',
        })
        assert res.status_code == 400

    def test_invalid_org_code(self, client):
        res = client.post('/api/auth/admin/register', json={
            'org_code': 'INVALID-9999',
            'name': '找不到',
            'employee_id': 'ID-0052',
            'department': '管理部',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        assert res.status_code == 404


class TestLogin:
    def test_admin_login_success(self, client):
        res = client.post('/api/auth/login', json={
            'org_code': ORG,
            'identifier': 'ID-0001',
            'password': 'password123',
        })
        assert res.status_code == 200
        assert 'access_token' in res.json
        assert 'refresh_token' in res.json

    def test_wrong_password(self, client):
        res = client.post('/api/auth/login', json={
            'org_code': ORG,
            'identifier': 'ID-0001',
            'password': 'wrongpassword',
        })
        assert res.status_code == 401

    def test_missing_fields(self, client):
        res = client.post('/api/auth/login', json={
            'org_code': ORG,
        })
        assert res.status_code == 400

    def test_invalid_org(self, client):
        res = client.post('/api/auth/login', json={
            'org_code': 'FAKE-0000',
            'identifier': 'ID-0001',
            'password': 'password123',
        })
        assert res.status_code == 400


class TestMe:
    def test_without_token(self, client):
        res = client.get('/api/auth/me')
        assert res.status_code == 401

    def test_with_valid_token(self, client):
        login = client.post('/api/auth/login', json={
            'org_code': ORG,
            'identifier': 'ID-0001',
            'password': 'password123',
        })
        token = login.json['access_token']

        res = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 200
        assert res.json['user']['employee_id'] == 'ID-0001'
