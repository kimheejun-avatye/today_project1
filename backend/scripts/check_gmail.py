"""Check TLS/authentication; send a message to the configured sender only on --send-test."""
import argparse
from pathlib import Path
import smtplib
import sys

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from app.core import config
from app.services import mail
from fastapi import HTTPException

def main():
    parser = argparse.ArgumentParser(description='Check Gmail without printing private settings')
    parser.add_argument('--send-test', action='store_true', help='Send a test to the configured sender account')
    args = parser.parse_args()
    if mail.status() != 'smtp':
        sys.exit(mail.configuration_problem() or '실제 Gmail 발송 설정이 필요합니다.')
    try:
        if args.send_test:
            import os
            mail.submit(os.environ['SMTP_USER'], '하루 Gmail 연결 확인',
                        '하루 사이트의 Gmail 발송 연결을 확인하는 테스트 메일입니다.\n가입 인증번호가 아닙니다.')
            print('Gmail이 테스트 메일을 접수했습니다. 받은편지함과 스팸함에서 도착을 확인해주세요.')
        else:
            with mail.connect():
                print('Gmail TLS 연결과 계정 인증을 확인했습니다. 메일은 발송하지 않았습니다.')
    except HTTPException as exc:
        sys.exit(str(exc.detail))
    except smtplib.SMTPAuthenticationError:
        sys.exit('Gmail 인증에 실패했습니다. 앱 비밀번호와 계정 설정을 확인해주세요.')
    except (OSError, smtplib.SMTPException):
        sys.exit('Gmail 연결에 실패했습니다. 네트워크와 계정 설정을 확인해주세요.')

if __name__ == '__main__':
    main()
