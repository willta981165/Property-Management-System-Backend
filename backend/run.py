import click
from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.admin import Admin
from app.models.resident import Resident

app = create_app()


@app.cli.command('init-db')
def init_db():
    """建立所有資料表。"""
    db.create_all()
    print('[OK] Tables created.')


@app.cli.command('create-org')
@click.option('--name', required=True, help='建案名稱，例如：幸福花園社區')
@click.option('--code', required=True, help='建案代碼，例如：HAPPY-0001')
def create_org(name, code):
    """建立一個新的建案（租戶）。"""
    code = code.upper()
    if Organization.query.filter_by(org_code=code).first():
        print(f'[ERROR] 建案代碼 {code} 已存在')
        return
    org = Organization(name=name, org_code=code)
    db.session.add(org)
    db.session.commit()
    print(f'[OK] 建案建立成功')
    print(f'     名稱：{name}')
    print(f'     代碼：{code}')
    print(f'     請將建案代碼交給客戶，讓管理員完成首次註冊。')


if __name__ == '__main__':
    app.run()
