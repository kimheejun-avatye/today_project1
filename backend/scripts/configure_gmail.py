"""Enter a Gmail app password locally, without echoing it or putting it in shell history."""
import argparse
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from dotenv import dotenv_values

def write_settings(path, values):
    lines = path.read_text().splitlines() if path.exists() else []
    pending = dict(values)
    result = []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in values:
            if key in pending:
                result.append(f'{key}={pending.pop(key)}')
        else:
            result.append(line)
    result.extend(f'{key}={value}' for key, value in pending.items())
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.gmail-settings-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(result) + '\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def main():
    parser = argparse.ArgumentParser(description='Gmail SMTP private configuration')
    parser.add_argument('--sender', help='Sender Gmail address (no passwords in command arguments)')
    args = parser.parse_args()
    path = backend / '.env'
    existing = dotenv_values(path, interpolate=False)
    sender = (args.sender or existing.get('SMTP_USER') or input('발신용 Gmail 주소: ')).strip().lower()
    if not re.fullmatch(r'[a-z0-9._+%-]+@(gmail|googlemail)\.com', sender):
        sys.exit('발신용 Gmail 주소를 확인해주세요.')
    if not sys.stdin.isatty():
        sys.exit('비밀번호 입력을 숨길 수 있는 로컬 터미널에서 실행해주세요.')
    raw = getpass.getpass('Google에서 발급한 16자리 앱 비밀번호 (입력 숨김): ')
    password = ''.join(raw.split())
    if not re.fullmatch(r'[A-Za-z0-9]{16}', password):
        sys.exit('16자리 앱 비밀번호를 확인해주세요. 일반 계정 비밀번호를 넣지 마세요.')
    write_settings(path, {'MAIL_MODE': 'smtp', 'SMTP_PROVIDER': 'gmail', 'SMTP_HOST': 'smtp.gmail.com',
                         'SMTP_PORT': '587', 'SMTP_USER': sender, 'SMTP_FROM': sender,
                         'SMTP_PASSWORD': password})
    print('Gmail 설정을 로컬 .env에 저장했습니다. 비밀번호는 표시하지 않습니다.')
    print('이어서 실행: .venv312/bin/python scripts/check_gmail.py')
    print('테스트 메일 접수 뒤 실제 도착 여부는 발신 계정의 메일함에서 확인해주세요.')

if __name__ == '__main__':
    main()
