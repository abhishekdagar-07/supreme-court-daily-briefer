"""One-time helper to set up and test email delivery (Gmail).

How to get a Gmail App Password (needed instead of your normal password):
  1. The sending Gmail account must have 2-Step Verification ON
     (Google Account -> Security -> 2-Step Verification).
  2. Go to  https://myaccount.google.com/apppasswords
  3. Create an app password (name it e.g. "SC Briefer"). Google shows a
     16-character code like  abcd efgh ijkl mnop.
  4. Put your details in .env:
        EMAIL_ADDRESS=your_sending_account@gmail.com
        EMAIL_APP_PASSWORD=abcdefghijklmnop      (the 16 chars, spaces optional)
        EMAIL_TO=adv.abhishekdagar@gmail.com
  5. Test it:   py email_setup.py
"""
import config
import email_notify


def main():
    print("EMAIL_ADDRESS :", config.EMAIL_ADDRESS or "(not set)")
    print("EMAIL_TO      :", config.EMAIL_TO or "(not set)")
    print("APP_PASSWORD  :", "set" if config.EMAIL_APP_PASSWORD else "(not set)")
    if not email_notify.is_configured():
        print("\nNot fully configured yet — fill EMAIL_ADDRESS / EMAIL_APP_PASSWORD / EMAIL_TO in .env.")
        return
    print("\nSending a test email...")
    ok = email_notify.deliver_status(
        "This is a test from your Supreme Court Daily Briefer. If you can read this, "
        "email delivery is working.")
    print("Test email sent — check the inbox at " + config.EMAIL_TO if ok
          else "Failed to send — check the app password and EMAIL_ADDRESS (see logs above).")


if __name__ == "__main__":
    main()
