# Backend Booking Taranto

## Technologies

- [X] Python
- [X] Django
- [X] Django Rest Framework
- [X] Docker
- [X] Postgresql
- [X] Redis
- [X] Celery
- [X] Ruff
- [X] Caddy

## Environments

This template is thought and designed for the docker environment. It is not recommended to use it without docker.


### How to use Docker dev

1. create a file named `.env` containing the required environment variables (read the next section)
2. run `docker compose up --build` for dev or `docker compose -f docker-compose.prod.yml up --build` for prod
3. work with your local files
4. execute commands inside the container. ex `docker exec -it backend-booking-taranto-app-1 python manage.py makemigrations`

Use Ruff to check the code quality. `ruff` command is already installed inside the container.
Example: `docker exec -it backend-booking-taranto-app-1 ruff check .` 

### Features

| Features                           |                            |
|------------------------------------|:--------------------------:|
| Auto-reload                        |            ❌ No            |
| Auto migrate at start              |             ✅              |
| Auto requirements install at start |             ✅              |
| Database                           |          MariaDB           |
| Database port publicly exposed     |             ✅              |
| Reverse proxy (Caddy)              |        ⚠️ Optional         |
| Debug                              | ⚠️ Optional (default=True) |
| Admin page                         |             ✅              |
| Serving media automatically        |             ✅              |
| CORS allow all                     |  ❌ No (default=localhost)  |
| Allow all hosts                    |  ❌ No (default=localhost)  |

There is google oauth2 authentication already implemented with django-allauth.
You have to create a google oauth2 app and add the credentials to the admin page.

### Required environment variables

- ✅ Required
- ❌ Not required
- ⚠️ Optional

| Variables                   |    |
|-----------------------------|:--:|
| DJANGO_SETTINGS_MODULE      | ✅  |
| DB_NAME                     | ✅  |
| DB_USERNAME                 | ✅  |
| DB_PASSWORD                 | ✅  |
| DB_HOSTNAME                 | ✅  |
| DB_PORT                     | ✅  |
| SECRET_KEY                  | ⚠️ |
| EMAIL_HOST                  | ⚠️ |
| EMAIL_HOST_PASSWORD         | ⚠️ |
| EMAIL_HOST_USER             | ⚠️ |
| EMAIL_PORT                  | ⚠️ |
| GOOGLE_CLIENT_ID            | ⚠️ |
| GOOGLE_CLIENT_SECRET        | ⚠️ |
| APPLE_CLIENT_ID             | ⚠️ |
| APPLE_CLIENT_SECRET         | ⚠️ |
| APPLE_KEY                   | ⚠️ |
| DEBUG                       | ⚠️ |
| DJANGO_ALLOWED_HOSTS        | ✅  |
| DJANGO_CORS_ALLOWED_ORIGINS | ✅  |
| DJANGO_CSRF_TRUSTED_ORIGINS | ✅  |
| CELERY_BROKER_URL           | ✅  |
| CELERY_RESULT_BACKEND       | ✅  |
| REDIS_BACKEND               | ✅  |
| CADDY_PORT                  | ✅  |
| CADDY_EMAIL                 | ✅  |
| DOMAIN                      | ✅  |


### drf-spectacular
To generate the schema.yml file run inside the container
`python manage.py spectacular --color --file schema.yml`
or outside the container
`docker exec -it backend-booking-taranto-app-1 python manage.py spectacular --color --file schema.yml`

### Google Calendar
Here are the steps you can follow to create a Google Calendar API in the Google Cloud Console:
1. Go to the Google Cloud Console and sign in with your Google account. 
2. In the dashboard, click on the "Select a Project" button in the top bar. If you haven't created any projects yet, you'll be prompted to create one. 
3. In the sidebar on the left, click on the "APIs & Services" button and then select "Credentials" from the menu. 
4. Click on the "Create credentials" button, then select "OAuth client ID". 
5. Select "Web application" as the application type, and enter a name for your application. 
6. In the "Authorized JavaScript Origins" and "Authorized Redirect URIs" fields, enter the URLs of your application that will be handling the OAuth flow. In this project, "http://localhost:8000" is set as the "Authorized JavaScript Origins" and "http://localhost:8000/api/v1/accounts/google-calendar/redirect/" is set as the "Authorized Redirect URIs" field. 
7. Click on the "Create" button. 
8. Once the OAuth client ID has been created, you'll be able to see the client ID and client secret in the "Credentials" tab. 
9. In the sidebar on the left, click on the "Library" button, then search for "Google Calendar API" and select it. 
10. Click on the "Enable" button to enable the Google Calendar API for your project. 
11. You can now use the client ID and client secret to authenticate with the Google Calendar API in your application.

### Example .env

```
DJANGO_SETTINGS_MODULE=core.config.settings.development (or .production)
SECRET_KEY=anotherrandomstring
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_PASSWORD=gmailpassword (Turn ON two factor authentication of gmail account, and create an app password - https://support.google.com/accounts/answer/185833)
EMAIL_HOST_USER=yourmail@gmail.com (gmail_username)
EMAIL_PORT=587
GOOGLE_CLIENT_ID=32193185322-05a6v4duc3cqhk25mjdc015g2903kr1n.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
APPLE_CLIENT_ID=com.example.app
APPLE_CLIENT_SECRET=applesecret
APPLE_KEY=applekey
DB_NAME=somerandomname
DB_USERNAME=somerandomusername
DB_PASSWORD=somerandomstring
DB_HOSTNAME=database
DB_PORT=5432
DEBUG=True
DJANGO_ALLOWED_HOSTS=*
DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:5000
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:5000
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
REDIS_BACKEND=redis://redis:6379/0
CADDY_PORT=80
CADDY_EMAIL=email@example.com
DOMAIN=example.com
FRONTEND_URL=http://localhost:5000
STRIPE_PUBLISHABLE_KEY=stripekey
STRIPE_SECRET_KEY=stripesecret
STRIPE_WEBHOOK_SECRET=whsec_7J9
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_STORAGE_BUCKET_NAME=your_bucket_name
AWS_S3_REGION_NAME=your_region_name
MY_ACCOUNT_SID=XXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=XXXXXXXXXXXXXX
MY_TWILIO_NUMBER=+XXXXXXXXXX
OWNER_PHONE_NUMBER=+393333333333
```