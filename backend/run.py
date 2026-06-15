from app import create_app
from app.extensions import db
from app.models.admin import Admin
from app.models.resident import Resident

app = create_app()


@app.cli.command('init-db')
def init_db():
    """建立所有資料表（不建立任何帳號）。"""
    db.create_all()
    print('[OK] Tables created.')
    print('[  ] 請呼叫 POST /api/auth/admin/register 建立第一個管理員帳號。')


if __name__ == '__main__':
    app.run()
