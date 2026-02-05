# Sending password reset link by email

The API can send the reset link by email when SMTP is configured. Follow these steps.

## 1. Choose an email provider

Use one of these (or any SMTP server):

| Provider   | SMTP host           | Port | Notes |
|-----------|---------------------|------|--------|
| Gmail     | smtp.gmail.com      | 587  | Use an [App Password](https://support.google.com/accounts/answer/185833), not your normal password. |
| SendGrid  | smtp.sendgrid.net   | 587  | Use API key as password. |
| Resend    | smtp.resend.com     | 587  | Use API key as password. |
| Mailgun   | smtp.mailgun.org    | 587  | Use SMTP credentials from dashboard. |
| Your host | Your provider’s host | 587 or 465 | Use the host and port they give you. |

## 2. Set environment variables

Add these where your **API** runs (e.g. Render dashboard, or `.env` locally).

**Required for email:**

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
EMAIL_FROM=noreply@yourdomain.com
```

**Optional but recommended (so the link points to your app):**

```env
FRONTEND_URL=https://your-frontend-domain.com
```

- No trailing slash on `FRONTEND_URL`.
- `SMTP_USE_TLS` defaults to `true`; set to `false` only if your provider says so.

## 3. Gmail example

1. Turn on 2-Step Verification for your Google account.
2. Go to [App passwords](https://myaccount.google.com/apppasswords) and create a password for “Mail”.
3. Set in your API env:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=the-16-char-app-password
EMAIL_FROM=your.email@gmail.com
FRONTEND_URL=https://your-app.vercel.app
```

## 4. Deploy / restart

- **Render:** Environment → add the variables → Save. Redeploy the API service.
- **Local:** Put variables in `apps/api-python/.env` and restart the API (e.g. `uvicorn`).

## 5. Test

1. Open your app’s “Forgot password” page.
2. Enter an email that exists in your app.
3. Submit.
4. If SMTP is configured, the API sends an email and the response says “A password reset link has been sent to your email.”
5. Check the inbox (and spam) for that address; open the link and set a new password.

If you don’t set SMTP, the reset link is still returned in the API response and shown on the forgot-password page (“Open reset link” / “Copy link”), so users can reset without email.
