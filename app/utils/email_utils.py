# app/utils/email_utils.py

from flask_mail import Message

def send_otp_email(mail, recipient, otp):
    from flask_mail import Message
    msg = Message(
        subject='Verify Your Email - Pepmytrip',
        recipients=[recipient],
        body=f"Your OTP code is {otp}. It expires in 10 minutes.",
        sender=None  # Can be left out if you use MAIL_DEFAULT_SENDER
    )
    mail.send(msg)

def send_email(mail, to, subject, body):
    from flask_mail import Message
    msg = Message(subject, recipients=[to], body=body)
    mail.send(msg)


